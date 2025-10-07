#!/usr/bin/env python3
"""
Backend test to verify item_id lookup is working for external collections
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from fichero.library.storage import LibraryStorage
from fichero.library.library_manager import LibraryManager

def test_item_id_lookup():
    """Test that files get the correct parent folder item_id"""

    # Initialize library
    storage = LibraryStorage()
    library_manager = LibraryManager(storage=storage)

    # Find the Tiny Test collection
    collections = storage.get_all_collections()
    tiny_test = None
    for coll in collections:
        if "Tiny" in coll.name:
            tiny_test = coll
            break

    if not tiny_test:
        print("❌ Tiny Test collection not found")
        return

    print(f"✅ Found collection: {tiny_test.name} (ID: {tiny_test.id})")
    print(f"   Source path: {tiny_test.source_path}")

    # Get collection items (should have the root folder)
    items = storage.get_collection_items(tiny_test.id)
    print(f"\n📊 Collection has {len(items)} items:")
    for item in items:
        print(f"   - {item.name} (ID: {item.id}, Type: {item.type})")
        print(f"     Source: {item.source_path}")

    if not items:
        print("\n❌ No items found - need to add folder to collection first")
        return

    # Get the folder item
    folder_item = items[0]
    print(f"\n📊 Using folder item: {folder_item.name} (ID: {folder_item.id})")

    # Check processing history for this item
    history = storage.get_processing_history(folder_item.id)
    print(f"\n📊 Processing history for folder:")
    if history:
        for result in history:
            print(f"   - Status: {result.status}")
            print(f"     Output paths: {result.output_paths}")
    else:
        print("   No processing history found")

    # Now simulate what happens in library_service._get_filesystem_structure
    print(f"\n📊 Simulating _get_filesystem_structure logic:")

    base_path = Path(tiny_test.source_path)
    subfolder_name = "1931 Antonio Asprilla pide que se haga efectiva una multa a M.C. Marshall y Manuel A. Peña; Istmina"
    current_path = base_path / subfolder_name

    print(f"   Base path: {base_path}")
    print(f"   Current path (subfolder): {current_path}")

    # Check if path matching works
    item_source = str(Path(folder_item.source_path).absolute())
    current_path_str = str(current_path.absolute())

    print(f"\n📊 Path matching:")
    print(f"   Item source (absolute): {item_source}")
    print(f"   Current path (absolute): {current_path_str}")
    print(f"   Exact match: {current_path_str == item_source}")
    print(f"   Starts with: {current_path_str.startswith(item_source + '/')}")

    if current_path_str == item_source or current_path_str.startswith(item_source + '/'):
        print(f"\n✅ SUCCESS: Files in subfolder would use folder item_id: {folder_item.id}")

        # Verify this item_id has processing results
        if history:
            print(f"✅ This item_id HAS processing results")
        else:
            print(f"⚠️  This item_id has NO processing results yet")
    else:
        print(f"\n❌ FAIL: Path matching logic didn't work")

if __name__ == "__main__":
    test_item_id_lookup()
