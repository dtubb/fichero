"""
Tests for Dynamic Metadata Extraction System

Tests the ability to extract ALL fields from JSON (not just predefined ones),
and the dynamic field discovery in the field registry.
"""

import json
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch
import pytest


# ============================================================================
# CatalogueExtractor Tests
# ============================================================================

class TestCatalogueExtractorDynamic:
    """Test that CatalogueExtractor extracts ALL fields from JSON."""

    def create_test_json(self, data: dict, suffix=".json") -> Path:
        """Create a temporary JSON file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as f:
            json.dump(data, f)
            return Path(f.name)

    def test_extracts_standard_fields(self):
        """Verify standard catalogue fields are extracted."""
        from fichero.library.metadata_extractors import CatalogueExtractor

        storage = Mock()
        storage.get_metadata_by_collection.return_value = []

        extractor = CatalogueExtractor(storage)

        json_data = {
            "title": "Test Document",
            "description": "A test description",
            "date": "1850-01-15",
            "author": "John Doe",
            "language": "en"
        }
        json_path = self.create_test_json(json_data)

        try:
            metadata_list = extractor.extract(
                output_path=json_path,
                collection_id="test_collection",
                item_id="test_item",
                processing_output_id="test_output",
                source_label="test_source"
            )

            # Should have all 5 fields
            assert len(metadata_list) == 5

            # Check values
            extracted = {m.key: m.value for m in metadata_list}
            assert extracted["title"] == "Test Document"
            assert extracted["description"] == "A test description"
            assert extracted["date"] == "1850-01-15"
            assert extracted["author"] == "John Doe"
            assert extracted["language"] == "en"

        finally:
            json_path.unlink()

    def test_extracts_dynamic_fields(self):
        """Verify custom/dynamic fields are extracted (not just predefined)."""
        from fichero.library.metadata_extractors import CatalogueExtractor

        storage = Mock()
        storage.get_metadata_by_collection.return_value = []

        extractor = CatalogueExtractor(storage)

        json_data = {
            "title": "Test Document",
            "custom_field": "Custom Value",
            "named_entities": ["Person A", "Place B", "Org C"],
            "sentiment": "positive",
            "people": ["John Smith", "Jane Doe"],
            "organizations": ["Anthropic", "OpenAI"],
            "locations": ["San Francisco", "London"]
        }
        json_path = self.create_test_json(json_data)

        try:
            metadata_list = extractor.extract(
                output_path=json_path,
                collection_id="test_collection",
                item_id="test_item",
                processing_output_id="test_output",
                source_label="test_source"
            )

            # Should extract ALL fields
            assert len(metadata_list) == 7

            # Check all fields are present
            extracted = {m.key: m.value for m in metadata_list}
            assert "title" in extracted
            assert "custom_field" in extracted
            assert "named_entities" in extracted
            assert "sentiment" in extracted
            assert "people" in extracted
            assert "organizations" in extracted
            assert "locations" in extracted

            # Check custom values
            assert extracted["custom_field"] == "Custom Value"
            assert extracted["sentiment"] == "positive"

            # Lists should be JSON strings
            assert json.loads(extracted["named_entities"]) == ["Person A", "Place B", "Org C"]
            assert json.loads(extracted["people"]) == ["John Smith", "Jane Doe"]

        finally:
            json_path.unlink()

    def test_normalizes_key_aliases(self):
        """Verify key aliases are normalized (Title -> title)."""
        from fichero.library.metadata_extractors import CatalogueExtractor

        storage = Mock()
        storage.get_metadata_by_collection.return_value = []

        extractor = CatalogueExtractor(storage)

        json_data = {
            "Title": "Test Document",  # Should become "title"
            "Description": "A test",    # Should become "description"
            "Type": "letter"            # Should become "document_type"
        }
        json_path = self.create_test_json(json_data)

        try:
            metadata_list = extractor.extract(
                output_path=json_path,
                collection_id="test_collection",
                item_id="test_item",
                processing_output_id="test_output",
                source_label="test_source"
            )

            extracted = {m.key: m.value for m in metadata_list}

            # Keys should be normalized
            assert "title" in extracted
            assert "description" in extracted
            assert "document_type" in extracted

            # Original keys should not be present
            assert "Title" not in extracted
            assert "Description" not in extracted
            assert "Type" not in extracted

        finally:
            json_path.unlink()

    def test_normalizes_spaces_and_hyphens(self):
        """Verify keys with spaces/hyphens are normalized to underscores."""
        from fichero.library.metadata_extractors import CatalogueExtractor

        storage = Mock()
        storage.get_metadata_by_collection.return_value = []

        extractor = CatalogueExtractor(storage)

        json_data = {
            "document type": "letter",
            "created-date": "2025-01-01",
            "Named Entities": ["test"]
        }
        json_path = self.create_test_json(json_data)

        try:
            metadata_list = extractor.extract(
                output_path=json_path,
                collection_id="test_collection",
                item_id="test_item",
                processing_output_id="test_output",
                source_label="test_source"
            )

            extracted = {m.key: m.value for m in metadata_list}

            # Keys should be normalized to lowercase with underscores
            assert "document_type" in extracted
            assert "created_date" in extracted
            assert "named_entities" in extracted

        finally:
            json_path.unlink()

    def test_skips_internal_fields(self):
        """Verify fields starting with underscore are skipped."""
        from fichero.library.metadata_extractors import CatalogueExtractor

        storage = Mock()
        storage.get_metadata_by_collection.return_value = []

        extractor = CatalogueExtractor(storage)

        json_data = {
            "title": "Test Document",
            "_internal": "should be skipped",
            "_metadata": {"foo": "bar"}
        }
        json_path = self.create_test_json(json_data)

        try:
            metadata_list = extractor.extract(
                output_path=json_path,
                collection_id="test_collection",
                item_id="test_item",
                processing_output_id="test_output",
                source_label="test_source"
            )

            # Should only have title
            assert len(metadata_list) == 1
            assert metadata_list[0].key == "title"

        finally:
            json_path.unlink()

    def test_skips_none_values(self):
        """Verify None values are skipped."""
        from fichero.library.metadata_extractors import CatalogueExtractor

        storage = Mock()
        storage.get_metadata_by_collection.return_value = []

        extractor = CatalogueExtractor(storage)

        json_data = {
            "title": "Test Document",
            "description": None,
            "author": None
        }
        json_path = self.create_test_json(json_data)

        try:
            metadata_list = extractor.extract(
                output_path=json_path,
                collection_id="test_collection",
                item_id="test_item",
                processing_output_id="test_output",
                source_label="test_source"
            )

            # Should only have title
            assert len(metadata_list) == 1
            assert metadata_list[0].key == "title"

        finally:
            json_path.unlink()


# ============================================================================
# TranscriptionExtractor Tests
# ============================================================================

class TestTranscriptionExtractorDynamic:
    """Test that TranscriptionExtractor extracts ALL fields from JSON."""

    def create_test_json(self, data: dict, suffix=".json") -> Path:
        """Create a temporary JSON file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as f:
            json.dump(data, f)
            return Path(f.name)

    def test_extracts_standard_fields(self):
        """Verify standard transcription fields are extracted."""
        from fichero.library.metadata_extractors import TranscriptionExtractor

        storage = Mock()
        storage.get_metadata_by_collection.return_value = []

        extractor = TranscriptionExtractor(storage)

        json_data = {
            "text": "This is the transcription text.",
            "language": "en",
            "confidence": 0.95,
            "model": "gpt-4"
        }
        json_path = self.create_test_json(json_data)

        try:
            metadata_list = extractor.extract(
                output_path=json_path,
                collection_id="test_collection",
                item_id="test_item",
                processing_output_id="test_output",
                source_label="test_source"
            )

            extracted = {m.key: m.value for m in metadata_list}

            # Should have text, language, confidence, model, word_count
            assert "text" in extracted
            assert "language" in extracted
            assert "confidence" in extracted
            assert "model" in extracted
            assert "word_count" in extracted

            assert extracted["language"] == "en"
            assert extracted["word_count"] == "5"  # 5 words in text

        finally:
            json_path.unlink()

    def test_extracts_dynamic_fields(self):
        """Verify custom fields in transcription JSON are extracted."""
        from fichero.library.metadata_extractors import TranscriptionExtractor

        storage = Mock()
        storage.get_metadata_by_collection.return_value = []

        extractor = TranscriptionExtractor(storage)

        json_data = {
            "text": "Hello world",
            "language": "en",
            "entities": ["John", "NYC"],
            "sentiment": "neutral",
            "topics": ["greeting", "general"]
        }
        json_path = self.create_test_json(json_data)

        try:
            metadata_list = extractor.extract(
                output_path=json_path,
                collection_id="test_collection",
                item_id="test_item",
                processing_output_id="test_output",
                source_label="test_source"
            )

            extracted = {m.key: m.value for m in metadata_list}

            # Custom fields should be extracted
            assert "entities" in extracted
            assert "sentiment" in extracted
            assert "topics" in extracted

            # Lists should be JSON strings
            assert json.loads(extracted["entities"]) == ["John", "NYC"]

        finally:
            json_path.unlink()


