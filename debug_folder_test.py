#!/usr/bin/env python3
"""
Debug script for folder processing test
"""

import logging
import sys
import tempfile
import json
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Reduce log noise
logging.basicConfig(level=logging.WARNING)

# Import test class
sys.path.insert(0, str(Path(__file__).parent))
from tests.integration.test_director_library_integration import TestDirectorLibraryIntegration

def debug_folder_test():
    """Debug the folder processing test"""
    test_instance = TestDirectorLibraryIntegration()
    test_instance.setUp()

    try:
        # Replicate the exact test setup
        folder_output_dir = test_instance.output_dir / "single_folder_test"
        folder_output_dir.mkdir()

        # Create workflow manifest for folder processing (same as test)
        test_instance._create_workflow_manifest(folder_output_dir, {
            "plan_name": "Transcribir y Catalogar",
            "workflow_name": "Catalogue",
            "task_id": "folder-task-123",
            "steps": [
                {
                    "order": 1,
                    "name": "catalogue_folder",
                    "status": "success",
                    "manifest_file": "assets/catalogue/catalogue_manifest.jsonl"
                }
            ]
        })

        # Create folder-level catalogue output (same as test)
        test_instance._create_catalogue_outputs(folder_output_dir, "test_folder", is_folder_level=True)

        print(f"Created test structure in: {folder_output_dir}")

        # Check what files were created
        cat_dir = folder_output_dir / "assets" / "catalogue"
        if cat_dir.exists():
            print(f"Catalogue files:")
            for file_path in cat_dir.iterdir():
                print(f"  - {file_path.name}")
                if file_path.suffix == ".json":
                    print(f"    Content: {file_path.read_text()[:100]}...")

        # Run the integration process
        processing_result_id = "result-folder-123"
        print(f"\n=== INGESTION ===")
        test_instance.director_service._ingest_processing_outputs(
            processing_result_id=processing_result_id,
            collection_id=test_instance.test_collection.id,
            item_id=test_instance.test_folder_item.id,
            output_path=folder_output_dir
        )

        # Check ProcessingOutput records
        outputs = test_instance.storage.get_outputs_by_item(
            item_id=test_instance.test_folder_item.id
        )
        print(f"ProcessingOutput records: {len(outputs)}")
        for output in outputs:
            print(f"  - {output.output_type}: {output.output_path} (step: {output.step_name})")

        print(f"\n=== METADATA EXTRACTION ===")
        test_instance.director_service._extract_metadata_from_outputs(
            processing_result_id=processing_result_id,
            collection_id=test_instance.test_collection.id,
            output_path=folder_output_dir
        )

        # Check metadata records
        metadata_records = test_instance.storage.get_extracted_metadata_by_item(
            item_id=test_instance.test_folder_item.id
        )
        print(f"ExtractedMetadata records: {len(metadata_records)}")
        for meta in metadata_records:
            print(f"  - {meta.schema_type}.{meta.key}: {meta.value}")

        # Check collection-level metadata separately
        collection_metadata = test_instance.storage.get_collection_level_metadata(
            collection_id=test_instance.test_collection.id
        )
        print(f"Collection-level metadata records: {len(collection_metadata)}")
        for meta in collection_metadata:
            print(f"  - {meta.schema_type}.{meta.key}: {meta.value}")

        return len(metadata_records) > 0 or len(collection_metadata) > 0

    finally:
        test_instance.tearDown()

if __name__ == "__main__":
    success = debug_folder_test()
    print(f"\nDebug result: {'SUCCESS' if success else 'FAILED'}")