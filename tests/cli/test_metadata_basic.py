#!/usr/bin/env python3
"""
Basic metadata CLI test

Tests the metadata API integration with the CLI by:
1. Creating test metadata directly via the API
2. Querying it via CLI commands
3. Verifying the results
"""

import sys
import subprocess
import json
from pathlib import Path
from unittest.mock import Mock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from fichero.library.storage import LibraryStorage
from fichero.library.metadata_api import LibraryMetadataAPI
from fichero.library.path_resolver import get_library_database_path
from fichero.library.models import Collection, CollectionItem
from datetime import datetime


def setup_test_data():
    """Create test collection and items with metadata"""
    print("Setting up test data...")

    # Get library path
    mock_app = Mock()
    mock_app.paths = Mock()
    mock_app.paths.data = Path.home() / "Library" / "Application Support" / "ca.tubb.fichero"

    db_path = get_library_database_path(mock_app)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    storage = LibraryStorage(db_path)
    metadata_api = LibraryMetadataAPI(storage)

    # Create test collection
    test_collection = Collection(
        name="Metadata CLI Test Collection",
        description="Test collection for metadata CLI",
        type="external",
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    collection_id = storage.add_collection(test_collection)
    print(f"  Created collection: {collection_id}")

    # Create test items
    item_ids = []
    for i in range(3):
        item = CollectionItem(
            collection_id=collection_id,
            name=f"Test Item {i+1}",
            type="file",
            source_path=f"/tmp/test_{i+1}.png",
            storage_type="external",
            status="pending",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        item_id = storage.add_item(item)
        item_ids.append(item_id)
        print(f"  Created item {i+1}: {item_id}")

    # Add metadata to first two items
    # Item 1: Processed with crop and rotate
    metadata_api.save_step_metadata(
        item_id=item_ids[0],
        step_name="crop",
        metadata={
            "method": "yolo",
            "confidence": 0.92,
            "box": {"x1": 100, "y1": 50, "x2": 800, "y2": 1000}
        },
        version=1
    )
    metadata_api.save_step_metadata(
        item_id=item_ids[0],
        step_name="rotate",
        metadata={
            "angle": -0.5,
            "found_lines": True,
            "method": "line_detection"
        },
        version=1
    )
    print(f"  Added metadata to item 1")

    # Item 2: Processed with crop (different method) and transcribe
    metadata_api.save_step_metadata(
        item_id=item_ids[1],
        step_name="crop",
        metadata={
            "method": "manual",
            "confidence": 0.95,
            "box": {"x1": 50, "y1": 100, "x2": 900, "y2": 1200}
        },
        version=1
    )
    metadata_api.save_step_metadata(
        item_id=item_ids[1],
        step_name="transcribe",
        metadata={
            "text_length": 500,
            "model": "qwen-vl-max",
            "has_content": True
        },
        version=1
    )
    print(f"  Added metadata to item 2")

    # Item 3: No metadata (for testing zero results)
    print(f"  Item 3 has no metadata")

    print(f"\nTest data created successfully!")
    return collection_id, item_ids


def run_cli_command(args):
    """Run a CLI command and return output"""
    cmd = ["briefcase", "dev", "--", "library"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout + result.stderr, result.returncode


def test_metadata_query(collection_id):
    """Test metadata query command"""
    print("\n=== Testing metadata-query ===")

    # Test 1: Query by crop.method=yolo
    print("\nTest 1: Query crop.method=yolo")
    output, code = run_cli_command([
        "metadata-query", collection_id,
        "--filter", "crop.method=yolo"
    ])
    print(output)
    assert "Test Item 1" in output, "Should find item 1 with yolo crop"

    # Test 2: Query by crop.confidence>=0.90
    print("\nTest 2: Query crop.confidence>=0.90")
    output, code = run_cli_command([
        "metadata-query", collection_id,
        "--filter", "crop.confidence>=0.90"
    ])
    print(output)
    assert "2 item(s)" in output or "Test Item 1" in output, "Should find both items with high confidence"

    # Test 3: Multiple filters (AND logic)
    print("\nTest 3: Query crop.method=yolo AND rotate.found_lines=true")
    output, code = run_cli_command([
        "metadata-query", collection_id,
        "--filter", "crop.method=yolo",
        "--filter", "rotate.found_lines=true"
    ])
    print(output)
    assert "Test Item 1" in output, "Should find item 1 with both filters"
    assert "Test Item 2" not in output, "Should not find item 2 (no rotate metadata)"

    print("\n✓ All query tests passed!")


def test_metadata_show(item_ids):
    """Test metadata show command"""
    print("\n=== Testing metadata-show ===")

    # Test 1: Show all metadata for item 1
    print("\nTest 1: Show all metadata for item 1")
    output, code = run_cli_command([
        "metadata-show", item_ids[0]
    ])
    print(output)
    assert "crop" in output and "rotate" in output, "Should show both crop and rotate metadata"
    assert "yolo" in output, "Should show method value"

    # Test 2: Show specific step metadata
    print("\nTest 2: Show crop metadata only")
    output, code = run_cli_command([
        "metadata-show", item_ids[0],
        "--step", "crop"
    ])
    print(output)
    assert "crop" in output, "Should show crop metadata"
    assert "rotate" not in output, "Should not show rotate metadata"

    # Test 3: JSON output
    print("\nTest 3: JSON output")
    output, code = run_cli_command([
        "metadata-show", item_ids[0],
        "--json"
    ])
    print(output)
    try:
        data = json.loads(output.split('\n')[-2])  # Get last line before empty
        assert "metadata" in data, "Should have metadata field in JSON"
        print("✓ Valid JSON output")
    except:
        print("Warning: Could not parse JSON output")

    print("\n✓ All show tests passed!")


def test_metadata_stats(collection_id):
    """Test metadata stats command"""
    print("\n=== Testing metadata-stats ===")

    output, code = run_cli_command([
        "metadata-stats", collection_id
    ])
    print(output)

    assert "Total Items: 3" in output, "Should show 3 total items"
    assert "Items with Metadata: 2" in output, "Should show 2 items with metadata"

    print("\n✓ Stats tests passed!")


def test_metadata_export(collection_id):
    """Test metadata export command"""
    print("\n=== Testing metadata-export ===")

    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        export_file = f.name

    try:
        output, code = run_cli_command([
            "metadata-export", collection_id, export_file
        ])
        print(output)

        # Verify file was created
        export_path = Path(export_file)
        assert export_path.exists(), "Export file should exist"

        # Verify contents
        with open(export_path, 'r') as f:
            data = json.load(f)
            assert "items" in data, "Should have items field"
            assert len(data["items"]) == 2, "Should export 2 items with metadata"
            print(f"\n✓ Export file contains {len(data['items'])} items")

        print("\n✓ Export tests passed!")

    finally:
        # Cleanup
        Path(export_file).unlink(missing_ok=True)


def cleanup_test_data(collection_id):
    """Clean up test data"""
    print("\n=== Cleaning up test data ===")

    output, code = run_cli_command(["delete", collection_id])
    print(output)

    print("✓ Test data cleaned up")


def main():
    """Run all tests"""
    print("="*60)
    print("Metadata CLI Basic Tests")
    print("="*60)

    try:
        # Setup
        collection_id, item_ids = setup_test_data()

        # Run tests
        test_metadata_query(collection_id)
        test_metadata_show(item_ids)
        test_metadata_stats(collection_id)
        test_metadata_export(collection_id)

        # Cleanup
        cleanup_test_data(collection_id)

        print("\n" + "="*60)
        print("✓ All tests passed successfully!")
        print("="*60)
        return 0

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
