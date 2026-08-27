"""Populate tier_assignments from existing wiki_notes.

Usage:
    python ingest_tiers.py

This walks every row in wiki_notes, runs the heuristic classifier, and
upserts a tier_assignments record. Re-running is safe (idempotent).
"""

from __future__ import annotations

from postgres_store import initialize_schema, connect
from tier_classify import classify
from tier_store import apply_tier_schema, upsert_assignment


def main() -> None:
    # Make sure the base + tier schemas exist.
    initialize_schema()
    apply_tier_schema()

    with connect() as connection:
        rows = connection.execute(
            "SELECT id, source_id, title FROM wiki_notes"
        ).fetchall()

    print(f"Found {len(rows)} notes. Classifying...")
    tier_counts = {1: 0, 2: 0, 3: 0}
    for row in rows:
        est = classify(row["title"], row["source_id"])
        assignment = upsert_assignment(
            source_id=row["source_id"],
            reviews=est.reviews,
            sales=est.sales,
            is_private=est.is_private,
            rationale=est.rationale,
        )
        tier_counts[assignment["tier"]] += 1
        print(
            f"[T{assignment['tier']}] {row['title']!r} "
            f"-> score={assignment['score']:.1f} ({est.rationale})"
        )

    print("\nTier distribution:")
    for tier, count in sorted(tier_counts.items()):
        print(f"  Tier {tier}: {count}")


if __name__ == "__main__":
    main()
