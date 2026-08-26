CREATE TABLE IF NOT EXISTS wiki_notes (
    id BIGSERIAL PRIMARY KEY,
    source_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS wiki_chunks (
    id BIGSERIAL PRIMARY KEY,
    note_id BIGINT NOT NULL REFERENCES wiki_notes(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(note_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS wiki_chats (
    id BIGSERIAL PRIMARY KEY,
    source_id TEXT UNIQUE,
    message TEXT NOT NULL,
    answer TEXT NOT NULL,
    raw_data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

DROP INDEX IF EXISTS wiki_notes_search_idx;
CREATE INDEX IF NOT EXISTS wiki_chunks_search_idx ON wiki_chunks USING gin (to_tsvector('simple', content));
