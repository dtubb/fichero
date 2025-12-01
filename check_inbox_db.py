#!/usr/bin/env python3
"""
Simple script to check inbox collections in the database.
"""

import sqlite3
import json
import os

# Find the database
db_paths = [
    os.path.expanduser("~/Library/Application Support/Fichero/library.db"),
    os.path.expanduser("~/.fichero/library.db"),
    "./library.db",
]

db_path = None
for path in db_paths:
    if os.path.exists(path):
        db_path = path
        break

if not db_path:
    print("ERROR: Could not find library.db")
    print("Tried paths:")
    for path in db_paths:
        print(f"  - {path}")
    exit(1)

print(f"Database: {db_path}")
print("=" * 60)

with sqlite3.connect(db_path) as conn:
    cursor = conn.cursor()

    # Get all collections
    cursor.execute("SELECT id, name, type, metadata FROM collections")
    collections = cursor.fetchall()

    print(f"\nTotal collections: {len(collections)}")
    print("-" * 60)

    inbox_count = 0
    for row in collections:
        col_id, name, col_type, metadata_str = row

        # Parse metadata
        metadata = {}
        if metadata_str:
            try:
                metadata = json.loads(metadata_str)
            except:
                pass

        # Check if inbox
        is_inbox = metadata.get('is_inbox', False)

        if is_inbox:
            inbox_count += 1
            print(f"\n[INBOX #{inbox_count}]")
            print(f"  Name: {name}")
            print(f"  ID: {col_id}")
            print(f"  Type: {col_type}")
            print(f"  Metadata: {metadata}")
        else:
            print(f"\n[Collection]")
            print(f"  Name: {name}")
            print(f"  ID: {col_id}")
            print(f"  Type: {col_type}")
            if metadata:
                print(f"  Metadata: {metadata}")

    print("\n" + "=" * 60)
    print(f"SUMMARY: Found {inbox_count} inbox collection(s)")
    print("=" * 60)
