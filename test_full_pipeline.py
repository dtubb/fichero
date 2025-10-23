#!/usr/bin/env python3
"""
Full pipeline test: Clear library → Add collection → Process → Verify results
"""
import asyncio
import sys
from pathlib import Path
import shutil

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero.library.library_manager import LibraryManager
from fichero.library.path_resolver import get_library_path
from fichero.library.director_integration import DirectorIntegrationService
from fichero.director.director_service import FicheroDirector

async def clear_library(library_manager):
    """Clear all collections from the library"""
    print("\n" + "="*60)
    print("STEP 1: Clearing Library")
    print("="*60)

    collections = await library_manager.get_all_collections()
    print(f"Found {len(collections)} existing collections")

    for collection in collections:
        print(f"  Deleting: {collection.name} (ID: {collection.id})")
        await library_manager.delete_collection(collection.id)

    # Verify empty
    collections = await library_manager.get_all_collections()
    print(f"✅ Library cleared. Remaining collections: {len(collections)}")

async def add_test_collection(library_manager, test_path: str):
    """Add a test collection"""
    print("\n" + "="*60)
    print("STEP 2: Adding Test Collection")
    print("="*60)

    test_path_obj = Path(test_path)
    if not test_path_obj.exists():
        print(f"❌ Test path does not exist: {test_path}")
        return None

    print(f"Adding collection from: {test_path}")
    collection_id = await library_manager.add_collection(
        name=test_path_obj.name,
        collection_type="external",
        source_path=test_path,
        description=f"Test collection from {test_path}"
    )

    print(f"✅ Collection created: {collection_id}")

    # Add items from folder
    print(f"\nScanning folder for items...")
    item_count = 0
    for file_path in test_path_obj.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.pdf']:
            item_id = await library_manager.add_item_to_collection(
                collection_id=collection_id,
                item_type="file",
                source=str(file_path),
                name=file_path.name,
                operation="link"
            )
            item_count += 1
            print(f"  Added: {file_path.name}")

    print(f"✅ Added {item_count} items to collection")
    return collection_id

async def process_collection(library_manager, collection_id: str, plan_name: str = "Test Images Only"):
    """Process the collection with a plan"""
    print("\n" + "="*60)
    print(f"STEP 3: Processing Collection with Plan: {plan_name}")
    print("="*60)

    # Initialize Director
    from fichero.config.core.settings_manager import SettingsManager
    settings_manager = SettingsManager()
    settings = settings_manager.load_settings()

    director = FicheroDirector(settings)

    # Initialize the backend to set up processing coordinator
    print("Initializing Director backend...")
    if not director.initialize_backend():
        print("❌ Failed to initialize Director backend")
        return []
    print("✅ Director backend initialized")

    # Initialize DirectorIntegrationService (needs app for event handling)
    class MockApp:
        pass
    mock_app = MockApp()

    integration_service = DirectorIntegrationService(mock_app, library_manager, director)

    # Get all items in collection
    items = await library_manager.get_collection_items(collection_id)
    item_ids = [item.id for item in items]

    print(f"Processing {len(item_ids)} items")
    print(f"Item IDs: {item_ids}")

    # Process items
    task_ids = await integration_service.process_items(
        collection_id=collection_id,
        item_ids=item_ids,
        plan_name=plan_name,
        workflow_name="ImagePrep"  # Use ImagePrep for quick testing
    )

    print(f"✅ Submitted {len(task_ids)} tasks to Director")
    print(f"Task IDs: {task_ids}")

    # Wait for processing to complete (simplified - just wait a reasonable time)
    print("\nWaiting for processing to complete...")
    print("(Waiting 30 seconds for tasks to finish...)")
    await asyncio.sleep(30)
    print("✅ Wait complete - proceeding to verify results")

    return task_ids

async def verify_results(library_manager, collection_id: str):
    """Verify we can load the processing results"""
    print("\n" + "="*60)
    print("STEP 4: Verifying Results")
    print("="*60)

    items = await library_manager.get_collection_items(collection_id)
    print(f"Collection has {len(items)} items")

    for i, item in enumerate(items, 1):
        print(f"\nItem {i}: {item.name}")
        print(f"  ID: {item.id}")
        print(f"  Status: {item.status}")

        # Get output data
        output_data = await library_manager.get_item_output_data(item.id)

        if output_data and output_data.get('has_outputs'):
            print(f"  ✅ Has outputs!")
            print(f"     Workflow: {output_data.get('workflow')}")
            print(f"     Output root: {output_data.get('output_root')}")
            print(f"     Processing steps: {len(output_data.get('processing_steps', []))}")

            for j, step in enumerate(output_data.get('processing_steps', []), 1):
                step_name = step.step_name if hasattr(step, 'step_name') else str(step)
                print(f"       {j}. {step_name}")
        else:
            print(f"  ❌ No outputs (not processed or processing failed)")

async def main():
    """Run the full pipeline test"""
    print("\n" + "="*60)
    print("FICHERO FULL PIPELINE TEST")
    print("="*60)

    # Initialize library with mock app for CLI mode
    class MockApp:
        pass

    mock_app = MockApp()
    library_manager = LibraryManager(mock_app)
    print(f"Library path: {library_manager.library_path}")
    print("✅ Library manager initialized")

    # Step 1: Clear library
    await clear_library(library_manager)

    # Step 2: Add test collection
    # Try Tiny Test first, fall back to Small Test
    test_paths = [
        "/Users/dtubb/Documents/fichero/Tiny Test",
        "/Users/dtubb/Documents/fichero/Small Test"
    ]

    collection_id = None
    for test_path in test_paths:
        if Path(test_path).exists():
            collection_id = await add_test_collection(library_manager, test_path)
            if collection_id:
                break

    if not collection_id:
        print("❌ No test collections found!")
        print(f"Tried: {test_paths}")
        return

    # Step 3: Process collection
    await process_collection(library_manager, collection_id, plan_name="Test Images Only")

    # Step 4: Verify results
    await verify_results(library_manager, collection_id)

    print("\n" + "="*60)
    print("PIPELINE TEST COMPLETE")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