# ============================================================================
# Storage Method Tests
# ============================================================================

class TestStorageMetadataKeyDiscovery:
    """Test storage methods for metadata key discovery."""

    def create_test_db(self) -> tuple:
        """Create an in-memory test database."""
        conn = sqlite3.connect(':memory:')
        cursor = conn.cursor()

        # Create extracted_metadata table
        cursor.execute('''
            CREATE TABLE extracted_metadata (
                id TEXT PRIMARY KEY,
                processing_output_id TEXT,
                collection_id TEXT,
                item_id TEXT,
                collection_level INTEGER DEFAULT 0,
                schema_type TEXT,
                source_label TEXT,
                version INTEGER DEFAULT 1,
                schema_version TEXT,
                key TEXT,
                value TEXT,
                confidence REAL,
                context TEXT,
                custom_fields TEXT,
                indexed INTEGER DEFAULT 0,
                created_at TEXT
            )
        ''')
        conn.commit()
        return conn, cursor

    def test_get_metadata_keys_for_item(self):
        """Test getting unique metadata keys for an item."""
        conn, cursor = self.create_test_db()

        # Insert test data
        cursor.executemany('''
            INSERT INTO extracted_metadata
            (id, collection_id, item_id, schema_type, key, value, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', [
            ('1', 'coll1', 'item1', 'catalogue', 'title', 'Test', '2025-01-01'),
            ('2', 'coll1', 'item1', 'catalogue', 'description', 'Desc', '2025-01-01'),
            ('3', 'coll1', 'item1', 'catalogue', 'custom_field', 'Value', '2025-01-01'),
            ('4', 'coll1', 'item1', 'transcription', 'text', 'Text', '2025-01-01'),
            ('5', 'coll1', 'item2', 'catalogue', 'title', 'Other', '2025-01-01'),  # Different item
        ])
        conn.commit()

        # Query
        cursor.execute('''
            SELECT DISTINCT key FROM extracted_metadata
            WHERE item_id = ?
            ORDER BY key
        ''', ('item1',))

        keys = [row[0] for row in cursor.fetchall()]

        # Should have 4 unique keys for item1
        assert len(keys) == 4
        assert 'title' in keys
        assert 'description' in keys
        assert 'custom_field' in keys
        assert 'text' in keys

        conn.close()

    def test_get_all_metadata_keys(self):
        """Test getting all unique metadata keys across library."""
        conn, cursor = self.create_test_db()

        # Insert test data with various keys
        cursor.executemany('''
            INSERT INTO extracted_metadata
            (id, collection_id, item_id, schema_type, key, value, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', [
            ('1', 'coll1', 'item1', 'catalogue', 'title', 'Test', '2025-01-01'),
            ('2', 'coll1', 'item1', 'catalogue', 'named_entities', '[]', '2025-01-01'),
            ('3', 'coll2', 'item2', 'catalogue', 'title', 'Other', '2025-01-01'),
            ('4', 'coll2', 'item2', 'catalogue', 'people', '[]', '2025-01-01'),
        ])
        conn.commit()

        # Query all unique keys
        cursor.execute('''
            SELECT DISTINCT key, schema_type FROM extracted_metadata
            ORDER BY schema_type, key
        ''')

        keys = [{"key": row[0], "schema_type": row[1]} for row in cursor.fetchall()]

        # Should have 3 unique key/schema combinations (title is deduplicated)
        assert len(keys) == 3

        key_names = [k["key"] for k in keys]
        assert 'title' in key_names
        assert 'named_entities' in key_names
        assert 'people' in key_names

        conn.close()


