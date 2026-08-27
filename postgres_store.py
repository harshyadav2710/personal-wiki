import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg import OperationalError
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent / ".env")


PG_DSN = os.getenv(
    "PG_DSN",
    "postgresql://postgres:postgres@localhost:5432/personal_wiki"
)


ALLOWED_TIERS = {
    int(tier.strip())
    for tier in os.getenv("MCP_ALLOWED_TIERS", "1,2,3").split(",")
    if tier.strip().isdigit()
}


def connect():
    try:
        return psycopg.connect(
            PG_DSN,
            row_factory=dict_row,
            connect_timeout=5
        )
    except OperationalError as error:
        raise RuntimeError(
            "Could not connect to PostgreSQL. Check that PostgreSQL is running, "
            "the personal_wiki database exists, and PG_DSN in .env is correct."
        ) from error


def initialize_schema():
    schema_path = Path(__file__).resolve().parent / "schema.sql"

    with connect() as connection:
        connection.execute(
            schema_path.read_text(encoding="utf-8")
        )
        connection.commit()


def chunk_text(text, size=450, overlap=60):
    words = text.split()

    chunks = []

    start = 0

    while start < len(words):
        chunks.append(
            " ".join(words[start:start + size])
        )

        start += size - overlap

    return chunks or [""]


def upsert_note(note):
    source_id = str(note["_id"])

    raw_data = {
        key: str(value) if key == "_id" else value
        for key, value in note.items()
    }

    with connect() as connection:

        row = connection.execute(
            """
            INSERT INTO wiki_notes
                (source_id, title, content, tags, raw_data, created_at)
            VALUES
                (%s, %s, %s, %s::jsonb, %s::jsonb, %s)

            ON CONFLICT (source_id)
            DO UPDATE SET
                title = EXCLUDED.title,
                content = EXCLUDED.content,
                tags = EXCLUDED.tags,
                raw_data = EXCLUDED.raw_data,
                created_at = EXCLUDED.created_at

            RETURNING id
            """,
            (
                source_id,
                note.get("title", "Untitled note"),
                note.get("content", ""),
                json.dumps(
                    note.get("tags", []),
                    default=str
                ),
                json.dumps(
                    raw_data,
                    default=str
                ),
                note.get("created_at"),
            ),
        ).fetchone()

        connection.execute(
            "DELETE FROM wiki_chunks WHERE note_id = %s",
            (row["id"],)
        )

        for index, content in enumerate(
            chunk_text(note.get("content", ""))
        ):
            connection.execute(
                """
                INSERT INTO wiki_chunks
                    (note_id, chunk_index, content)
                VALUES
                    (%s, %s, %s)
                """,
                (
                    row["id"],
                    index,
                    content
                ),
            )

        connection.commit()


