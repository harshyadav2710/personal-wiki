"""Tiered wrapper around postgres_store.

This module adds tier classification on top of the existing personal-wiki
schema. It does NOT modify postgres_store.py or schema.sql.

Tier rule (curation-based, by review/sale proxy):
    Tier 1 = highest curation score (top third of scored notes)
    Tier 2 = middle curation score
    Tier 3 = lowest curation score, OR any private note

Enforcement is application-level: MCP servers are pinned to a single tier
via the MCP_TIER env var and only return rows whose assigned tier is in
that server's allowlist.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

from postgres_store import PG_DSN, connect  # noqa: F401  (re-exported)

load_dotenv(Path(__file__).resolve().parent / ".env")

# Map: MCP_TIER env value -> set of tiers that server is allowed to expose.
TIER_ALLOWLIST = {
    1: {1, 2, 3},  # MCP 1 sees everything
    2: {2, 3},     # MCP 2 sees T2 + T3
    3: {3},        # MCP 3 sees T3 only
}

PRIVATE_TAG = "myself"
PRIVATE_FILENAME_HINTS = ("personal", "about_me")


def _is_private_title(title: str, source_id: str) -> bool:
    haystack = f"{title} {source_id}".lower()
    return any(hint in haystack for hint in PRIVATE_FILENAME_HINTS)


def compute_tier(score: float, is_private: bool) -> int:
    """Bucket a raw score into a tier.

    Scoring is intentionally simple and review/sale driven:
        score = reviews * 1.0 + sales * 0.1
    The top third of observed scores becomes Tier 1, the next third Tier 2,
    the bottom third Tier 3. Private notes are always Tier 3.
    """
    if is_private:
        return 3
    if score >= 80:
        return 1
    if score >= 25:
        return 2
    return 3


def apply_tier_schema() -> None:
    with connect() as connection:
        connection.execute(Path("tier_schema.sql").read_text(encoding="utf-8"))
        connection.commit()


def upsert_assignment(
    source_id: str,
    reviews: int,
    sales: int,
    is_private: bool = False,
    rationale: str | None = None,
) -> dict:
    """Insert or update the tier assignment for a single source_id."""
    score = float(reviews) + 0.1 * float(sales)
    tier = compute_tier(score, is_private)
    with connect() as connection:
        row = connection.execute(
            """
            INSERT INTO tier_assignments
                (source_id, tier, score, reviews, sales, is_private, rationale, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id) DO UPDATE SET
                tier = EXCLUDED.tier,
                score = EXCLUDED.score,
                reviews = EXCLUDED.reviews,
                sales = EXCLUDED.sales,
                is_private = EXCLUDED.is_private,
                rationale = EXCLUDED.rationale,
                updated_at = EXCLUDED.updated_at
            RETURNING source_id, tier, score, reviews, sales, is_private, rationale
            """,
            (
                source_id,
                tier,
                score,
                reviews,
                sales,
                is_private,
                rationale,
                datetime.now(timezone.utc),
            ),
        ).fetchone()
        connection.commit()
    return row


def assignment_for(source_id: str) -> dict | None:
    with connect() as connection:
        return connection.execute(
            "SELECT * FROM tier_assignments WHERE source_id = %s",
            (source_id,),
        ).fetchone()


def _server_tier() -> int:
    raw = os.getenv("MCP_TIER", "1").strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError(f"MCP_TIER must be 1, 2, or 3; got {raw!r}") from error
    if value not in TIER_ALLOWLIST:
        raise RuntimeError(f"MCP_TIER must be 1, 2, or 3; got {value}")
    return value


def allowed_tiers() -> set[int]:
    """Return the tiers that the running MCP server is permitted to expose."""
    return TIER_ALLOWLIST[_server_tier()]


# ---------------------------------------------------------------------------
# Tier-aware read paths. Each function restricts results to allowed_tiers().
# ---------------------------------------------------------------------------

def search_tiered(query: str, limit: int = 5) -> list[dict]:
    """Search wiki_notes via the tiered view, filtered by allowed tiers."""
    from postgres_store import search_notes  # local import to avoid cycles

    allowed = allowed_tiers()
    candidates = search_notes(query, limit=limit * 5)
    if not candidates:
        return []
    ids = [row["id"] for row in candidates]
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT n.id, n.title, n.content, n.tags, n.created_at,
                   a.tier, a.is_private, a.score
            FROM wiki_notes n
            LEFT JOIN tier_assignments a ON a.source_id = n.source_id
            WHERE n.id = ANY(%s) AND COALESCE(a.tier, 3) = ANY(%s)
            ORDER BY a.score DESC NULLS LAST, n.id
            LIMIT %s
            """,
            (ids, list(allowed), limit),
        ).fetchall()
    return rows


