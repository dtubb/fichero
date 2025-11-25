#!/usr/bin/env python3
"""
Debug script to directly check the database
"""

import logging
import sys
import tempfile
import json
import sqlite3
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero.library.storage import LibraryStorage
from fichero.library.director_integration import DirectorIntegrationService
from fichero.library.models import Collection, CollectionItem

# Set up logging
logging.basicConfig(level=logging.WARNING)  # Reduce noise
logger = logging.getLogger(__name__)

def debug_sql_directly():
    """Debug the database content directly"""

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

        # Create test output structure
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

            # Now run the integration process
            processing_result_id = "result-file-123"

            print("\n=== INGESTING AND EXTRACTING ===")
            director_service._ingest_processing_outputs(
                processing_result_id=processing_result_id,
                collection_id=test_collection.id,
                item_id=test_file_item.id,
                output_path=output_dir
            )

            director_service._extract_metadata_from_outputs(
                processing_result_id=processing_result_id,
                collection_id=test_collection.id,
                output_path=output_dir
            )

            # Now directly query the database
            print(f"\n=== DIRECT DATABASE QUERY ===")
            print(f"Target item_id: {test_file_item.id}")

            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()

                # Check what's in the extracted_metadata table
                cursor.execute("SELECT item_id, collection_id, schema_type, key, value FROM extracted_metadata")
                rows = cursor.fetchall()
                print(f"\nAll extracted_metadata rows: {len(rows)}")
                for i, row in enumerate(rows):
                    item_id, collection_id, schema_type, key, value = row
                    print(f"  {i+1}. item_id='{item_id}', collection_id='{collection_id}', schema_type='{schema_type}', key='{key}', value='{value[:50]}'")

                # Check if the item_id matches exactly
                cursor.execute("SELECT COUNT(*) FROM extracted_metadata WHERE item_id = ?", [test_file_item.id])
                exact_match_count = cursor.fetchone()[0]
                print(f"\nExact item_id matches: {exact_match_count}")

                # Check for any NULL item_ids
                cursor.execute("SELECT COUNT(*) FROM extracted_metadata WHERE item_id IS NULL")
                null_count = cursor.fetchone()[0]
                print(f"NULL item_ids: {null_count}")

                # Check the length of the item_id in the database vs our expected
                cursor.execute("SELECT DISTINCT item_id, LENGTH(item_id) FROM extracted_metadata")
                item_id_lengths = cursor.fetchall()
                print(f"Item ID lengths in database:")
                for item_id, length in item_id_lengths:
                    print(f"  '{item_id}' -> length {length}")

                print(f"Expected item_id: '{test_file_item.id}' -> length {len(test_file_item.id)}")

    finally:
        # Clean up
        import os
        try:
            os.unlink(db_path)
        except:
            pass

if __name__ == "__main__":
    debug_sql_directly()