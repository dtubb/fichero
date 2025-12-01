#!/usr/bin/env python3
"""
Quick test to verify the optimization is working.
This tests the new get_file_items_by_parent() method.
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero.library.storage import LibraryStorage
from fichero.library.models import Collection, CollectionItem

def test_optimization():
    """Test the optimized get_file_items_by_parent method"""

    # Create storage with default database path
    import os
    db_path = os.path.expanduser("~/Library/Application Support/ca.tubb.fichero/library/library.db")
    storage = LibraryStorage(db_path=db_path)

    # Get all collections
    collections = storage.get_all_collections()

    if not collections:
        print("❌ No collections found in database")
        print("   Process a folder first using the GUI or CLI")
        return False

    print(f"📊 Found {len(collections)} collection(s)")

    # Find the largest collection
    collection = None
    max_items = 0
    for coll in collections:
        items = storage.get_collection_items(collection_id=coll.id)
        if len(items) > max_items:
            max_items = len(items)
            collection = coll

    if not collection:
        collection = collections[0]

    print(f"   Testing with collection: {collection.name}")

    # Get all items to find a folder
    all_items = storage.get_collection_items(collection_id=collection.id)
    print(f"   Total items in collection: {len(all_items)}")

    # Find a folder item with children
    folder_items = [item for item in all_items if item.type == 'folder']

    if not folder_items:
        print("❌ No folder items found")
        return False

    folder_item = folder_items[0]
    print(f"   Testing with folder: {folder_item.name}")

    # Method 1: Old way (get all, filter in Python)
    start_old = time.time()
    old_items = storage.get_collection_items(collection_id=collection.id)
    old_file_items = [
        item for item in old_items
        if item.type == 'file' and item.parent_id == folder_item.id
    ]
    time_old = time.time() - start_old

    # Method 2: New way (database filtering)
    start_new = time.time()
    new_file_items = storage.get_file_items_by_parent(
        collection_id=collection.id,
        parent_id=folder_item.id
    )
    time_new = time.time() - start_new

    print(f"\n📈 Performance Comparison:")
    print(f"   Old method (query all + Python filter):")
    print(f"      - Queried {len(old_items)} items")
    print(f"      - Found {len(old_file_items)} files")
    print(f"      - Time: {time_old*1000:.2f}ms")

    print(f"   New method (database WHERE clause):")
    print(f"      - Queried {len(new_file_items)} items")
    print(f"      - Found {len(new_file_items)} files")
    print(f"      - Time: {time_new*1000:.2f}ms")

    if time_old > 0 and time_new > 0:
        speedup = time_old / time_new
        print(f"   Speedup: {speedup:.1f}x faster")

    # Verify same results
    old_ids = sorted([item.id for item in old_file_items])
    new_ids = sorted([item.id for item in new_file_items])

    if old_ids == new_ids:
        print(f"\n✅ OPTIMIZATION WORKING!")
        print(f"   Both methods return identical results")
        print(f"   New method is {speedup:.1f}x faster")
        return True
    else:
        print(f"\n❌ ERROR: Methods return different results!")
        print(f"   Old method: {len(old_ids)} items")
        print(f"   New method: {len(new_ids)} items")
        return False

if __name__ == "__main__":
    print("🔍 Testing Performance Optimization\n")
    success = test_optimization()
    sys.exit(0 if success else 1)
