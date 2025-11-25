#!/usr/bin/env python3
"""
Simple Integration Test Validation

Validates that the integration test framework is working correctly and
demonstrates that director-library integration is functional.
"""

import sys
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

# Add src directory to Python path
src_dir = Path(__file__).parent / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))

from fichero.library.models import Collection, CollectionItem
from fichero.library.storage import LibraryStorage
from fichero.library.library_manager import LibraryManager
from fichero.library.director_integration import DirectorIntegrationService
from unittest.mock import Mock


def test_basic_integration():
    """Test basic director-library integration is working"""
    print("🧪 Testing Director-Library Integration Framework...")

    # Create temporary directories
    test_dir = Path(tempfile.mkdtemp())
    library_dir = test_dir / "library"
    output_dir = test_dir / "outputs"
    library_dir.mkdir()
    output_dir.mkdir()

    try:
        # Create test database
        db_path = library_dir / "test.db"
        storage = LibraryStorage(str(db_path))

        # Mock app and director
        app = Mock()
        director = Mock()

        # Create library manager
        with patch('fichero.library.path_resolver.get_library_database_path', return_value=db_path):
            library_manager = LibraryManager(app=app)
        library_manager.storage = storage

        # Create director integration service
        director_service = DirectorIntegrationService(
            app=app,
            library_manager=library_manager,
            director=director
        )

        # Create test collection and item
        test_collection = Collection(
            id="test-collection-123",
            name="Test Collection",
            type="local"
        )
        storage.add_collection(test_collection)

        test_item = CollectionItem(
            id="test-item-123",
            collection_id=test_collection.id,
            type="file",
            name="test.jpg",
            status="pending"
        )
        storage.add_collection_item(test_item)

        # Create minimal workflow manifest
        manifest_dir = output_dir / "test_output"
        manifest_dir.mkdir()

        workflow_manifest = {
            "version": "1.0",
            "workflow": {
                "plan_name": "Test Plan",
                "workflow_name": "Test",
                "task_id": "test-123",
                "success": True
            },
            "steps": [
                {
                    "order": 1,
                    "name": "test_step",
                    "status": "success",
                    "manifest_file": "assets/test/test_manifest.jsonl"
                }
            ]
        }

        manifest_file = manifest_dir / "workflow_manifest.json"
        manifest_file.write_text(json.dumps(workflow_manifest))

        # Create test output
        test_assets_dir = manifest_dir / "assets" / "test"
        test_assets_dir.mkdir(parents=True)

        test_manifest = {
            "outputs": ["test_output.txt"],
            "source": "test.jpg",
            "details": {"test": True}
        }

        test_manifest_file = test_assets_dir / "test_manifest.jsonl"
        test_manifest_file.write_text(json.dumps(test_manifest))

        test_output_file = test_assets_dir / "test_output.txt"
        test_output_file.write_text("Test output content")

        # Test ingestion
        director_service._ingest_processing_outputs(
            processing_result_id="test-result-123",
            collection_id=test_collection.id,
            item_id=test_item.id,
            output_path=manifest_dir
        )

        # Verify outputs were created
        outputs = storage.get_outputs_by_item(item_id=test_item.id)

        success = len(outputs) > 0

        if success:
            print("✅ Basic integration test PASSED!")
            print(f"   Created {len(outputs)} processing output record(s)")
            print("   Director → Database ingestion is working")
            return True
        else:
            print("❌ Basic integration test FAILED!")
            print("   No processing outputs were created")
            return False

    except Exception as e:
        print(f"❌ Integration test FAILED with error: {e}")
        return False

    finally:
        # Clean up
        import shutil
        if test_dir.exists():
            shutil.rmtree(test_dir)


def main():
    """Run basic validation"""
    print("=" * 60)
    print("FICHERO DIRECTOR-LIBRARY INTEGRATION VALIDATION")
    print("=" * 60)
    print()

    success = test_basic_integration()

    print()
    print("=" * 60)
    if success:
        print("🎉 VALIDATION SUCCESSFUL!")
        print()
        print("The director-library integration framework is working correctly.")
        print("The comprehensive integration tests in tests/integration/ are ready to use.")
        print()
        print("Next steps:")
        print("• Run full integration test suite: PYTHONPATH=src python -m pytest tests/integration/")
        print("• Or use: python run_integration_tests.py")
        print("• Individual tests: python run_integration_tests.py --pattern test_single_file_processing_end_to_end")
    else:
        print("💥 VALIDATION FAILED!")
        print()
        print("The director-library integration has issues that need to be resolved.")

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())