# ============================================================================
# Field Registry Tests
# ============================================================================

class TestFieldRegistryDynamicDiscovery:
    """Test field registry dynamic field discovery."""

    def test_create_dynamic_field_info(self):
        """Test creating dynamic field info from key."""
        from fichero.windows.main.views.preview.field_registry import (
            MetadataFieldRegistry, FieldInfo
        )

        field_info = MetadataFieldRegistry.create_dynamic_field_info("named_entities")

        assert field_info.key == "named_entities"
        assert field_info.label == "Named Entities"  # Title case
        assert field_info.schema_type == "discovered"
        assert field_info.editable is True

    def test_create_dynamic_field_info_with_schema_type(self):
        """Test creating dynamic field info with custom schema type."""
        from fichero.windows.main.views.preview.field_registry import MetadataFieldRegistry

        field_info = MetadataFieldRegistry.create_dynamic_field_info(
            "people", schema_type="catalogue"
        )

        assert field_info.key == "people"
        assert field_info.schema_type == "catalogue"

    def test_register_dynamic_field(self):
        """Test registering a dynamic field in the registry."""
        from fichero.windows.main.views.preview.field_registry import MetadataFieldRegistry

        # Clear fields for clean test
        MetadataFieldRegistry.FIELDS = {}

        field_info = MetadataFieldRegistry.register_dynamic_field(
            "custom_test_field",
            schema_type="discovered",
            label="Custom Test Field"
        )

        assert field_info.key == "custom_test_field"
        assert field_info.label == "Custom Test Field"

        # Should be in registry now
        assert MetadataFieldRegistry.field_exists("custom_test_field")

        # Clean up
        del MetadataFieldRegistry.FIELDS["custom_test_field"]

    def test_get_dynamic_fields_for_item(self):
        """Test discovering dynamic fields from storage."""
        from fichero.windows.main.views.preview.field_registry import MetadataFieldRegistry

        # Reset fields
        MetadataFieldRegistry.FIELDS = {}
        MetadataFieldRegistry._init_fields()

        # Mock storage
        storage = Mock()
        storage.get_metadata_keys_for_item.return_value = [
            "title",  # Known field
            "description",  # Known field
            "custom_dynamic_field",  # Dynamic
            "another_dynamic",  # Dynamic
        ]

        dynamic_fields = MetadataFieldRegistry.get_dynamic_fields_for_item(
            storage, "item123"
        )

        # Should only return dynamic fields not in predefined
        dynamic_keys = [f.key for f in dynamic_fields]

        assert "custom_dynamic_field" in dynamic_keys
        assert "another_dynamic" in dynamic_keys
        assert "title" not in dynamic_keys  # Predefined, not dynamic
        assert "description" not in dynamic_keys  # Predefined, not dynamic

    def test_get_available_fields_with_discovery(self):
        """Test getting all available fields including discovered ones."""
        from fichero.windows.main.views.preview.field_registry import MetadataFieldRegistry

        # Reset fields
        MetadataFieldRegistry.FIELDS = {}
        MetadataFieldRegistry._init_fields()

        predefined_count = len(MetadataFieldRegistry.FIELDS)

        # Mock storage
        storage = Mock()
        storage.get_metadata_keys_for_item.return_value = [
            "title",
            "new_dynamic_field"
        ]

        all_fields = MetadataFieldRegistry.get_available_fields_with_discovery(
            storage=storage,
            item_id="item123"
        )

        # Should have predefined + 1 new dynamic field
        assert len(all_fields) == predefined_count + 1

        field_keys = [f.key for f in all_fields]
        assert "new_dynamic_field" in field_keys


