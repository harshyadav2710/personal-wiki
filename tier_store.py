from __future__ import annotations
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from postgres_store import PG_DSN, connect  # noqa: F401
load_dotenv(Path(__file__).resolve().parent / ".env")
TIER_ALLOWLIST = {
    1: {1, 2, 3},
    2: {2, 3},
    3: {3},
}
PRIVATE_TAG = "myself"
PRIVATE_FILENAME_HINTS = ("personal", "about_me")
BOOK_CATEGORIES = {
    "romance",
    "love",
    "emotional",
    "mystery",
    "thriller",
    "fantasy",
    "science fiction",
    "horror",
    "adventure",
    "classic",
    "poetry",
    "history",
    "biography",
    "self-help",
    "philosophy",
    "drama",
    "comedy",
    "children",
    "politics",
    "science",
    "gothic",
    "war",
    "crime",
    "western",
}
def _is_private_title(title: str, source_id: str) -> bool:
    haystack = f"{title} {source_id}".lower()
    return any(hint in haystack for hint in PRIVATE_FILENAME_HINTS)
def compute_tier(score: float, is_private: bool) -> int:
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
        raise RuntimeError(f"MCP_TIER must be 1, 2, or 3; got {raw!r}") from error
    if value not in TIER_ALLOWLIST:
        raise RuntimeError(f"MCP_TIER must be 1, 2, or 3; got {value}")
    return value
def allowed_tiers() -> set[int]:
    return TIER_ALLOWLIST[_server_tier()]
def _extract_requested_tier(query: str) -> int | None:
    match = re.search(r"\btier\s*([123])\b", query.lower().strip())
    if not match:
        return None
    return int(match.group(1))
def _is_personal_query(query: str) -> bool:
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
    return any(phrase in query_lower for phrase in personal_phrases)
def detect_book_categories(title: str, content: str) -> list[str]:
    text = f"{title} {content}".lower()
    detected = []
    category_keywords = {
        "romance": ["romance", "romantic", "love story"],
        "love": ["love", "lovers", "relationship"],
        "emotional": ["emotional", "emotion", "heartbreak", "grief"],
        "mystery": ["mystery", "mysterious", "detective"],
        "thriller": ["thriller", "suspense", "psychological"],
        "fantasy": ["fantasy", "magic", "wizard", "witch", "dragon"],
        "science fiction": ["science fiction", "sci-fi", "space", "future"],
        "horror": ["horror", "ghost", "haunted", "vampire"],
        "adventure": ["adventure", "journey", "exploration"],
        "classic": ["classic", "classical literature"],
        "poetry": ["poetry", "poem", "poems", "verse"],
        "history": ["history", "historical", "empire", "war"],
        "biography": ["biography", "autobiography", "memoir"],
        "self-help": ["self-help", "self help", "personal development"],
        "philosophy": ["philosophy", "philosophical"],
        "drama": ["drama", "dramatic"],
        "comedy": ["comedy", "humor", "humour", "funny"],
        "children": ["children", "childrens", "kids", "fairy tale"],
        "politics": ["politics", "political", "government"],
        "science": ["science", "scientific", "physics", "chemistry", "biology"],
        "gothic": ["gothic"],
        "war": ["war", "soldier", "battle", "military"],
        "crime": ["crime", "criminal", "murder", "police"],
        "western": ["western", "cowboy", "wild west"],
    }
    for category, keywords in category_keywords.items():
        if any(keyword in text for keyword in keywords):
            detected.append(category)
    return detected
def apply_tier_schema() -> None:
    schema_path = Path(__file__).resolve().parent / "tier_schema.sql"
    with connect() as connection:
        connection.execute(schema_path.read_text(encoding="utf-8"))
        connection.commit()
