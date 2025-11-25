#!/usr/bin/env python3
"""
Check the actual database schema
"""

import sys
import sqlite3
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero.library.path_resolver import get_library_path

def check_schema():
    """Check the database schema"""

    # Get database path
    library_path = get_library_path()
    db_path = library_path / "library.db"

    print(f"Database path: {db_path}")
    print(f"Database exists: {db_path.exists()}")

    if not db_path.exists():
        print("Database does not exist!")
        return

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # List all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()

        print(f"\nTables in database: {len(tables)}")
        for table in tables:
            table_name = table[0]
            print(f"\n  Table: {table_name}")

            # Get table schema
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()

            for col in columns:
                col_id, name, type, notnull, default, pk = col
                pk_str = " (PRIMARY KEY)" if pk else ""
                print(f"    - {name}: {type}{pk_str}")

            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            print(f"    Rows: {count}")

if __name__ == "__main__":
    check_schema()