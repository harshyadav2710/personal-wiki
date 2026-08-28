-- Tiered MCP support schema. Applied alongside schema.sql.
-- This file is additive only; it does NOT modify any existing table.

CREATE TABLE IF NOT EXISTS tier_assignments (
    source_id      TEXT PRIMARY KEY,
    tier           SMALLINT NOT NULL CHECK (tier IN (1, 2, 3)),
    score          DOUBLE PRECISION NOT NULL DEFAULT 0,
    reviews        INTEGER NOT NULL DEFAULT 0,
    sales          INTEGER NOT NULL DEFAULT 0,
    is_private     BOOLEAN NOT NULL DEFAULT FALSE,
    rationale      TEXT,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS tier_assignments_tier_idx
    ON tier_assignments (tier);

-- View that joins each note to its tier, used by all tiered MCP servers.
-- Application-level enforcement means MCP servers still need to filter by tier,
-- but this view gives a single, auditable place to read tier-aware data.
CREATE OR REPLACE VIEW wiki_notes_tiered AS
SELECT
    n.id,
    n.source_id,
    n.title,
    n.content,
    n.tags,
    n.created_at,
    COALESCE(a.tier, 3)        AS tier,
    COALESCE(a.is_private, FALSE) AS is_private,
    a.score,
    a.reviews,
    a.sales
FROM wiki_notes n
LEFT JOIN tier_assignments a ON a.source_id = n.source_id;


CREATE TABLE IF NOT EXISTS book_categories (
    id BIGSERIAL PRIMARY KEY,

    note_id BIGINT NOT NULL
        REFERENCES wiki_notes(id)
        ON DELETE CASCADE,

    category TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (note_id, category)
);

CREATE INDEX IF NOT EXISTS book_categories_category_idx
    ON book_categories (LOWER(category));

CREATE INDEX IF NOT EXISTS book_categories_note_id_idx
    ON book_categories (note_id);