def apply_book_categories() -> None:
    with connect() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS book_categories (
                id BIGSERIAL PRIMARY KEY,
                note_id BIGINT NOT NULL REFERENCES wiki_notes(id) ON DELETE CASCADE,
                category TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (note_id, category)
            )
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS book_categories_category_idx
            ON book_categories (LOWER(category))
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS book_categories_note_id_idx
            ON book_categories (note_id)
        """)
        connection.commit()
def upsert_assignment(source_id: str, reviews: int, sales: int, is_private: bool = False, rationale: str | None = None) -> dict:
    score = float(reviews) + 0.1 * float(sales)
    tier = compute_tier(score, is_private)
    with connect() as connection:
        row = connection.execute("""
            INSERT INTO tier_assignments
                (source_id, tier, score, reviews, sales, is_private, rationale, updated_at)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id)
            DO UPDATE SET
                tier = EXCLUDED.tier,
                score = EXCLUDED.score,
                reviews = EXCLUDED.reviews,
                sales = EXCLUDED.sales,
                is_private = EXCLUDED.is_private,
                rationale = EXCLUDED.rationale,
                updated_at = EXCLUDED.updated_at
            RETURNING source_id, tier, score, reviews, sales, is_private, rationale
        """, (
            source_id,
            tier,
            score,
            reviews,
            sales,
            is_private,
            rationale,
            datetime.now(timezone.utc),
        )).fetchone()
        connection.commit()
    return row
def assignment_for(source_id: str) -> dict | None:
    with connect() as connection:
        return connection.execute("""
            SELECT *
            FROM tier_assignments
            WHERE source_id = %s
        """, (source_id,)).fetchone()
def search_tiered(query: str, limit: int = 100) -> list[dict]:
    allowed = allowed_tiers()
    limit = max(1, min(int(limit), 1000))
    query = (query or "").strip()
    requested_tier = _extract_requested_tier(query)
    if requested_tier is not None:
        if requested_tier not in allowed:
            return []
        with connect() as connection:
            return connection.execute("""
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
                JOIN tier_assignments t ON t.source_id = n.source_id
                WHERE t.tier = %s
                ORDER BY t.score DESC, n.id ASC
                LIMIT %s
            """, (requested_tier, limit)).fetchall()
    if _is_personal_query(query):
        tier_placeholders = ", ".join(["%s"] * len(allowed))
        tier_values = tuple(sorted(allowed))
        with connect() as connection:
            personal_note = connection.execute(f"""
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
                JOIN tier_assignments t ON t.source_id = n.source_id
                WHERE t.tier IN ({tier_placeholders})
                AND (
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
                ORDER BY t.is_private DESC, t.tier ASC, n.id ASC
                LIMIT 1
            """, tier_values).fetchone()
        return [personal_note] if personal_note else []
    if not query:
        return []
    from postgres_store import search_notes
    candidates = search_notes(query, limit=limit * 5)
    if not candidates:
        return []
    candidate_ids = [row["id"] for row in candidates]
    with connect() as connection:
        tier_placeholders = ", ".join(["%s"] * len(allowed))
        return connection.execute(f"""
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
            JOIN tier_assignments t ON t.source_id = n.source_id
            WHERE n.id = ANY(%s)
            AND t.tier IN ({tier_placeholders})
            ORDER BY t.score DESC, n.id ASC
            LIMIT %s
        """, (
            candidate_ids,
            *sorted(allowed),
            limit,
        )).fetchall()
def get_tiered(note_id: int) -> dict | None:
    allowed = allowed_tiers()
    tier_placeholders = ", ".join(["%s"] * len(allowed))
    with connect() as connection:
        return connection.execute(f"""
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
            JOIN tier_assignments t ON t.source_id = n.source_id
            WHERE n.id = %s
            AND t.tier IN ({tier_placeholders})
        """, (
            note_id,
            *sorted(allowed),
        )).fetchone()
def list_recent_tiered(limit: int = 10) -> list[dict]:
    allowed = allowed_tiers()
    limit = max(1, min(int(limit), 50))
    tier_placeholders = ", ".join(["%s"] * len(allowed))
    with connect() as connection:
        return connection.execute(f"""
            SELECT
                n.id,
                n.title,
                n.tags,
                n.created_at,
                t.tier,
                t.score,
                t.is_private
            FROM wiki_notes n
            JOIN tier_assignments t ON t.source_id = n.source_id
            WHERE t.tier IN ({tier_placeholders})
            ORDER BY n.created_at DESC
            LIMIT %s
        """, (
            *sorted(allowed),
            limit,
        )).fetchall()
def save_tiered(title: str, content: str, tags: list[str] | None = None) -> dict:
    tags = tags or []
    is_private = PRIVATE_TAG in tags or _is_private_title(title, "")
    return _insert_note(title=title, content=content, tags=tags, is_private=is_private)
def _insert_note(title: str, content: str, tags: list[str], is_private: bool) -> dict:
    import json
    from postgres_store import chunk_text
    source_id = f"mcp:{uuid.uuid4()}"
    score = 0.0
    tier = compute_tier(score, is_private)
    now = datetime.now(timezone.utc)
    categories = detect_book_categories(title, content)
    with connect() as connection:
        row = connection.execute("""
            INSERT INTO wiki_notes
                (source_id, title, content, tags, raw_data, created_at)
            VALUES
                (%s, %s, %s, %s::jsonb, %s::jsonb, %s)
            RETURNING id, source_id, title, content, tags, created_at
        """, (
            source_id,
            title.strip(),
            content.strip(),
            json.dumps(tags),
            json.dumps({"created_via": "tiered_mcp"}),
            now,
        )).fetchone()
        connection.execute("""
            INSERT INTO tier_assignments
                (source_id, tier, score, reviews, sales, is_private, rationale, updated_at)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id)
            DO UPDATE SET
                tier = EXCLUDED.tier,
                is_private = EXCLUDED.is_private,
                updated_at = EXCLUDED.updated_at
        """, (
            source_id,
            tier,
            score,
            0,
            0,
            is_private,
            "auto: new note",
            now,
        ))
        for category in categories:
            connection.execute("""
                INSERT INTO book_categories (note_id, category)
                VALUES (%s, %s)
                ON CONFLICT (note_id, category) DO NOTHING
            """, (row["id"], category))
        for index, chunk in enumerate(chunk_text(content)):
            connection.execute("""
                INSERT INTO wiki_chunks
                    (note_id, chunk_index, content)
                VALUES
                    (%s, %s, %s)
            """, (row["id"], index, chunk))
        connection.commit()
    return row
def status() -> dict:
    with connect() as connection:
        counts = connection.execute("""
            SELECT
                COALESCE(t.tier, 3) AS tier,
                COUNT(*) AS n
            FROM wiki_notes n
            LEFT JOIN tier_assignments t ON t.source_id = n.source_id
            GROUP BY 1
            ORDER BY 1
        """).fetchall()
    counts = {row["tier"]: row["n"] for row in counts}
    return {
        "server_tier": _server_tier(),
        "allowed_tiers": sorted(allowed_tiers()),
        "rows_per_tier": counts,
    }
def list_books_by_tier(tier: int, page: int = 1, page_size: int = 20) -> list[dict]:
    if tier not in allowed_tiers():
        return []
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 100))
    offset = (page - 1) * page_size
    with connect() as connection:
        return connection.execute("""
            SELECT
                n.id,
                n.title,
                t.tier,
                t.score,
                COALESCE(
                    ARRAY_AGG(bc.category ORDER BY bc.category)
                    FILTER (WHERE bc.category IS NOT NULL),
                    ARRAY[]::TEXT[]
                ) AS categories
            FROM wiki_notes n
            JOIN tier_assignments t ON t.source_id = n.source_id
            LEFT JOIN book_categories bc ON bc.note_id = n.id
            WHERE t.tier = %s
            GROUP BY n.id, n.title, t.tier, t.score
            ORDER BY t.score DESC, n.title ASC
            LIMIT %s
            OFFSET %s
        """, (
            tier,
            page_size,
            offset,
        )).fetchall()
def search_books(query: str, page: int = 1, page_size: int = 20) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 100))
    offset = (page - 1) * page_size
    allowed = allowed_tiers()
    tier_placeholders = ", ".join(["%s"] * len(allowed))
    with connect() as connection:
        return connection.execute(f"""
            SELECT
                n.id,
                n.title,
                t.tier,
                t.score,
                COALESCE(
                    ARRAY_AGG(bc.category ORDER BY bc.category)
                    FILTER (WHERE bc.category IS NOT NULL),
                    ARRAY[]::TEXT[]
                ) AS categories
            FROM wiki_notes n
            JOIN tier_assignments t ON t.source_id = n.source_id
            LEFT JOIN book_categories bc ON bc.note_id = n.id
            WHERE t.tier IN ({tier_placeholders})
            AND (
                LOWER(n.title) LIKE LOWER(%s)
                OR LOWER(n.content) LIKE LOWER(%s)
                OR EXISTS (
                    SELECT 1
                    FROM book_categories bc2
                    WHERE bc2.note_id = n.id
                    AND LOWER(bc2.category) LIKE LOWER(%s)
                )
            )
            GROUP BY n.id, n.title, t.tier, t.score
            ORDER BY t.score DESC, n.title ASC
            LIMIT %s
            OFFSET %s
        """, (
            *sorted(allowed),
            f"%{query}%",
            f"%{query}%",
            f"%{query}%",
            page_size,
            offset,
        )).fetchall()
def list_books_by_category(category: str, page: int = 1, page_size: int = 20) -> list[dict]:
    category = (category or "").strip().lower()
    if not category:
        return []
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 100))
    offset = (page - 1) * page_size
    allowed = allowed_tiers()
    tier_placeholders = ", ".join(["%s"] * len(allowed))
    with connect() as connection:
        return connection.execute(f"""
            SELECT
                n.id,
                n.title,
                t.tier,
                t.score,
                COALESCE(
                    ARRAY_AGG(bc.category ORDER BY bc.category)
                    FILTER (WHERE bc.category IS NOT NULL),
                    ARRAY[]::TEXT[]
                ) AS categories
            FROM wiki_notes n
            JOIN tier_assignments t ON t.source_id = n.source_id
            JOIN book_categories bc ON bc.note_id = n.id
            WHERE t.tier IN ({tier_placeholders})
            AND LOWER(bc.category) = LOWER(%s)
            GROUP BY n.id, n.title, t.tier, t.score
            ORDER BY t.score DESC, n.title ASC
            LIMIT %s
            OFFSET %s
        """, (
            *sorted(allowed),
            category,
            page_size,
            offset,
        )).fetchall()
def list_categories() -> list[dict]:
    allowed = allowed_tiers()
    tier_placeholders = ", ".join(["%s"] * len(allowed))
    with connect() as connection:
        return connection.execute(f"""
            SELECT
                bc.category,
                COUNT(DISTINCT n.id) AS book_count
            FROM book_categories bc
            JOIN wiki_notes n ON n.id = bc.note_id
            JOIN tier_assignments t ON t.source_id = n.source_id
            WHERE t.tier IN ({tier_placeholders})
            GROUP BY bc.category
            ORDER BY book_count DESC, bc.category ASC
        """, tuple(sorted(allowed))).fetchall()
def backfill_book_categories() -> int:
    total = 0
    with connect() as connection:
        rows = connection.execute("""
            SELECT id, title, content
            FROM wiki_notes
            ORDER BY id ASC
        """).fetchall()
        for row in rows:
            categories = detect_book_categories(
                row["title"],
                row["content"],
            )
            for category in categories:
                connection.execute("""
                    INSERT INTO book_categories (note_id, category)
                    VALUES (%s, %s)
                    ON CONFLICT (note_id, category) DO NOTHING
                """, (row["id"], category))
                total += 1
        connection.commit()
    return total