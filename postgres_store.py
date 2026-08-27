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
PG_DSN = os.getenv("PG_DSN", "postgresql://postgres:postgres@localhost:5432/personal_wiki")
ALLOWED_TIERS = {
    int(tier.strip())
    for tier in os.getenv("MCP_ALLOWED_TIERS", "1,2,3").split(",")
    if tier.strip().isdigit()
}


def connect():
    try:
        return psycopg.connect(PG_DSN, row_factory=dict_row, connect_timeout=5)
    except OperationalError as error:
        raise RuntimeError(
            "Could not connect to PostgreSQL. Check that PostgreSQL is running, "
            "the personal_wiki database exists, and PG_DSN in .env is correct."
        ) from error


def initialize_schema():
    with connect() as connection:
        connection.execute(Path("schema.sql").read_text(encoding="utf-8"))
        connection.commit()


def chunk_text(text, size=450, overlap=60):
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        chunks.append(" ".join(words[start:start + size]))
        start += size - overlap
    return chunks or [""]


def upsert_note(note):
    source_id = str(note["_id"])
    raw_data = {key: str(value) if key == "_id" else value for key, value in note.items()}
    with connect() as connection:
        row = connection.execute(
            """INSERT INTO wiki_notes (source_id, title, content, tags, raw_data, created_at)
               VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)
               ON CONFLICT (source_id) DO UPDATE SET title=EXCLUDED.title, content=EXCLUDED.content,
               tags=EXCLUDED.tags, raw_data=EXCLUDED.raw_data, created_at=EXCLUDED.created_at
               RETURNING id""",
            (source_id, note.get("title", "Untitled note"), note.get("content", ""),
             json.dumps(note.get("tags", []), default=str), json.dumps(raw_data, default=str), note.get("created_at")),
        ).fetchone()
        connection.execute("DELETE FROM wiki_chunks WHERE note_id = %s", (row["id"],))
        for index, content in enumerate(chunk_text(note.get("content", ""))):
            connection.execute("INSERT INTO wiki_chunks (note_id, chunk_index, content) VALUES (%s, %s, %s)", (row["id"], index, content))
        connection.commit()


def search_notes(query, limit=5):
    stop_words = {
        "what", "when", "where", "which", "who", "how", "tell",
        "about", "my", "me", "the", "are", "is", "do", "have",
        "i", "delivered", "deliver", "gave", "give", "said", "say"
    }

    words = [
        word
        for word in re.findall(r"[a-zA-Z0-9]+", query.lower())
        if len(word) > 2 and word not in stop_words
    ]

    terms = " ".join(words)

    if not terms:
        return []

    # Prevent very large MCP responses
    limit = max(1, min(int(limit), 10))

    # Make sure this MCP has at least one allowed tier
    if not ALLOWED_TIERS:
        return []

    tier_placeholders = ", ".join(["%s"] * len(ALLOWED_TIERS))
    tier_values = tuple(sorted(ALLOWED_TIERS))

    with connect() as connection:

        # 1. Search note titles
        title_conditions = " OR ".join(
            "lower(n.title) LIKE %s"
            for _ in words
        )

        title_score_conditions = " + ".join(
            "CASE WHEN lower(n.title) LIKE %s THEN 1 ELSE 0 END"
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
                ({title_score_conditions}) AS title_score
            FROM wiki_notes n
            WHERE
                n.tier IN ({tier_placeholders})
                AND ({title_conditions})
            ORDER BY title_score DESC, n.id
            LIMIT %s
            """,
            tuple(f"%{word}%" for word in words)
            + tier_values
            + tuple(f"%{word}%" for word in words)
            + (limit,),
        ).fetchall()

        if title_matches:
            return title_matches

        # 2. Search chunks by title
        title_matches = connection.execute(
            f"""
            SELECT
                n.id,
                n.title,
                n.tags,
                c.content
            FROM wiki_chunks c
            JOIN wiki_notes n ON n.id = c.note_id
            WHERE
                n.tier IN ({tier_placeholders})
                AND lower(n.title) LIKE %s
            ORDER BY n.id, c.chunk_index
            LIMIT %s
            """,
            tier_values + (f"%{terms}%", limit),
        ).fetchall()

        if title_matches:
            return title_matches

        # 3. Full-text search inside chunks
        return connection.execute(
            f"""
            SELECT
                n.id,
                n.title,
                n.tags,
                c.content
            FROM wiki_chunks c
            JOIN wiki_notes n ON n.id = c.note_id
            WHERE
                n.tier IN ({tier_placeholders})
                AND to_tsvector('simple', c.content)
                    @@ plainto_tsquery('simple', %s)
            ORDER BY
                ts_rank(
                    to_tsvector('simple', c.content),
                    plainto_tsquery('simple', %s)
                ) DESC
            LIMIT %s
            """,
            tier_values + (terms, terms, limit),
        ).fetchall()


def list_recent_notes(limit=10):
    with connect() as connection:
        return connection.execute(
            """SELECT id, title, content, tags, created_at
               FROM wiki_notes ORDER BY created_at DESC LIMIT %s""", (limit,)
        ).fetchall()


def get_note(note_id):
    with connect() as connection:
        return connection.execute(
            "SELECT id, title, content, tags, created_at FROM wiki_notes WHERE id = %s",
            (note_id,),
        ).fetchone()


def save_note(title, content, tags=None):
    tags = tags or []
    created_at = datetime.now(timezone.utc)
    with connect() as connection:
        row = connection.execute(
            """INSERT INTO wiki_notes (source_id, title, content, tags, raw_data, created_at)
               VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)
               RETURNING id, title, content, tags, created_at""",
            (f"mcp:{uuid.uuid4()}", title.strip(), content.strip(), json.dumps(tags), json.dumps({}), created_at),
        ).fetchone()
        for index, chunk in enumerate(chunk_text(content)):
            connection.execute(
                "INSERT INTO wiki_chunks (note_id, chunk_index, content) VALUES (%s, %s, %s)",
                (row["id"], index, chunk),
            )
        connection.commit()
    return row