def search_notes(query, limit=5):

    stop_words = {
        "what",
        "when",
        "where",
        "which",
        "who",
        "how",
        "tell",
        "about",
        "my",
        "me",
        "the",
        "are",
        "is",
        "do",
        "have",
        "i",
        "delivered",
        "deliver",
        "gave",
        "give",
        "said",
        "say",
        "show",
        "list",
        "find",
        "get",
        "please",
        "all",
        "books",
        "book",
        "titles",
        "title",
        "where"
    }

    query_lower = query.lower().strip()

    tier_match = re.search(
        r"\btier\s*(\d+)\b",
        query_lower
    )

    requested_tier = None

    if tier_match:
        requested_tier = int(
            tier_match.group(1)
        )

    personal_query = any(
        phrase in query_lower
        for phrase in [
            "about myself",
            "about me",
            "tell me about myself",
            "tell me about me",
            "myself",
            "personal information",
            "personal details",
            "my information",
            "my profile",
            "who am i"
        ]
    )

    limit = max(
        1,
        min(int(limit), 1000)
    )

    if not ALLOWED_TIERS:
        return []

    tier_placeholders = ", ".join(
        ["%s"] * len(ALLOWED_TIERS)
    )

    tier_values = tuple(
        sorted(ALLOWED_TIERS)
    )

    with connect() as connection:

        if requested_tier is not None:

            if requested_tier not in ALLOWED_TIERS:
                return []

            tier_results = connection.execute(
                """
                SELECT
                    n.id,
                    n.title,
                    n.tags,
                    '' AS content,
                    n.created_at,
                    t.tier,
                    t.score,
                    t.rationale
                FROM wiki_notes n
                JOIN tier_assignments t
                    ON t.source_id = n.source_id
                WHERE t.tier = %s
                ORDER BY n.title ASC
                LIMIT %s
                """,
                (
                    requested_tier,
                    limit
                ),
            ).fetchall()

            return tier_results

        if personal_query:

            personal_note = connection.execute(
                f"""
                SELECT
                    n.id,
                    n.title,
                    n.tags,
                    n.content,
                    n.created_at,
                    t.tier,
                    t.score,
                    t.rationale
                FROM wiki_notes n
                JOIN tier_assignments t
                    ON t.source_id = n.source_id
                WHERE
                    t.tier IN ({tier_placeholders})
                    AND
                    (
                        lower(n.title) LIKE '%personal%'
                        OR lower(n.title) LIKE '%about me%'
                        OR lower(n.title) LIKE '%about myself%'
                        OR EXISTS (
                            SELECT 1
                            FROM jsonb_array_elements_text(n.tags) tag
                            WHERE lower(tag) = 'myself'
                        )
                    )
                ORDER BY
                    CASE
                        WHEN lower(n.title) LIKE '%personal about me%'
                        THEN 0
                        WHEN lower(n.title) LIKE '%about me%'
                        THEN 1
                        ELSE 2
                    END,
                    t.tier ASC,
                    n.id ASC
                LIMIT 1
                """,
                tier_values,
            ).fetchone()

            if personal_note:
                return [personal_note]

        words = [
            word
            for word in re.findall(
                r"[a-zA-Z0-9]+",
                query_lower
            )
            if len(word) > 2
            and word not in stop_words
        ]

        if not words:
            return []

        title_conditions = " OR ".join(
            "lower(n.title) LIKE %s"
            for _ in words
        )

        title_score_conditions = " + ".join(
            """
            CASE
                WHEN lower(n.title) LIKE %s
                THEN 1
                ELSE 0
            END
            """
            for _ in words
        )

        title_matches = connection.execute(
            f"""
            SELECT
                n.id,
                n.title,
                n.tags,
                n.content,
                n.created_at,
                t.tier,
                t.score,
                t.rationale,
                ({title_score_conditions}) AS title_score
            FROM wiki_notes n
            JOIN tier_assignments t
                ON t.source_id = n.source_id
            WHERE
                t.tier IN ({tier_placeholders})
                AND
                ({title_conditions})
            ORDER BY
                title_score DESC,
                n.id
            LIMIT %s
            """,
            (
                tuple(
                    f"%{word}%"
                    for word in words
                )
                +
                tier_values
                +
                tuple(
                    f"%{word}%"
                    for word in words
                )
                +
                (limit,)
            ),
        ).fetchall()

        if title_matches:
            return title_matches

        tag_conditions = " OR ".join(
            """
            EXISTS (
                SELECT 1
                FROM jsonb_array_elements_text(n.tags) tag
                WHERE lower(tag) LIKE %s
            )
            """
            for _ in words
        )

        tag_matches = connection.execute(
            f"""
            SELECT
                n.id,
                n.title,
                n.tags,
                n.content,
                n.created_at,
                t.tier,
                t.score,
                t.rationale
            FROM wiki_notes n
            JOIN tier_assignments t
                ON t.source_id = n.source_id
            WHERE
                t.tier IN ({tier_placeholders})
                AND
                ({tag_conditions})
            ORDER BY
                n.id
            LIMIT %s
            """,
            (
                tier_values
                +
                tuple(
                    f"%{word}%"
                    for word in words
                )
                +
                (limit,)
            ),
        ).fetchall()

        if tag_matches:
            return tag_matches

        chunk_conditions = " OR ".join(
            "lower(c.content) LIKE %s"
            for _ in words
        )

        chunk_matches = connection.execute(
            f"""
            SELECT
                n.id,
                n.title,
                n.tags,
                c.content,
                t.tier,
                t.score,
                t.rationale
            FROM wiki_chunks c
            JOIN wiki_notes n
                ON n.id = c.note_id
            JOIN tier_assignments t
                ON t.source_id = n.source_id
            WHERE
                t.tier IN ({tier_placeholders})
                AND
                ({chunk_conditions})
            ORDER BY
                n.id,
                c.chunk_index
            LIMIT %s
            """,
            (
                tier_values
                +
                tuple(
                    f"%{word}%"
                    for word in words
                )
                +
                (limit,)
            ),
        ).fetchall()

        if chunk_matches:
            return chunk_matches

        terms = " ".join(words)

        return connection.execute(
            f"""
            SELECT
                n.id,
                n.title,
                n.tags,
                c.content,
                t.tier,
                t.score,
                t.rationale
            FROM wiki_chunks c
            JOIN wiki_notes n
                ON n.id = c.note_id
            JOIN tier_assignments t
                ON t.source_id = n.source_id
            WHERE
                t.tier IN ({tier_placeholders})
                AND
                to_tsvector('simple', c.content)
                    @@ plainto_tsquery('simple', %s)
            ORDER BY
                ts_rank(
                    to_tsvector('simple', c.content),
                    plainto_tsquery('simple', %s)
                ) DESC
            LIMIT %s
            """,
            (
                tier_values
                +
                (
                    terms,
                    terms,
                    limit
                )
            ),
        ).fetchall()


def list_recent_notes(limit=10):

    with connect() as connection:

        return connection.execute(
            """
            SELECT
                id,
                title,
                content,
                tags,
                created_at
            FROM wiki_notes
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,)
        ).fetchall()


def get_note(note_id):

    with connect() as connection:

        return connection.execute(
            """
            SELECT
                id,
                title,
                content,
                tags,
                created_at
            FROM wiki_notes
            WHERE id = %s
            """,
            (note_id,)
        ).fetchone()


def save_note(title, content, tags=None):

    tags = tags or []

    created_at = datetime.now(timezone.utc)

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
                title,
                content,
                tags,
                created_at
            """,
            (
                f"mcp:{uuid.uuid4()}",
                title.strip(),
                content.strip(),
                json.dumps(tags),
                json.dumps({}),
                created_at
            ),
        ).fetchone()

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
                    chunk
                ),
            )

        connection.commit()

    return row