#!/usr/bin/env python3
"""
Debug script for integration test metadata extraction issues
"""

import logging
import sys
import tempfile
import json
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero.library.storage import LibraryStorage
from fichero.library.director_integration import DirectorIntegrationService
from fichero.library.models import Collection, CollectionItem

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def debug_integration_flow():
    """Debug the integration test flow"""

    # Create a temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        # Create library components
        storage = LibraryStorage(db_path)

        # Mock library manager
        class MockLibraryManager:
            def __init__(self):
                self.storage = storage

        library_manager = MockLibraryManager()

        # Mock director
        class MockDirector:
            def __init__(self):
                self.task_monitor = None

        director = MockDirector()
        director_service = DirectorIntegrationService(None, library_manager, director)

        # Create test collection and item
        test_collection = Collection(
            name="Test Collection",
            type="local"
        )
        storage.add_collection(test_collection)

        test_file_item = CollectionItem(
            collection_id=test_collection.id,
            type="file",
            source_path="test_document.jpg",
            name="test_document.jpg"
        )
        storage.add_collection_item(test_file_item)

        print(f"Created collection: {test_collection.id}")
        print(f"Created item: {test_file_item.id}")

        # Create test output structure like the integration test does
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "single_file_test"
            output_dir.mkdir()

            # Create workflow manifest
            workflow_manifest = {
                "plan_name": "Transcribir y Catalogar",
                "workflow_name": "Catalogue",
                "task_id": "file-task-123",
                "steps": [
                    {
                        "order": 2,
                        "name": "catalogue",
                        "status": "success",
                        "manifest_file": "assets/catalogue/catalogue_manifest.jsonl"
                    }
                ]
            }
            manifest_file = output_dir / "workflow_manifest.json"
            manifest_file.write_text(json.dumps(workflow_manifest, indent=2))

            # Create catalogue directory and files
            cat_dir = output_dir / "assets" / "catalogue"
            cat_dir.mkdir(parents=True)

            # Create catalogue JSON file
            cat_file = cat_dir / "test_document_catalogue.json"
            catalogue_data = {
                "title": "Document: test_document.jpg",
                "document_type": "Letter",
                "date": "1965-03-15",
                "author": "María González",
                "language": "Spanish",
                "description": "Personal letter discussing family matters from test_document.jpg"
            }
            cat_file.write_text(json.dumps(catalogue_data, indent=2))

            # Create catalogue manifest entry
            manifest_entry = {
                "outputs": [cat_file.name],
                "source": "test_document.jpg",
                "details": {
                    "catalogue_type": "file",
                    "fields_extracted": len(catalogue_data),
                    "confidence": 0.89
                }
            }
            cat_manifest = cat_dir / "catalogue_manifest.jsonl"
            cat_manifest.write_text(json.dumps(manifest_entry) + '\n')

            print(f"Created output structure at: {output_dir}")
            print(f"Catalogue file: {cat_file}")
            print(f"Catalogue file exists: {cat_file.exists()}")
            print(f"Manifest file: {cat_manifest}")

            # Now run the integration process
            processing_result_id = "result-file-123"

            print("\n=== INGESTING PROCESSING OUTPUTS ===")
            director_service._ingest_processing_outputs(
                processing_result_id=processing_result_id,
                collection_id=test_collection.id,
                item_id=test_file_item.id,
                output_path=output_dir
            )

            # Check what outputs were created
            outputs = storage.get_outputs_by_item(item_id=test_file_item.id)
            print(f"\nProcessingOutputs created: {len(outputs)}")
            for output in outputs:
                print(f"  - {output.output_type}: {output.output_path} (step: {output.step_name})")

            print("\n=== EXTRACTING METADATA ===")
            director_service._extract_metadata_from_outputs(
                processing_result_id=processing_result_id,
                collection_id=test_collection.id,
                output_path=output_dir
            )

            # Check what metadata was created
            print(f"\nQuerying metadata for item_id: {test_file_item.id}")

            # First check all metadata without filtering
            try:
                all_metadata = storage.get_all_extracted_metadata()
                print(f"Total metadata records in database: {len(all_metadata) if all_metadata else 0}")
                if all_metadata:
                    for meta in all_metadata[:5]:  # Show first 5
                        print(f"  - {meta.schema_type}.{meta.key} (item_id={meta.item_id}): {meta.value}")
            except Exception as e:
                print(f"Error getting all metadata: {e}")

            # Now check item-specific metadata
            try:
                metadata_records = storage.get_extracted_metadata_by_item(item_id=test_file_item.id)
                print(f"\nExtractedMetadata records for item {test_file_item.id}: {len(metadata_records) if metadata_records else 0}")
                if metadata_records:
                    for meta in metadata_records:
                        print(f"  - {meta.schema_type}.{meta.key}: {meta.value}")
            except Exception as e:
                print(f"Error getting metadata by item: {e}")

            # Check catalogue-specific metadata
            try:
                catalogue_meta = storage.get_extracted_metadata_by_item(
                    item_id=test_file_item.id,
                    schema_type="catalogue"
                )
                print(f"\nCatalogue metadata records: {len(catalogue_meta) if catalogue_meta else 0}")
                if catalogue_meta:
                    for meta in catalogue_meta:
                        print(f"  - {meta.key}: {meta.value}")
            except Exception as e:
                print(f"Error getting catalogue metadata: {e}")

    finally:
        # Clean up
        import os
        try:
            os.unlink(db_path)
        except:
            pass

if __name__ == "__main__":
    debug_integration_flow()