#!/usr/bin/env python3
"""
Quick test to see if adding step info fixes the failing test
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

def test_with_step_info():
    """Test if adding step info fixes the metadata extraction"""
    test_instance = TestDirectorLibraryIntegration()
    test_instance.setUp()

    try:
        # Create test directory
        adjust_test_dir = test_instance.output_dir / "adjust_integration_test_fixed"
        adjust_test_dir.mkdir()

        # Create workflow manifest WITH step information
        test_instance._create_workflow_manifest(adjust_test_dir, {
            "plan_name": "Transcribir y Catalogar",
            "workflow_name": "Catalogue",
            "task_id": "adjust-task-123",
            "steps": [
                {
                    "order": 1,
                    "name": "transcribe",
                    "status": "success",
                    "manifest_file": "assets/transcriptions/transcriptions_manifest.jsonl"
                },
                {
                    "order": 2,
                    "name": "catalogue",
                    "status": "success",
                    "manifest_file": "assets/catalogue/catalogue_manifest.jsonl"
                }
            ]
        })

        test_instance._create_transcription_outputs(adjust_test_dir, ["adjust_doc.jpg"])
        test_instance._create_catalogue_outputs(adjust_test_dir, "adjust_doc.jpg")

        # Process into database
        test_instance.director_service._ingest_processing_outputs(
            processing_result_id="adjust-result-123",
            collection_id=test_instance.test_collection.id,
            item_id=test_instance.test_file_item.id,
            output_path=adjust_test_dir
        )

        test_instance.director_service._extract_metadata_from_outputs(
            processing_result_id="adjust-result-123",
            collection_id=test_instance.test_collection.id,
            output_path=adjust_test_dir
        )

        # Check metadata
        all_metadata = test_instance.storage.get_extracted_metadata_by_item(
            item_id=test_instance.test_file_item.id
        )

        print(f"Total metadata records: {len(all_metadata)}")

        # Group by schema type
        metadata_by_type = {}
        for meta in all_metadata:
            if meta.schema_type not in metadata_by_type:
                metadata_by_type[meta.schema_type] = []
            metadata_by_type[meta.schema_type].append(meta)

        print(f"Metadata types: {list(metadata_by_type.keys())}")
        print(f"Has catalogue metadata: {'catalogue' in metadata_by_type}")

        if 'catalogue' in metadata_by_type:
            print(f"Catalogue records: {len(metadata_by_type['catalogue'])}")
            for meta in metadata_by_type['catalogue']:
                print(f"  - {meta.key}: {meta.value}")

        return 'catalogue' in metadata_by_type

    finally:
        test_instance.tearDown()

if __name__ == "__main__":
    success = test_with_step_info()
    print(f"\nTest result: {'PASSED' if success else 'FAILED'}")