"""Tiered wrapper around postgres_store.

This module adds tier classification on top of the existing personal-wiki
schema.

Tier access:
    MCP_TIER=1 -> Tier 1 + Tier 2 + Tier 3
    MCP_TIER=2 -> Tier 2 + Tier 3
    MCP_TIER=3 -> Tier 3 only

Search behavior:
    "tier 1" -> return Tier 1 records
    "tier 2" -> return Tier 2 records
    "tier 3" -> return Tier 3 records
    normal query -> search only within allowed tiers
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from postgres_store import PG_DSN, connect  # noqa: F401


load_dotenv(Path(__file__).resolve().parent / ".env")


# ---------------------------------------------------------------------------
# Tier configuration
# ---------------------------------------------------------------------------

TIER_ALLOWLIST = {
    1: {1, 2, 3},
    2: {2, 3},
    3: {3},
}


PRIVATE_TAG = "myself"

PRIVATE_FILENAME_HINTS = (
    "personal",
    "about_me",
)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _is_private_title(title: str, source_id: str) -> bool:
    haystack = f"{title} {source_id}".lower()

    return any(
        hint in haystack
        for hint in PRIVATE_FILENAME_HINTS
    )


def compute_tier(score: float, is_private: bool) -> int:
    """Convert score into Tier 1, Tier 2 or Tier 3."""

    if is_private:
        return 3

    if score >= 80:
        return 1

    if score >= 25:
        return 2

    return 3


def _server_tier() -> int:
    raw = os.getenv("MCP_TIER", "1").strip()

    try:
        value = int(raw)

    except ValueError as error:
        raise RuntimeError(
            f"MCP_TIER must be 1, 2, or 3; got {raw!r}"
        ) from error

    if value not in TIER_ALLOWLIST:
        raise RuntimeError(
            f"MCP_TIER must be 1, 2, or 3; got {value}"
        )

    return value


def allowed_tiers() -> set[int]:
    """Return the tiers the current MCP server can expose."""

    return TIER_ALLOWLIST[_server_tier()]


def _extract_requested_tier(query: str) -> int | None:
    """Detect queries such as 'tier 1', 'tier2', or 'Tier 3 books'."""

    match = re.search(
        r"\btier\s*([123])\b",
        query.lower().strip()
    )

    if not match:
        return None

    return int(match.group(1))


def _is_personal_query(query: str) -> bool:
    """Detect requests asking for the user's personal information."""

    query_lower = query.lower().strip()

    personal_phrases = (
        "myself",
        "about myself",
        "about me",
        "tell me about myself",
        "tell me about me",
        "personal information",
        "personal details",
        "my information",
        "my profile",
        "who am i",
    )

    return any(
        phrase in query_lower
        for phrase in personal_phrases
    )


# ---------------------------------------------------------------------------
# Tier assignment
# ---------------------------------------------------------------------------

def apply_tier_schema() -> None:
    schema_path = (
        Path(__file__).resolve().parent / "tier_schema.sql"
    )

    with connect() as connection:
        connection.execute(
            schema_path.read_text(encoding="utf-8")
        )

        connection.commit()


