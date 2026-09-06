"""Load Gutenberg txt files directly into PostgreSQL"""

import os
from pathlib import Path
import psycopg

# DATABASE CONNECTION - DIRECT
DATABASE_URL = "postgresql://oauth_wiki_db_user:JazS56SdJHeQl15utHUoLZXlmSVBnhRN@dpg-daed221t0dsc739o9g40-a.virginia-postgres.render.com/oauth_wiki_db"

def load_gutenberg_files():
    """Load all .txt files from gutenberg folder into DB"""
    
    GUTENBERG_DIR = "source_files/gutenberg"
    
    # Connect to DB
    try:
        conn = psycopg.connect(DATABASE_URL)
        cursor = conn.cursor()
        print("✅ Connected to database!")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return
    
    txt_files = sorted(Path(GUTENBERG_DIR).glob("*.txt"))
    print(f"Found {len(txt_files)} files to load...\n")
    
    loaded_count = 0
    failed_count = 0
    
    for file_path in txt_files:
        try:
            # Parse filename
            # Format: 00001-The-Title.txt
            filename = file_path.stem  # Remove .txt
            parts = filename.split('-', 1)  # Split on first dash
            
            if len(parts) == 2:
                book_id = parts[0]
                title = parts[1].replace('-', ' ')  # Replace dashes with spaces
            else:
                title = filename
                book_id = "unknown"
            
            # Read content
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()[:3000]  # First 3000 chars (preview)
            
            # Save to DB - INSERT into wiki_notes table
            if content.strip():
                cursor.execute(
                    """
                    INSERT INTO wiki_notes (title, content, tags, tier)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        title,
                        content,
                        ["gutenberg", "literature"],  # tags as array
                        1  # tier 1 (accessible to all)
                    )
                )
                conn.commit()
                print(f"✅ [{book_id}] {title}")
                loaded_count += 1
            
        except Exception as e:
            print(f"❌ Error loading {file_path.name}: {e}")
            failed_count += 1
            conn.rollback()
    
    # Close connection
    cursor.close()
    conn.close()
    
    print(f"\n" + "="*60)
    print(f"✅ Loaded: {loaded_count}")
    print(f"❌ Failed: {failed_count}")
    print(f"Total: {loaded_count + failed_count}")
    print(f"="*60)

if __name__ == "__main__":
    load_gutenberg_files()