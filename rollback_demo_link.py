#!/usr/bin/env python3
"""
Rollback the demo link changes
"""
import sqlite3
from pathlib import Path

# Paths
db_path = Path("/Users/dtubb/Library/Application Support/ca.tubb.fichero/library/library.db")
item_ids = [
    "26c21990-4392-4120-8b82-7904db9101f3",  # _015.JPG
    "43811979-3f27-4e7e-944e-9e6db59a0e7b"   # _016.JPG
]

print("Rolling back demo link changes...")

# Connect to database
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Delete the processing_history records we just created
print("\nDeleting processing_history records...")
cursor.execute("DELETE FROM processing_history WHERE item_id IN (?, ?)", item_ids)
print(f"Deleted {cursor.rowcount} records")

# Set item statuses back to pending
print("\nResetting item statuses to pending...")
cursor.execute("""
    UPDATE collection_items
    SET status = 'pending'
    WHERE id IN (?, ?)
""", item_ids)
print(f"Updated {cursor.rowcount} items back to 'pending'")

# Commit and close
conn.commit()
conn.close()

print("\n✅ Rollback complete - items are back to pending with no processing history")
