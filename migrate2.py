"""
Migration 2: Add UNIQUE(source_url) constraint so upserts use source_url as conflict key.

Run from your local machine (requires DB_HOST and DB_PASSWORD in .env):
  uv run python migrate2.py
"""

import os
import sys
import psycopg2
from dotenv import load_dotenv

load_dotenv(override=True)

DB_HOST = os.getenv("DB_HOST")
DB_PASSWORD = os.getenv("DB_PASSWORD")

if not DB_HOST or not DB_PASSWORD:
    print("ERROR: DB_HOST and DB_PASSWORD must be set in .env")
    sys.exit(1)

conn = psycopg2.connect(
    host=DB_HOST,
    port=5432,
    dbname="postgres",
    user="postgres",
    password=DB_PASSWORD,
    sslmode="require",
    connect_timeout=10,
)
conn.autocommit = True
cur = conn.cursor()

print("Connected.")

# Add UNIQUE constraint on source_url (idempotent)
cur.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'headlines_source_url_key'
              AND conrelid = 'headlines'::regclass
        ) THEN
            ALTER TABLE headlines
                ADD CONSTRAINT headlines_source_url_key UNIQUE (source_url);
            RAISE NOTICE 'UNIQUE(source_url) constraint added';
        ELSE
            RAISE NOTICE 'UNIQUE(source_url) constraint already exists, skipping';
        END IF;
    END $$;
""")

# Verify
cur.execute("""
    SELECT constraint_name, constraint_type
    FROM information_schema.table_constraints
    WHERE table_name = 'headlines'
    ORDER BY constraint_type, constraint_name
""")
print("headlines constraints:", cur.fetchall())

# Check for any rows with NULL source_url (would block the constraint)
cur.execute("SELECT count(*) FROM headlines WHERE source_url IS NULL")
null_count = cur.fetchone()[0]
if null_count > 0:
    print(f"WARNING: {null_count} rows have NULL source_url — fix these before the constraint applies to new rows.")
else:
    print("All rows have source_url set.")

conn.close()
print("Migration 2 complete.")