def upsert_assignment(
    source_id: str,
    reviews: int,
    sales: int,
    is_private: bool = False,
    rationale: str | None = None,
) -> dict:
    """Insert or update a tier assignment."""

    score = (
        float(reviews)
        + 0.1 * float(sales)
    )

    tier = compute_tier(
        score,
        is_private
    )

    with connect() as connection:

        row = connection.execute(
            """
            INSERT INTO tier_assignments
                (
                    source_id,
                    tier,
                    score,
                    reviews,
                    sales,
                    is_private,
                    rationale,
                    updated_at
                )
            VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )

            ON CONFLICT (source_id)
            DO UPDATE SET
                tier = EXCLUDED.tier,
                score = EXCLUDED.score,
                reviews = EXCLUDED.reviews,
                sales = EXCLUDED.sales,
                is_private = EXCLUDED.is_private,
                rationale = EXCLUDED.rationale,
                updated_at = EXCLUDED.updated_at

            RETURNING
                source_id,
                tier,
                score,
                reviews,
                sales,
                is_private,
                rationale
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


def assignment_for(
    source_id: str
) -> dict | None:

    with connect() as connection:

        return connection.execute(
            """
            SELECT *
            FROM tier_assignments
            WHERE source_id = %s
            """,
            (source_id,),
        ).fetchone()


# ---------------------------------------------------------------------------
# Tier-aware search
# ---------------------------------------------------------------------------

def search_tiered(
    query: str,
    limit: int = 5
) -> list[dict]:
    """Search the wiki while respecting the current MCP tier.

    Special queries:
        tier 1 -> Tier 1 records
        tier 2 -> Tier 2 records
        tier 3 -> Tier 3 records
        myself -> personal note

    Normal queries are searched within the allowed tiers.
    """

    allowed = allowed_tiers()

    limit = max(
        1,
        min(int(limit), 1000)
    )

    query = (query or "").strip()

    # ---------------------------------------------------------------
    # 1. Explicit tier search
    # ---------------------------------------------------------------

    requested_tier = _extract_requested_tier(query)

    if requested_tier is not None:

        # Security:
        # A server cannot expose a tier it is not allowed to see.
        if requested_tier not in allowed:
            return []

        with connect() as connection:

            return connection.execute(
                """
                SELECT
                    n.id,
                    n.source_id,
                    n.title,
                    n.content,
                    n.tags,
                    n.created_at,
                    t.tier,
                    t.score,
                    t.rationale,
                    t.is_private
                FROM wiki_notes n
                JOIN tier_assignments t
                    ON t.source_id = n.source_id
                WHERE t.tier = %s
                ORDER BY
                    t.score DESC,
                    n.id ASC
                LIMIT %s
                """,
                (
                    requested_tier,
                    limit,
                ),
            ).fetchall()

    # ---------------------------------------------------------------
    # 2. Personal / myself search
    # ---------------------------------------------------------------

    if _is_personal_query(query):

        tier_placeholders = ", ".join(
            ["%s"] * len(allowed)
        )

        tier_values = tuple(
            sorted(allowed)
        )

        with connect() as connection:

            personal_note = connection.execute(
                f"""
                SELECT
                    n.id,
                    n.source_id,
                    n.title,
                    n.content,
                    n.tags,
                    n.created_at,
                    t.tier,
                    t.score,
                    t.rationale,
                    t.is_private
                FROM wiki_notes n
                JOIN tier_assignments t
                    ON t.source_id = n.source_id
                WHERE
                    t.tier IN ({tier_placeholders})
                    AND
                    (
                        t.is_private = TRUE

                        OR lower(n.title) LIKE '%%personal%%'

                        OR lower(n.title) LIKE '%%about me%%'

                        OR lower(n.title) LIKE '%%about myself%%'

                        OR EXISTS (
                            SELECT 1
                            FROM jsonb_array_elements_text(n.tags) tag
                            WHERE lower(tag) = 'myself'
                        )
                    )
                ORDER BY
                    t.is_private DESC,
                    t.tier ASC,
                    n.id ASC
                LIMIT 1
                """,
                tier_values,
            ).fetchone()

        if personal_note:
            return [personal_note]

        return []

    # ---------------------------------------------------------------
    # 3. Empty query
    # ---------------------------------------------------------------

    if not query:
        return []

    # ---------------------------------------------------------------
    # 4. Normal search
    # ---------------------------------------------------------------

    from postgres_store import search_notes

    # Ask the existing search engine for a larger candidate set.
    candidates = search_notes(
        query,
        limit=limit * 5
    )

    if not candidates:
        return []

    candidate_ids = [
        row["id"]
        for row in candidates
    ]

    with connect() as connection:

        tier_placeholders = ", ".join(
            ["%s"] * len(allowed)
        )

        rows = connection.execute(
            f"""
            SELECT
                n.id,
                n.source_id,
                n.title,
                n.content,
                n.tags,
                n.created_at,
                t.tier,
                t.score,
                t.rationale,
                t.is_private
            FROM wiki_notes n
            JOIN tier_assignments t
                ON t.source_id = n.source_id
            WHERE
                n.id = ANY(%s)
                AND t.tier IN ({tier_placeholders})
            ORDER BY
                t.score DESC,
                n.id ASC
            LIMIT %s
            """,
            (
                candidate_ids,
                *sorted(allowed),
                limit,
            ),
        ).fetchall()

    return rows


# ---------------------------------------------------------------------------
# Read one note
# ---------------------------------------------------------------------------

def get_tiered(
    note_id: int
) -> dict | None:

    allowed = allowed_tiers()

    with connect() as connection:

        tier_placeholders = ", ".join(
            ["%s"] * len(allowed)
        )

        return connection.execute(
            f"""
            SELECT
                n.id,
                n.source_id,
                n.title,
                n.content,
                n.tags,
                n.created_at,
                t.tier,
                t.score,
                t.rationale,
                t.is_private
            FROM wiki_notes n
            JOIN tier_assignments t
                ON t.source_id = n.source_id
            WHERE
                n.id = %s
                AND t.tier IN ({tier_placeholders})
            """,
            (
                note_id,
                *sorted(allowed),
            ),
        ).fetchone()


# ---------------------------------------------------------------------------
# List recent notes
# ---------------------------------------------------------------------------

def list_recent_tiered(
    limit: int = 10
) -> list[dict]:

    allowed = allowed_tiers()

    limit = max(
        1,
        min(int(limit), 50)
    )

    tier_placeholders = ", ".join(
        ["%s"] * len(allowed)
    )

    with connect() as connection:

        return connection.execute(
            f"""
            SELECT
                n.id,
                n.title,
                n.tags,
                n.created_at,
                t.tier,
                t.score,
                t.is_private
            FROM wiki_notes n
            JOIN tier_assignments t
                ON t.source_id = n.source_id
            WHERE
                t.tier IN ({tier_placeholders})
            ORDER BY
                n.created_at DESC
            LIMIT %s
            """,
            (
                *sorted(allowed),
                limit,
            ),
        ).fetchall()


# ---------------------------------------------------------------------------
# Save new tiered note
# ---------------------------------------------------------------------------

def save_tiered(
    title: str,
    content: str,
    tags: list[str] | None = None
) -> dict:

    tags = tags or []

    is_private = (
        PRIVATE_TAG in tags
        or _is_private_title(title, "")
    )

    return _insert_note(
        title=title,
        content=content,
        tags=tags,
        is_private=is_private,
    )


def _insert_note(
    title: str,
    content: str,
    tags: list[str],
    is_private: bool
) -> dict:

    import json

    from postgres_store import chunk_text

    source_id = f"mcp:{uuid.uuid4()}"

    score = 0.0

    tier = compute_tier(
        score,
        is_private
    )

    now = datetime.now(timezone.utc)

    with connect() as connection:

        row = connection.execute(
            """
            INSERT INTO wiki_notes
                (
                    source_id,
                    title,
                    content,
                    tags,
                    raw_data,
                    created_at
                )
            VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s::jsonb,
                    %s::jsonb,
                    %s
                )
            RETURNING
                id,
                source_id,
                title,
                content,
                tags,
                created_at
            """,
            (
                source_id,
                title.strip(),
                content.strip(),
                json.dumps(tags),
                json.dumps(
                    {
                        "created_via": "tiered_mcp"
                    }
                ),
                now,
            ),
        ).fetchone()

        connection.execute(
            """
            INSERT INTO tier_assignments
                (
                    source_id,
                    tier,
                    score,
                    reviews,
                    sales,
                    is_private,
                    rationale,
                    updated_at
                )
            VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )

            ON CONFLICT (source_id)
            DO UPDATE SET
                tier = EXCLUDED.tier,
                is_private = EXCLUDED.is_private,
                updated_at = EXCLUDED.updated_at
            """,
            (
                source_id,
                tier,
                score,
                0,
                0,
                is_private,
                "auto: new note",
                now,
            ),
        )

        for index, chunk in enumerate(
            chunk_text(content)
        ):

            connection.execute(
                """
                INSERT INTO wiki_chunks
                    (
                        note_id,
                        chunk_index,
                        content
                    )
                VALUES
                    (
                        %s,
                        %s,
                        %s
                    )
                """,
                (
                    row["id"],
                    index,
                    chunk,
                ),
            )

        connection.commit()

    return row


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def status() -> dict:

    with connect() as connection:

        counts = connection.execute(
            """
            SELECT
                COALESCE(t.tier, 3) AS tier,
                COUNT(*) AS n
            FROM wiki_notes n
            LEFT JOIN tier_assignments t
                ON t.source_id = n.source_id
            GROUP BY 1
            ORDER BY 1
            """
        ).fetchall()

    counts = {
        row["tier"]: row["n"]
        for row in counts
    }

    return {
        "server_tier": _server_tier(),
        "allowed_tiers": sorted(
            allowed_tiers()
        ),
        "rows_per_tier": counts,
    }