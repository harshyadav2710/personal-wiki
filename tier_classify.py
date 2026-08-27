"""Heuristic tier classifier.

The classifier converts a (title, author, source_id) triple into an estimated
review count and sale count. These are used to compute a tier score:

    score = reviews * 1.0 + sales * 0.1

The score is then bucketed by tier_store.compute_tier() into Tier 1/2/3.

The numbers are NOT real review/sale data. They are stable, deterministic
proxies seeded from the Gutenberg ID range (lower IDs = more famous works)
and a small whitelist of titles we know to be canonical classics. The
intent is to demonstrate the tiered layout; replace these heuristics with
real data when it becomes available.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# (substring, reviews, sales) - substring is matched case-insensitively
# against the title. These are intentionally rough.
_WHITELIST: list[tuple[str, int, int]] = [
    ("declaration of independence", 95, 800),
    ("constitution", 90, 750),
    ("bill of rights", 80, 600),
    ("gettysburg", 92, 700),
    ("common sense", 85, 650),
    ("communist manifesto", 78, 500),
    ("discourse on the method", 70, 300),
    ("tao teh king", 72, 320),
    ("renaissance", 60, 200),
    ("paradise regained", 74, 360),
    ("jeckyll and mr hyde", 95, 900),  # both spellings attempted
    ("jekyll and mr hyde", 95, 900),
    ("jeckyll", 95, 900),
    ("casque of amontillado", 88, 700),
    ("cask of amontillado", 88, 700),
    ("fall of the house of usher", 90, 720),
    ("masque of the red death", 84, 650),
    ("monkey's paw", 86, 680),
    ("the yellow wallpaper", 89, 700),
    ("rip van winkle", 82, 600),
    ("legend of sleepy hollow", 88, 720),
    ("tom sawyer", 93, 850),
    ("david copperfield", 0, 0),  # explicit zero - never in whitelist
]

PRIVATE_TITLE_HINTS = ("personal", "about me", "about_me")


@dataclass
class TierEstimate:
    reviews: int
    sales: int
    is_private: bool
    rationale: str


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _looks_private(title: str, source_id: str) -> bool:
    blob = _normalize(f"{title} {source_id}")
    return any(hint in blob for hint in PRIVATE_TITLE_HINTS)


def _gutenberg_id(source_id: str) -> int | None:
    match = re.search(r"(\d{3,6})", source_id or "")
    return int(match.group(1)) if match else None


def classify(title: str, source_id: str = "") -> TierEstimate:
    norm = _normalize(title)
    is_private = _looks_private(title, source_id)

    if is_private:
        return TierEstimate(reviews=0, sales=0, is_private=True, rationale="private note")

    for needle, reviews, sales in _WHITELIST:
        if needle and needle in norm:
            return TierEstimate(
                reviews=reviews,
                sales=sales,
                is_private=False,
                rationale=f"whitelist match: {needle}",
            )

    gut_id = _gutenberg_id(source_id)
    if gut_id is not None:
        # Lower Gutenberg IDs are generally older, more famous works.
        if gut_id <= 12:
            return TierEstimate(reviews=88, sales=620, is_private=False, rationale="early Gutenberg id")
        if gut_id <= 40:
            return TierEstimate(reviews=70, sales=380, is_private=False, rationale="mid Gutenberg id")
        if gut_id <= 70:
            return TierEstimate(reviews=45, sales=180, is_private=False, rationale="late Gutenberg id")
        return TierEstimate(reviews=20, sales=60, is_private=False, rationale="recent Gutenberg id")

    return TierEstimate(reviews=15, sales=40, is_private=False, rationale="default low estimate")
