"""
Unit tests for LibraryMetadataAPI

Tests the metadata storage and retrieval functionality for processing step metadata.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# Import from src
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from fichero.library.storage import LibraryStorage
from fichero.library.metadata_api import LibraryMetadataAPI
from fichero.library.models import Collection, CollectionItem


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test.db"
    yield db_path
    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def storage(temp_db):
    """Create a LibraryStorage instance"""
    return LibraryStorage(temp_db)


@pytest.fixture
def metadata_api(storage):
    """Create a LibraryMetadataAPI instance"""
    return LibraryMetadataAPI(storage)


@pytest.fixture
def test_collection(storage):
    """Create a test collection"""
    collection = Collection(
        name="Test Collection",
        type="local"
    )
    storage.add_collection(collection)
    return collection


@pytest.fixture
def test_item(storage, test_collection):
    """Create a test collection item"""
    item = CollectionItem(
        collection_id=test_collection.id,
        type="file",
        name="test_document.jpg",
        storage_type="local",
        local_path="/test/path/test_document.jpg"
    )
    storage.add_collection_item(item)
    return item


class TestMetadataAPISaveAndRetrieve:
    """Test saving and retrieving step metadata"""

    def test_save_step_metadata_basic(self, metadata_api, test_item):
        """Test saving basic step metadata"""
        metadata = {
            "method": "yolo",
            "confidence": 0.92,
            "padding": 30
        }

        result = metadata_api.save_step_metadata(
            item_id=test_item.id,
            step_name="crop",
            metadata=metadata
        )

        assert result is True

    def test_save_step_metadata_with_version(self, metadata_api, test_item):
        """Test saving metadata with version tracking"""
        metadata = {
            "method": "yolo",
            "confidence": 0.92
        }

        result = metadata_api.save_step_metadata(
            item_id=test_item.id,
            step_name="crop",
            metadata=metadata,
            version=1
        )

        assert result is True

    def test_save_step_metadata_invalid_item(self, metadata_api):
        """Test saving metadata for non-existent item"""
        result = metadata_api.save_step_metadata(
            item_id="invalid-id",
            step_name="crop",
            metadata={"test": "data"}
        )

        assert result is False

    def test_get_step_metadata(self, metadata_api, test_item):
        """Test retrieving saved metadata"""
        # Save metadata
        metadata = {
            "method": "yolo",
            "confidence": 0.92,
            "box": {"x1": 100, "y1": 50, "x2": 800, "y2": 1000}
        }

        metadata_api.save_step_metadata(
            item_id=test_item.id,
            step_name="crop",
            metadata=metadata
        )

        # Retrieve metadata
        retrieved = metadata_api.get_step_metadata(
            item_id=test_item.id,
            step_name="crop"
        )

        assert retrieved is not None
        assert retrieved["method"] == "yolo"
        assert retrieved["confidence"] == 0.92
        assert isinstance(retrieved["box"], dict)

    def test_get_step_metadata_not_found(self, metadata_api, test_item):
        """Test retrieving metadata that doesn't exist"""
        retrieved = metadata_api.get_step_metadata(
            item_id=test_item.id,
            step_name="nonexistent"
        )

        assert retrieved is None

    def test_get_all_step_metadata(self, metadata_api, test_item):
        """Test retrieving all step metadata for an item"""
        # Save metadata for multiple steps
        crop_metadata = {"method": "yolo", "confidence": 0.92}
        rotate_metadata = {"angle": -0.5, "found_lines": True}
        transcribe_metadata = {"text_length": 450, "model": "qwen-vl-max"}

        metadata_api.save_step_metadata(test_item.id, "crop", crop_metadata)
        metadata_api.save_step_metadata(test_item.id, "rotate", rotate_metadata)
        metadata_api.save_step_metadata(test_item.id, "transcribe", transcribe_metadata)

        # Retrieve all metadata
        all_metadata = metadata_api.get_all_step_metadata(test_item.id)

        assert "crop" in all_metadata
        assert "rotate" in all_metadata
        assert "transcribe" in all_metadata
        assert all_metadata["crop"]["method"] == "yolo"
        assert all_metadata["rotate"]["angle"] == -0.5
        assert all_metadata["transcribe"]["model"] == "qwen-vl-max"


