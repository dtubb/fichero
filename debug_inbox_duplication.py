#!/usr/bin/env python3
"""
Debug script to check inbox duplication issue.

This script checks:
1. How many inbox collections exist in the database
2. Whether metadata is being stored correctly
3. Whether get_or_create_inbox() finds existing inbox
"""

import sys
import os
import sqlite3
import asyncio

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from fichero.library.library_manager import LibraryManager


async def check_inbox_duplication():
    """Check for inbox duplication in the database."""

    # Initialize library manager
    library_manager = LibraryManager()
    await library_manager.initialize()

    print("=" * 60)
    print("INBOX DUPLICATION DEBUG")
    print("=" * 60)

    # Check database directly
    db_path = library_manager.storage.db_path
    print(f"\n1. Database path: {db_path}")

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Get all collections
        cursor.execute("SELECT id, name, type, metadata FROM collections")
        collections = cursor.fetchall()

        print(f"\n2. Total collections in database: {len(collections)}")

        # Check for inbox collections
        inbox_collections = []
        for row in collections:
            col_id, name, col_type, metadata_str = row
            print(f"\n   Collection: {name} (ID: {col_id}, Type: {col_type})")
            print(f"   Metadata: {metadata_str}")

            # Try to parse metadata
            if metadata_str:
                import json
                try:
                    metadata = json.loads(metadata_str)
                    print(f"   Parsed metadata: {metadata}")
                    if metadata.get('is_inbox'):
                        inbox_collections.append((col_id, name, metadata))
                except Exception as e:
                    print(f"   ERROR parsing metadata: {e}")

        print(f"\n3. Inbox collections found: {len(inbox_collections)}")
        for col_id, name, metadata in inbox_collections:
            print(f"   - {name} (ID: {col_id})")
            print(f"     Metadata: {metadata}")

    # Test get_or_create_inbox()
    print(f"\n4. Testing get_or_create_inbox()...")
    inbox_id = await library_manager.get_or_create_inbox()
    print(f"   Returned inbox ID: {inbox_id}")

    # Check again after get_or_create_inbox()
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM collections WHERE metadata LIKE '%is_inbox%'")
        count = cursor.fetchone()[0]
        print(f"\n5. Inbox collections after get_or_create_inbox(): {count}")

    # Get all collections via library manager
    print(f"\n6. Collections via library_manager.get_all_collections():")
    collections = await library_manager.get_all_collections()
    for collection in collections:
        if collection.metadata.get('is_inbox'):
            print(f"   - {collection.name} (ID: {collection.id})")
            print(f"     Metadata: {collection.metadata}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(check_inbox_duplication())
