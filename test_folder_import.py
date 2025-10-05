#!/usr/bin/env python3
"""
Test script for new folder import functionality with thumbnail deduplication
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero.library.library_manager import LibraryManager

async def test_folder_import():
    """Test importing a folder with the new architecture"""

    # Initialize library manager
    library_path = Path.home() / "Library" / "Application Support" / "ca.tubb.fichero"
    db_path = library_path / "library" / "library.db"

    library_manager = LibraryManager(db_path)

    # Test folder path
    test_folder = Path("/Users/dtubb/Documents/fichero/1930 Moisés Delgado M y Arquímedes Delgado R. Contra Cia minera Chocó pacifico Derecho sobre la mina playa de oro Playa de oro")

    if not test_folder.exists():
        print(f"❌ Test folder not found: {test_folder}")
        return False

    print(f"📂 Testing folder import: {test_folder.name}")
    print(f"   Files in folder: {len(list(test_folder.glob('*')))}")

    # Create a test collection (use "external" to link without copying)
    collection_id = await library_manager.add_collection(
        name=f"Test: {test_folder.name}",
        collection_type="external",
        source_path=str(test_folder)
    )

    if not collection_id:
        print("❌ Failed to create collection")
        return False

    print(f"✅ Created collection: {collection_id}")

    # Import folder files
    print("\n📥 Importing folder files...")
    stats = await library_manager.add_folder_items_to_collection(
        collection_id=collection_id,
        folder_path=str(test_folder),
        operation="link",
        recursive=True
    )

    print(f"\n📊 Import Statistics:")
    print(f"   ✅ Added: {stats['added']}")
    print(f"   ⏭️  Skipped: {stats['skipped']}")
    print(f"   ❌ Errors: {stats['errors']}")
    print(f"   🆔 Item IDs: {len(stats['item_ids'])}")

    # Verify items in collection
    items = library_manager.storage.get_collection_items(collection_id)
    print(f"\n📋 Collection Items: {len(items)}")

    # Check thumbnail tracking
    if library_manager.storage:
        print(f"\n🖼️  Checking thumbnail database...")
        for item in items[:3]:  # Check first 3 items
            file_hash = item.metadata.get('file_hash')
            if file_hash:
                thumbnail = library_manager.storage.get_thumbnail(file_hash, "128x128")
                if thumbnail:
                    print(f"   ✅ Thumbnail tracked: {thumbnail.thumbnail_path[:50]}...")
                    # Check if file exists
                    thumbnail_file = library_manager.icon_generator.cache_dir / thumbnail.thumbnail_path
                    if thumbnail_file.exists():
                        print(f"      ✓ File exists on disk")
                    else:
                        print(f"      ✗ File missing on disk!")
                else:
                    print(f"   ⚠️  No thumbnail record for: {item.name}")

    # Test deduplication by importing again
    print(f"\n🔄 Testing deduplication (importing same folder again)...")
    stats2 = await library_manager.add_folder_items_to_collection(
        collection_id=collection_id,
        folder_path=str(test_folder),
        operation="link",
        recursive=True
    )

    print(f"   Second import results:")
    print(f"   ✅ Added: {stats2['added']} (should be 0)")
    print(f"   ⏭️  Skipped: {stats2['skipped']} (should equal first added count)")
    print(f"   ❌ Errors: {stats2['errors']}")

    # Cleanup
    print(f"\n🧹 Cleaning up test collection...")
    success = await library_manager.delete_collection(collection_id)
    if success:
        print(f"   ✅ Collection deleted")
    else:
        print(f"   ❌ Failed to delete collection")

    # Verify results
    if stats['added'] > 0 and stats2['added'] == 0 and stats2['skipped'] == stats['added']:
        print(f"\n✅ TEST PASSED: Folder import and deduplication working correctly!")
        return True
    else:
        print(f"\n❌ TEST FAILED: Unexpected results")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_folder_import())
    sys.exit(0 if result else 1)
