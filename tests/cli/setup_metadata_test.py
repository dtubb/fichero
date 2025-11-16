#!/usr/bin/env python3
"""
Setup test data for metadata CLI testing
"""
import sys
import os
from pathlib import Path

# Set environment
os.environ["TOGA_BACKEND"] = "toga_cocoa"

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from unittest.mock import Mock
from datetime import datetime

try:
    from fichero.library.library_manager import LibraryManager
    from fichero.library.models import Collection, CollectionItem
except ImportError as e:
    print(f"Import error: {e}", file=sys.stderr)
    print(f"Python path: {sys.path}", file=sys.stderr)
    sys.exit(1)

def main():
    # Create mock app
    mock_app = Mock()
    mock_app.paths = Mock()
    mock_app.paths.data = Path.home() / "Library" / "Application Support" / "ca.tubb.fichero"

    # Initialize library manager
    lib = LibraryManager(mock_app)

    # Create collection
    collection = Collection(
        name="CLI Metadata Test",
        description="Test collection for metadata CLI",
        type="external",
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    collection_id = lib.storage.add_collection(collection)

    # Create items
    items = []
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
        item_id = lib.storage.add_item(item)
        items.append(item_id)

    # Add metadata to first item
    lib.metadata_api.save_step_metadata(
        item_id=items[0],
        step_name="crop",
        metadata={
            "method": "yolo",
            "confidence": 0.92,
            "box": {"x1": 100, "y1": 50, "x2": 800, "y2": 1000}
        },
        version=1
    )

    lib.metadata_api.save_step_metadata(
        item_id=items[0],
        step_name="rotate",
        metadata={
            "angle": -0.5,
            "found_lines": True,
            "num_lines": 3
        },
        version=1
    )

    # Add metadata to second item
    lib.metadata_api.save_step_metadata(
        item_id=items[1],
        step_name="crop",
        metadata={
            "method": "manual",
            "confidence": 0.95,
            "box": {"x1": 50, "y1": 100, "x2": 900, "y2": 1200}
        },
        version=1
    )

    # Output IDs (collection|item1|item2|item3)
    print(f"{collection_id}|{items[0]}|{items[1]}|{items[2]}")

if __name__ == "__main__":
    main()
