from tier_store import apply_tier_schema, backfill_book_categories

print("Applying tier schema...")
apply_tier_schema()

print("Backfilling book categories...")
count = backfill_book_categories()

print(f"Done. Added {count} category assignments.")