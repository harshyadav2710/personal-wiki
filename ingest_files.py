import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from postgres_store import connect, initialize_schema, chunk_text

SUPPORTED_EXTENSIONS = {".md", ".txt", ".json", ".csv"}


def remove_gutenberg_boilerplate(content):
    start_marker = "*** START OF THE PROJECT GUTENBERG EBOOK"
    end_marker = "*** END OF THE PROJECT GUTENBERG EBOOK"
    if start_marker in content and end_marker in content:
        content = content.split(start_marker, 1)[1]
        content = content.split(end_marker, 1)[0]
    return content.strip()


def extract_title(content, fallback):
    match = re.search(r"^[ \t]*Title:[ \t]*([^\r\n]+)", content, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else fallback


def extract_author(content):
    match = re.search(r"^[ \t]*Author:[ \t]*([^\r\n]+)", content, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else ""


def ingest_folder(folder="source_files"):
    initialize_schema()
    files = sorted(
        path for path in Path(folder).rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    ingested = 0
    with connect() as connection:
        for path in files:
            print(f"Processing: {path.name}")
            raw_content = path.read_text(encoding="utf-8")
            source_id = f"file:{path.resolve()}"
            filename_title = path.stem.replace("_", " ").replace("-", " ").title()
            title = extract_title(raw_content, filename_title)
            author = extract_author(raw_content)
            content = remove_gutenberg_boilerplate(raw_content)
            if author:
                content = f"Title: {title}\nAuthor: {author}\n\n{content}"
            raw_data = {"source": str(path), "extension": path.suffix.lower(), "size": len(content)}
            tags = '["myself"]' if "personal" in path.stem.lower() or "about_me" in path.stem.lower() else '["file-ingestion"]'
            note = connection.execute(
                """INSERT INTO wiki_notes (source_id, title, content, tags, raw_data, created_at)
                   VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)
                   ON CONFLICT (source_id) DO UPDATE SET title=EXCLUDED.title, content=EXCLUDED.content,
                   tags=EXCLUDED.tags, raw_data=EXCLUDED.raw_data, created_at=EXCLUDED.created_at
                   RETURNING id""",
                (source_id, title, content, tags, json.dumps(raw_data), datetime.now(timezone.utc)),
            ).fetchone()
            note_id = note["id"]
            connection.execute("DELETE FROM wiki_chunks WHERE note_id = %s", (note_id,))
            for index, chunk in enumerate(chunk_text(content)):
                connection.execute(
                    "INSERT INTO wiki_chunks (note_id, chunk_index, content) VALUES (%s, %s, %s)",
                    (note_id, index, chunk),
                )
            ingested += 1
    print(f"Ingested {ingested} files into PostgreSQL.")
    return ingested

def ingest_single_file(file_path):
    initialize_schema()
    path = Path(file_path)
    if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        print(f"Skipped: {path} (unsupported or not found)")
        return
    with connect() as connection:
        print(f"Processing: {path.name}")
        raw_content = path.read_text(encoding="utf-8")
        source_id = f"file:{path.resolve()}"
        filename_title = path.stem.replace("_", " ").replace("-", " ").title()
        title = extract_title(raw_content, filename_title)
        author = extract_author(raw_content)
        content = remove_gutenberg_boilerplate(raw_content)
        if author:
            content = f"Title: {title}\nAuthor: {author}\n\n{content}"
        raw_data = {"source": str(path), "extension": path.suffix.lower(), "size": len(content)}
        tags = '["myself"]' if "personal" in path.stem.lower() or "about_me" in path.stem.lower() else '["file-ingestion"]'
        note = connection.execute(
            """INSERT INTO wiki_notes (source_id, title, content, tags, raw_data, created_at)
               VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)
               ON CONFLICT (source_id) DO UPDATE SET title=EXCLUDED.title, content=EXCLUDED.content,
               tags=EXCLUDED.tags, raw_data=EXCLUDED.raw_data, created_at=EXCLUDED.created_at
               RETURNING id""",
            (source_id, title, content, tags, json.dumps(raw_data), datetime.now(timezone.utc)),
        ).fetchone()
        note_id = note["id"]
        connection.execute("DELETE FROM wiki_chunks WHERE note_id = %s", (note_id,))
        for index, chunk in enumerate(chunk_text(content)):
            connection.execute(
                "INSERT INTO wiki_chunks (note_id, chunk_index, content) VALUES (%s, %s, %s)",
                (note_id, index, chunk),
            )
    print("Done.")

if __name__ == "__main__":
    ingest_folder(os.getenv("WIKI_SOURCE_DIR", "source_files"))