class TestMetadataAPIQuery:
    """Test querying items by metadata"""

    def test_query_items_by_metadata_simple(self, metadata_api, storage, test_collection):
        """Test simple equality query"""
        # Create multiple items with metadata
        item1 = CollectionItem(
            collection_id=test_collection.id,
            type="file",
            name="doc1.jpg",
            storage_type="local",
            local_path="/test/doc1.jpg"
        )
        item2 = CollectionItem(
            collection_id=test_collection.id,
            type="file",
            name="doc2.jpg",
            storage_type="local",
            local_path="/test/doc2.jpg"
        )
        item3 = CollectionItem(
            collection_id=test_collection.id,
            type="file",
            name="doc3.jpg",
            storage_type="local",
            local_path="/test/doc3.jpg"
        )

        storage.add_collection_item(item1)
        storage.add_collection_item(item2)
        storage.add_collection_item(item3)

        # Add metadata
        metadata_api.save_step_metadata(item1.id, "crop", {"method": "yolo", "confidence": 0.92})
        metadata_api.save_step_metadata(item2.id, "crop", {"method": "yolo", "confidence": 0.85})
        metadata_api.save_step_metadata(item3.id, "crop", {"method": "contour", "confidence": 0.70})

        # Query for yolo method
        results = metadata_api.query_items_by_metadata(
            test_collection.id,
            {"crop.method": "yolo"}
        )

        assert len(results) == 2
        assert item1.id in results
        assert item2.id in results

    def test_query_items_by_metadata_with_operator(self, metadata_api, storage, test_collection):
        """Test query with comparison operator"""
        # Create items
        item1 = CollectionItem(
            collection_id=test_collection.id,
            type="file",
            name="doc1.jpg",
            storage_type="local",
            local_path="/test/doc1.jpg"
        )
        item2 = CollectionItem(
            collection_id=test_collection.id,
            type="file",
            name="doc2.jpg",
            storage_type="local",
            local_path="/test/doc2.jpg"
        )
        item3 = CollectionItem(
            collection_id=test_collection.id,
            type="file",
            name="doc3.jpg",
            storage_type="local",
            local_path="/test/doc3.jpg"
        )

        storage.add_collection_item(item1)
        storage.add_collection_item(item2)
        storage.add_collection_item(item3)

        # Add metadata
        metadata_api.save_step_metadata(item1.id, "crop", {"confidence": 0.95})
        metadata_api.save_step_metadata(item2.id, "crop", {"confidence": 0.85})
        metadata_api.save_step_metadata(item3.id, "crop", {"confidence": 0.70})

        # Query for confidence >= 0.85
        results = metadata_api.query_items_by_metadata(
            test_collection.id,
            {"crop.confidence": {"$gte": 0.85}}
        )

        assert len(results) == 2
        assert item1.id in results
        assert item2.id in results

    def test_query_items_by_metadata_multiple_filters(self, metadata_api, storage, test_collection):
        """Test query with multiple filters (AND logic)"""
        # Create items
        item1 = CollectionItem(
            collection_id=test_collection.id,
            type="file",
            name="doc1.jpg",
            storage_type="local",
            local_path="/test/doc1.jpg"
        )
        item2 = CollectionItem(
            collection_id=test_collection.id,
            type="file",
            name="doc2.jpg",
            storage_type="local",
            local_path="/test/doc2.jpg"
        )

        storage.add_collection_item(item1)
        storage.add_collection_item(item2)

        # Add metadata
        metadata_api.save_step_metadata(item1.id, "crop", {"method": "yolo", "confidence": 0.95})
        metadata_api.save_step_metadata(item2.id, "crop", {"method": "yolo", "confidence": 0.70})

        # Query for yolo AND confidence >= 0.85
        results = metadata_api.query_items_by_metadata(
            test_collection.id,
            {
                "crop.method": "yolo",
                "crop.confidence": {"$gte": 0.85}
            }
        )

        assert len(results) == 1
        assert item1.id in results