def get_tiered(note_id: int) -> dict | None:
    allowed = allowed_tiers()
    with connect() as connection:
        return connection.execute(
            """
            SELECT n.id, n.source_id, n.title, n.content, n.tags, n.created_at,
                   a.tier, a.is_private, a.score
            FROM wiki_notes n
            LEFT JOIN tier_assignments a ON a.source_id = n.source_id
            WHERE n.id = %s AND COALESCE(a.tier, 3) = ANY(%s)
            """,
            (note_id, list(allowed)),
        ).fetchone()


def list_recent_tiered(limit: int = 10) -> list[dict]:
    allowed = allowed_tiers()
    with connect() as connection:
        return connection.execute(
            """
            SELECT n.id, n.title, n.tags, n.created_at, a.tier, a.score
            FROM wiki_notes n
            LEFT JOIN tier_assignments a ON a.source_id = n.source_id
            WHERE COALESCE(a.tier, 3) = ANY(%s)
            ORDER BY n.created_at DESC
            LIMIT %s
            """,
            (list(allowed), max(1, min(limit, 50))),
        ).fetchall()


def save_tiered(title: str, content: str, tags: list[str] | None = None) -> dict:
    """Save a new note. The tier is auto-assigned from the note's tags.

    Notes tagged with PRIVATE_TAG land in Tier 3. Everything else gets a
    default score of 0 (Tier 3) and can be promoted later via upsert_assignment.
    """
    tags = tags or []
    is_private = PRIVATE_TAG in tags or _is_private_title(title, "")
    return _insert_note(
        title=title,
        content=content,
        tags=tags,
        is_private=is_private,
    )


def _insert_note(title: str, content: str, tags: list[str], is_private: bool) -> dict:
    import json
    import uuid

    from postgres_store import chunk_text

    source_id = f"mcp:{uuid.uuid4()}"
    score = 0.0
    tier = compute_tier(score, is_private)
    now = datetime.now(timezone.utc)

    with connect() as connection:
        row = connection.execute(
            """
            INSERT INTO wiki_notes (source_id, title, content, tags, raw_data, created_at)
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)
            RETURNING id, source_id, title, content, tags, created_at
            """,
            (
                source_id,
                title.strip(),
                content.strip(),
                json.dumps(tags),
                json.dumps({"created_via": "tiered_mcp"}),
                now,
            ),
        ).fetchone()

        connection.execute(
            """
            INSERT INTO tier_assignments
                (source_id, tier, score, reviews, sales, is_private, rationale, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id) DO UPDATE SET
                tier = EXCLUDED.tier,
                is_private = EXCLUDED.is_private,
                updated_at = EXCLUDED.updated_at
            """,
            (source_id, tier, score, 0, 0, is_private, "auto: new note", now),
        )

        for index, chunk in enumerate(chunk_text(content)):
            connection.execute(
                "INSERT INTO wiki_chunks (note_id, chunk_index, content) VALUES (%s, %s, %s)",
                (row["id"], index, chunk),
            )
        connection.commit()
    return row


def status() -> dict:
    """Return a small status object describing the running tier server."""
    with connect() as connection:
        counts = connection.execute(
            """
            SELECT COALESCE(a.tier, 3) AS tier, COUNT(*) AS n
            FROM wiki_notes n
            LEFT JOIN tier_assignments a ON a.source_id = n.source_id
            GROUP BY 1
            ORDER BY 1
            """
        ).fetchall()
    counts = {row["tier"]: row["n"] for row in counts}
    return {
        "server_tier": _server_tier(),
        "allowed_tiers": sorted(allowed_tiers()),
        "rows_per_tier": counts,
    }