# ============================================================================
# Integration Tests
# ============================================================================

class TestDynamicMetadataIntegration:
    """Integration tests for dynamic metadata flow."""

    def test_full_extraction_to_discovery_flow(self):
        """Test full flow: JSON -> Extractor -> Storage -> Registry."""
        from fichero.library.metadata_extractors import CatalogueExtractor
        from fichero.windows.main.views.preview.field_registry import MetadataFieldRegistry

        # 1. Create sample JSON with dynamic fields
        json_data = {
            "title": "Historical Document",
            "description": "Important letter",
            "named_entities": ["George Washington", "Philadelphia"],
            "topics": ["history", "politics"],
            "sentiment": "formal"
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(json_data, f)
            json_path = Path(f.name)

        try:
            # 2. Extract with CatalogueExtractor
            storage = Mock()
            storage.get_metadata_by_collection.return_value = []

            extractor = CatalogueExtractor(storage)
            metadata_list = extractor.extract(
                output_path=json_path,
                collection_id="test_collection",
                item_id="test_item",
                processing_output_id="test_output",
                source_label="test_source"
            )

            # 3. All fields should be extracted
            extracted_keys = {m.key for m in metadata_list}
            assert "title" in extracted_keys
            assert "description" in extracted_keys
            assert "named_entities" in extracted_keys
            assert "topics" in extracted_keys
            assert "sentiment" in extracted_keys

            # 4. Simulate storage returning these keys
            storage.get_metadata_keys_for_item.return_value = list(extracted_keys)

            # 5. Registry should discover the dynamic fields
            MetadataFieldRegistry.FIELDS = {}
            MetadataFieldRegistry._init_fields()

            dynamic_fields = MetadataFieldRegistry.get_dynamic_fields_for_item(
                storage, "test_item"
            )

            # Should discover at least named_entities, topics, sentiment as dynamic
            dynamic_keys = {f.key for f in dynamic_fields}
            assert "named_entities" in dynamic_keys or "topics" in dynamic_keys or "sentiment" in dynamic_keys

        finally:
            json_path.unlink()


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