class TestMetadataAPIUpdate:
    """Test updating step metadata"""

    def test_update_step_metadata(self, metadata_api, test_item):
        """Test updating metadata fields"""
        # Save initial metadata
        metadata_api.save_step_metadata(
            test_item.id,
            "crop",
            {"method": "yolo", "confidence": 0.85}
        )

        # Update metadata
        result = metadata_api.update_step_metadata(
            test_item.id,
            "crop",
            {"confidence": 0.95, "method": "yolo-v2"}
        )

        assert result is True

        # Verify update
        updated = metadata_api.get_step_metadata(test_item.id, "crop")
        assert updated["confidence"] == 0.95
        assert updated["method"] == "yolo-v2"


class TestMetadataAPIVersionTracking:
    """Test version tracking functionality"""

    def test_version_snapshot_created(self, metadata_api, test_item, storage):
        """Test that version snapshots are created"""
        # Save metadata with version
        metadata_api.save_step_metadata(
            test_item.id,
            "crop",
            {"method": "yolo", "confidence": 0.92},
            version=1
        )

        # Check version exists
        versions = storage.get_metadata_versions(test_item.id, "crop")
        assert len(versions) == 1
        assert versions[0]["version"] == 1
        assert versions[0]["metadata"]["method"] == "yolo"

    def test_multiple_versions(self, metadata_api, test_item, storage):
        """Test multiple version snapshots"""
        # Create multiple versions
        metadata_api.save_step_metadata(
            test_item.id,
            "crop",
            {"method": "yolo", "confidence": 0.85},
            version=1
        )

        metadata_api.save_step_metadata(
            test_item.id,
            "crop",
            {"method": "yolo-v2", "confidence": 0.92},
            version=2
        )

        # Get version history
        versions = metadata_api.get_metadata_history(test_item.id, "crop")
        assert len(versions) == 2
        assert versions[0]["version"] == 1
        assert versions[1]["version"] == 2
        assert versions[1]["metadata"]["method"] == "yolo-v2"

    def test_get_specific_version(self, metadata_api, test_item):
        """Test retrieving specific version"""
        # Create versions
        metadata_api.save_step_metadata(
            test_item.id,
            "crop",
            {"confidence": 0.85},
            version=1
        )

        metadata_api.save_step_metadata(
            test_item.id,
            "crop",
            {"confidence": 0.92},
            version=2
        )

        # Get v1
        v1_metadata = metadata_api.get_step_metadata(
            test_item.id,
            "crop",
            version=1
        )

        assert v1_metadata is not None
        assert v1_metadata["confidence"] == 0.85


class TestMetadataAPIHelpers:
    """Test helper methods"""

    def test_infer_metadata_type(self, metadata_api):
        """Test metadata type inference"""
        assert metadata_api._infer_metadata_type("crop", "padding") == "step_param"
        assert metadata_api._infer_metadata_type("crop", "confidence") == "step_result"
        assert metadata_api._infer_metadata_type("crop", "attempts") == "detection"
        assert metadata_api._infer_metadata_type("crop", "output_format") == "file_info"
        assert metadata_api._infer_metadata_type("transcribe", "text") == "transcription"

    def test_serialize_deserialize_value(self, metadata_api):
        """Test value serialization and deserialization"""
        # Dict
        dict_value = {"x1": 100, "y1": 50}
        serialized = metadata_api._serialize_value(dict_value)
        deserialized = metadata_api._deserialize_value(serialized)
        assert deserialized == dict_value

        # List
        list_value = [1, 2, 3]
        serialized = metadata_api._serialize_value(list_value)
        deserialized = metadata_api._deserialize_value(serialized)
        assert deserialized == list_value

        # String
        str_value = "yolo"
        serialized = metadata_api._serialize_value(str_value)
        deserialized = metadata_api._deserialize_value(serialized)
        assert deserialized == str_value

        # Float
        float_value = 0.92
        serialized = metadata_api._serialize_value(float_value)
        deserialized = metadata_api._deserialize_value(serialized)
        assert float(deserialized) == float_value

    def test_apply_operator(self, metadata_api):
        """Test comparison operators"""
        assert metadata_api._apply_operator(0.95, "$gte", 0.85) is True
        assert metadata_api._apply_operator(0.70, "$gte", 0.85) is False
        assert metadata_api._apply_operator(0.85, "$lte", 0.90) is True
        assert metadata_api._apply_operator(0.95, "$lte", 0.90) is False
        assert metadata_api._apply_operator("yolo", "$eq", "yolo") is True
        assert metadata_api._apply_operator("yolo", "$ne", "contour") is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
