#!/usr/bin/env python3
"""
Check for duplicate Inbox collections in the library database
"""

import sqlite3
from pathlib import Path
import json
from datetime import datetime


def check_inbox_duplicates():
    """Check for duplicate inbox collections"""

    # Find library database
    home = Path.home()
    possible_paths = [
        home / "Library" / "Application Support" / "com.fichero" / "library.db",
        home / "Library" / "Application Support" / "fichero" / "library.db",
        Path("library.db"),
    ]

    db_path = None
    for path in possible_paths:
        if path.exists():
            db_path = path
            break

    if not db_path:
        print("❌ Could not find library database")
        print(f"Searched locations:")
        for path in possible_paths:
            print(f"  - {path}")
        return

    print(f"✅ Found library database: {db_path}")
    print()

    # Connect to database
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Get all collections
    cursor.execute("SELECT id, name, type, metadata, created_at, sort_order FROM collections")
    collections = cursor.fetchall()

    print(f"Total collections: {len(collections)}")
    print()

    # Find inbox collections
    inbox_collections = []
    for row in collections:
        col_id, name, col_type, metadata_json, created_at, sort_order = row
        metadata = json.loads(metadata_json) if metadata_json else {}

        # Check by metadata (correct way)
        if metadata.get('is_inbox'):
            inbox_collections.append(('metadata', row, metadata))
        # Check by name only (incorrect way)
        elif name == "Inbox":
            inbox_collections.append(('name_only', row, metadata))

    if not inbox_collections:
        print("⚠️  No Inbox collections found!")
    elif len(inbox_collections) == 1:
        method, row, metadata = inbox_collections[0]
        col_id, name, col_type, _, created_at, sort_order = row
        print(f"✅ Single Inbox collection found ({method}):")
        print(f"   ID: {col_id}")
        print(f"   Name: {name}")
        print(f"   Type: {col_type}")
        print(f"   Sort Order: {sort_order}")
        print(f"   Metadata: {metadata}")
    else:
        print(f"❌ DUPLICATE INBOX FOUND! ({len(inbox_collections)} inboxes)")
        print()
        for i, (method, row, metadata) in enumerate(inbox_collections, 1):
            col_id, name, col_type, _, created_at, sort_order = row
            print(f"Inbox #{i} (detected by {method}):")
            print(f"  ID: {col_id}")
            print(f"  Name: {name}")
            print(f"  Type: {col_type}")
            print(f"  Created: {created_at}")
            print(f"  Sort Order: {sort_order}")
            print(f"  Metadata: {metadata}")
            print()

    # List all collections
    print("\nAll collections:")
    for row in collections:
        col_id, name, col_type, metadata_json, created_at, sort_order = row
        metadata = json.loads(metadata_json) if metadata_json else {}
        is_inbox_meta = "📥" if metadata.get('is_inbox') else "  "
        is_inbox_name = "📧" if name == "Inbox" else "  "
        print(f"{is_inbox_meta} {is_inbox_name} {name:<20} (type={col_type}, sort={sort_order}, id={col_id[:8]}...)")

    conn.close()


if __name__ == "__main__":
    check_inbox_duplicates()
