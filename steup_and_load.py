"""Assign all books to tiers 1, 2, 3 evenly"""

import psycopg

DATABASE_URL = "postgresql://oauth_wiki_db_user:JazS56SdJHeQl15utHUoLZXlmSVBnhRN@dpg-daed221t0dsc739o9g40-a.virginia-postgres.render.com/oauth_wiki_db"

def assign_tiers():
    try:
        conn = psycopg.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        print("📚 Fetching all books...")
        
        # Get all books without tier assignments
        cursor.execute("""
            SELECT id, source_id, title 
            FROM wiki_notes 
            WHERE source_id NOT IN (SELECT source_id FROM tier_assignments)
            ORDER BY id
        """)
        
        books = cursor.fetchall()
        print(f"Found {len(books)} books without tier assignments\n")
        
        if not books:
            print("✅ All books already have tier assignments!")
            conn.close()
            return
        
        # Assign tiers: distribute evenly across tiers 1, 2, 3
        tier1_count = 0
        tier2_count = 0
        tier3_count = 0
        
        for idx, (book_id, source_id, title) in enumerate(books):
            # Distribute evenly: 1, 2, 3, 1, 2, 3, ...
            tier = (idx % 3) + 1
            
            cursor.execute("""
                INSERT INTO tier_assignments (source_id, tier, score, reviews, sales, is_private)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_id) DO NOTHING
            """, (source_id, tier, 0, 0, 0, False))
            
            if tier == 1:
                tier1_count += 1
                status = "T1"
            elif tier == 2:
                tier2_count += 1
                status = "T2"
            else:
                tier3_count += 1
                status = "T3"
            
            print(f"✅ [{status}] {title}")
        
        conn.commit()
        
        print(f"\n" + "="*60)
        print(f"📊 Tier Distribution:")
        print(f"  Tier 1: {tier1_count} books")
        print(f"  Tier 2: {tier2_count} books")
        print(f"  Tier 3: {tier3_count} books")
        print(f"  Total:  {len(books)} books assigned")
        print(f"="*60)
        
        cursor.close()
        conn.close()
        print("✅ Done!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    assign_tiers()