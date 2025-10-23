#!/usr/bin/env python3
"""Quick script to get a processed item ID for testing"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import asyncio
from fichero.library.path_resolver import get_library_database_path
from fichero.library.storage import LibraryStorage

class MockApp:
    """Mock app for library initialization"""
    class Paths:
        app = Path(__file__).parent / "src" / "fichero"

    paths = Paths()

async def main():
    # Get library path
    db_path = get_library_database_path(MockApp())

    # Initialize storage
    storage = LibraryStorage(db_path)

    # Get the test collection
    collection_id = "e9476f00-fbdc-4cea-97c7-652cbdcabbe4"

    # Get items
    items = storage.get_collection_items(collection_id)

    if not items:
        print("❌ No items found in collection")
        return

    print(f"✅ Found {len(items)} items in collection")
    print()

    # Find processed items
    for item in items:
        processing_history = storage.get_processing_history(item.id)
        if processing_history:
            print(f"📄 Item: {item.name}")
            print(f"   ID: {item.id}")
            print(f"   Type: {item.type}")
            print(f"   Source: {item.source_path}")
            print(f"   Processing Results: {len(processing_history)}")
            for i, result in enumerate(processing_history, 1):
                print(f"     {i}. Workflow: {result.workflow}, Status: {result.status}")
            print()

            # Print command to test
            print(f"Test command:")
            print(f"  briefcase dev -- library outputs item-outputs {item.id}")
            print()
            break

if __name__ == "__main__":
    asyncio.run(main())
