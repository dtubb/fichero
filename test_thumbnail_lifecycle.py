#!/usr/bin/env python3
"""
Test complete thumbnail lifecycle:
1. Import folder → generates thumbnails
2. Import same folder again → reuses thumbnails (deduplication)
3. Delete first collection → thumbnails remain (still referenced)
4. Delete second collection → thumbnails deleted (no more references)
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero.library.library_manager import LibraryManager


async def test_thumbnail_lifecycle():
    """Test complete thumbnail lifecycle with reference counting"""

    # Initialize library manager
    library_path = Path.home() / "Library" / "Application Support" / "ca.tubb.fichero"
    db_path = library_path / "library" / "library.db"
    thumbnail_dir = library_path / "library" / "thumbnails"

    library_manager = LibraryManager(db_path)

    # Test folder path
    test_folder = Path("/Users/dtubb/Documents/fichero/1930 Moisés Delgado M y Arquímedes Delgado R. Contra Cia minera Chocó pacifico Derecho sobre la mina playa de oro Playa de oro")

    if not test_folder.exists():
        print(f"❌ Test folder not found: {test_folder}")
        return False

    print(f"\n{'='*80}")
    print(f"THUMBNAIL LIFECYCLE TEST")
    print(f"{'='*80}\n")

    # Count initial thumbnails
    initial_thumbnail_count = len(list(thumbnail_dir.rglob("*.png"))) if thumbnail_dir.exists() else 0
    print(f"📊 Initial state:")
    print(f"   Thumbnails on disk: {initial_thumbnail_count}")

    # Get initial database thumbnail count
    initial_db_thumbnails = len(library_manager.storage.db.execute("SELECT id FROM thumbnails").fetchall()) if hasattr(library_manager.storage, 'db') else 0

    # STEP 1: Import folder first time
    print(f"\n{'='*80}")
    print(f"STEP 1: Import folder (first time)")
    print(f"{'='*80}\n")

    collection_id_1 = await library_manager.add_collection(
        name="Test Collection 1",
        collection_type="external",
        source_path=str(test_folder)
    )

    stats_1 = await library_manager.add_folder_items_to_collection(
        collection_id=collection_id_1,
        folder_path=str(test_folder),
        operation="link",
        recursive=True
    )

    print(f"✅ Collection 1 created: {collection_id_1}")
    print(f"   Files added: {stats_1['added']}")

    # Wait for thumbnails to generate
    await asyncio.sleep(2)

    # Count thumbnails after first import
    after_first_count = len(list(thumbnail_dir.rglob("*.png"))) if thumbnail_dir.exists() else 0
    thumbnails_generated = after_first_count - initial_thumbnail_count

    print(f"\n📊 After first import:")
    print(f"   Thumbnails on disk: {after_first_count} (+{thumbnails_generated} new)")

    # STEP 2: Import same folder again (should reuse thumbnails)
    print(f"\n{'='*80}")
    print(f"STEP 2: Import same folder (second time - should reuse thumbnails)")
    print(f"{'='*80}\n")

    collection_id_2 = await library_manager.add_collection(
        name="Test Collection 2 (Duplicate)",
        collection_type="external",
        source_path=str(test_folder)
    )

    stats_2 = await library_manager.add_folder_items_to_collection(
        collection_id=collection_id_2,
        folder_path=str(test_folder),
        operation="link",
        recursive=True
    )

    print(f"✅ Collection 2 created: {collection_id_2}")
    print(f"   Files added: {stats_2['added']}")

    # Wait for any thumbnail operations
    await asyncio.sleep(2)

    # Count thumbnails after second import (should be same - deduplication)
    after_second_count = len(list(thumbnail_dir.rglob("*.png"))) if thumbnail_dir.exists() else 0

    print(f"\n📊 After second import:")
    print(f"   Thumbnails on disk: {after_second_count}")

    if after_second_count == after_first_count:
        print(f"   ✅ DEDUPLICATION WORKING: No new thumbnails generated (reused existing)")
    else:
        print(f"   ⚠️  WARNING: Generated {after_second_count - after_first_count} new thumbnails (should have reused)")

    # STEP 3: Delete first collection (thumbnails should remain - still referenced by collection 2)
    print(f"\n{'='*80}")
    print(f"STEP 3: Delete first collection (thumbnails should REMAIN)")
    print(f"{'='*80}\n")

    success = await library_manager.delete_collection(collection_id_1)
    print(f"✅ Collection 1 deleted: {success}")

    await asyncio.sleep(1)

    after_first_delete = len(list(thumbnail_dir.rglob("*.png"))) if thumbnail_dir.exists() else 0

    print(f"\n📊 After deleting Collection 1:")
    print(f"   Thumbnails on disk: {after_first_delete}")

    if after_first_delete == after_second_count:
        print(f"   ✅ REFERENCE COUNTING WORKING: Thumbnails kept (still referenced by Collection 2)")
    else:
        print(f"   ❌ ERROR: Lost {after_second_count - after_first_delete} thumbnails (should have kept all)")

    # STEP 4: Delete second collection (thumbnails should now be deleted - no more references)
    print(f"\n{'='*80}")
    print(f"STEP 4: Delete second collection (thumbnails should be DELETED)")
    print(f"{'='*80}\n")

    success = await library_manager.delete_collection(collection_id_2)
    print(f"✅ Collection 2 deleted: {success}")

    await asyncio.sleep(1)

    after_second_delete = len(list(thumbnail_dir.rglob("*.png"))) if thumbnail_dir.exists() else 0

    print(f"\n📊 After deleting Collection 2:")
    print(f"   Thumbnails on disk: {after_second_delete}")

    thumbnails_deleted = after_first_delete - after_second_delete

    if after_second_delete == initial_thumbnail_count:
        print(f"   ✅ CLEANUP WORKING: All test thumbnails deleted ({thumbnails_deleted} removed)")
    else:
        print(f"   ⚠️  Note: {after_second_delete - initial_thumbnail_count} thumbnails remain")

    # FINAL VERIFICATION
    print(f"\n{'='*80}")
    print(f"FINAL VERIFICATION")
    print(f"{'='*80}\n")

    all_passed = True

    # Check 1: Deduplication worked
    if after_second_count == after_first_count:
        print(f"✅ TEST 1 PASSED: Thumbnail deduplication working")
    else:
        print(f"❌ TEST 1 FAILED: Deduplication not working")
        all_passed = False

    # Check 2: Reference counting worked (kept thumbnails after first delete)
    if after_first_delete == after_second_count:
        print(f"✅ TEST 2 PASSED: Reference counting working (kept shared thumbnails)")
    else:
        print(f"❌ TEST 2 FAILED: Reference counting not working")
        all_passed = False

    # Check 3: Cleanup worked (deleted thumbnails after last reference removed)
    if thumbnails_deleted > 0:
        print(f"✅ TEST 3 PASSED: Cleanup working (deleted {thumbnails_deleted} thumbnails)")
    else:
        print(f"❌ TEST 3 FAILED: Cleanup not working")
        all_passed = False

    if all_passed:
        print(f"\n🎉 ALL TESTS PASSED: Complete thumbnail lifecycle working correctly!")
        return True
    else:
        print(f"\n❌ SOME TESTS FAILED: Review output above")
        return False


if __name__ == "__main__":
    result = asyncio.run(test_thumbnail_lifecycle())
    sys.exit(0 if result else 1)
