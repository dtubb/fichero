#!/usr/bin/env python3
"""
Debug script to test database ingestion with existing output files
"""

import sys
import logging
import asyncio
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from fichero.library.library_manager import LibraryManager
from fichero.library.director_integration import DirectorIntegrationService

async def test_ingestion():
    """Test ingestion with existing output files"""

    # Initialize library manager
    print("Initializing LibraryManager...")
    # LibraryManager needs an app object, we'll pass None for testing
    library_manager = LibraryManager(app=None)

    # Get the collection
    collections = await library_manager.get_all_collections()
    print(f"Found {len(collections)} collections")

    if not collections:
        print("ERROR: No collections found")
        return

    # Check all collections and their items
    for idx, col in enumerate(collections):
        print(f"{idx+1}. {col.name} (id={col.id})")
        items = await library_manager.get_collection_items(col.id)
        print(f"   Items: {len(items)}")
        for item in items:
            print(f"     - {item.name} (id={item.id})")

    # Find collection with processing history by checking all items
    collection = None
    target_item = None
    history = []

    for col in collections:
        items = await library_manager.get_collection_items(col.id)
        for item in items:
            item_history = library_manager.storage.get_processing_history(item.id)
            if len(item_history) > 0:
                collection = col
                target_item = item
                history = item_history
                print(f"\nUsing collection: {collection.name} (id={collection.id})")
                print(f"Found item with processing history: {item.name} (id={item.id})")
                print(f"Processing history records: {len(history)}")
                break
        if collection:
            break

    if not collection:
        print("\nNo collection with processing history found")
        return

    print("\nProcessing history records:")
    for record in history:
        print(f"  - workflow={record.workflow}, status={record.status}, id={record.id}")

        # Check if this record has outputs
        outputs = library_manager.storage.get_processing_outputs(record.id)
        print(f"    Outputs in DB: {len(outputs)}")

        if len(outputs) == 0 and record.output_paths:
            # output_paths is a list
            print(f"    Output paths: {record.output_paths}")
            output_path = Path(record.output_paths[0]) if record.output_paths else None
            if not output_path:
                continue

            if output_path.exists():
                print(f"    Output path EXISTS!")

                # Check for workflow manifest
                workflow_manifest_path = output_path / "workflow_manifest.json"
                if workflow_manifest_path.exists():
                    print(f"    workflow_manifest.json EXISTS!")

                    # List all manifest files
                    print("\n    Looking for tool manifests...")
                    for manifest in output_path.rglob("*_manifest.jsonl"):
                        print(f"      - {manifest.relative_to(output_path)}")

                        # Check file size
                        size = manifest.stat().st_size
                        print(f"        Size: {size} bytes")

                        if size > 0:
                            # Read first line
                            with open(manifest, 'r') as f:
                                first_line = f.readline().strip()
                                print(f"        First line: {first_line[:100]}...")

                    # Now try to ingest this manually
                    print(f"\n    Attempting manual ingestion for processing_result_id={record.id}...")

                    # Create a minimal director integration service
                    # We need to pass app and director, but we can use None for testing
                    integration = DirectorIntegrationService(None, library_manager, None)

                    # Use the target item ID
                    item_id = target_item.id if target_item else None
                    print(f"    Using item_id={item_id}")

                    # Call the ingestion method directly
                    integration._ingest_processing_outputs(
                        processing_result_id=record.id,
                        collection_id=collection.id,
                        item_id=item_id,
                        output_path=output_path
                    )

                    # Check if outputs were created
                    outputs_after = library_manager.storage.get_processing_outputs(record.id)
                    print(f"\n    Outputs after ingestion: {len(outputs_after)}")

                    for output in outputs_after:
                        print(f"      - {output.output_type}: {output.output_path}")

                else:
                    print(f"    workflow_manifest.json NOT FOUND")
            else:
                print(f"    Output path DOES NOT EXIST")

if __name__ == "__main__":
    asyncio.run(test_ingestion())
