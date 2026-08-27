from __future__ import annotations

import os
from pathlib import Path

from postgres_store import initialize_schema, connect
from tier_classify import classify
from tier_store import apply_tier_schema, upsert_assignment


SUPPORTED_EXTENSIONS = {".md", ".txt", ".json", ".csv"}


def main() -> None:
    # Make sure the base + tier schemas exist.
    initialize_schema()
    apply_tier_schema()

    folder = os.getenv("WIKI_SOURCE_DIR", "source_files")

    # Get only the files currently present in source_files.
    files = sorted(
        path
        for path in Path(folder).rglob("*")
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    print(f"Found {len(files)} files in {folder}. Classifying...")

    tier_counts = {1: 0, 2: 0, 3: 0}
    processed = 0
    skipped = 0

    with connect() as connection:
        for path in files:
            source_id = f"file:{path.resolve()}"

            # Get only the wiki_note belonging to this current file.
            row = connection.execute(
                """
                SELECT id, source_id, title
                FROM wiki_notes
                WHERE source_id = %s
                """,
                (source_id,),
            ).fetchone()

            if not row:
                print(f"Skipped (not found in wiki_notes): {path.name}")
                skipped += 1
                continue

            est = classify(row["title"], row["source_id"])

            assignment = upsert_assignment(
                source_id=row["source_id"],
                reviews=est.reviews,
                sales=est.sales,
                is_private=est.is_private,
                rationale=est.rationale,
            )

            tier_counts[assignment["tier"]] += 1
            processed += 1

            print(
                f"[T{assignment['tier']}] {row['title']!r} "
                f"-> score={assignment['score']:.1f} ({est.rationale})"
            )

    print("\nTier distribution:")
    for tier, count in sorted(tier_counts.items()):
        print(f"  Tier {tier}: {count}")

    print(f"\nProcessed: {processed}")
    print(f"Skipped:   {skipped}")


if __name__ == "__main__":
    main()