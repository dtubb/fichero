"""
Unit tests for metadata version query methods in storage.py

Tests the new version-aware query methods:
- get_field_versions() - Get all versions of a specific field
- get_item_metadata_with_versions() - Get metadata grouped by key with versions
- get_model_versions_for_item() - Get AI model version summaries
- get_metadata_by_source() - Get metadata from a specific source/model
- get_max_metadata_version() - Get highest version number
"""

import unittest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import sqlite3

import pytest

from fichero.library.storage import LibraryStorage
from fichero.library.models import (
    Collection, CollectionItem, ExtractedMetadata,
    ProcessingOutput, ProcessingResult
)


class TestMetadataVersionQueries(unittest.TestCase):
    """Test metadata version query methods in LibraryStorage"""

    def setUp(self):
        """Create a temporary database with test data"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_library.db"
        self.storage = LibraryStorage(self.db_path)

        # Create test collection
        self.collection = Collection(
            id="test-collection-1",
            name="Test Collection",
            type="local"
        )
        self.storage.add_collection(self.collection)

        # Create test item
        self.item = CollectionItem(
            id="test-item-1",
            collection_id="test-collection-1",
            name="Test Document",
            type="file"
        )
        self.storage.add_collection_item(self.item)

        # Create test ProcessingResult
        self.processing_result = ProcessingResult(
            id="result-1",
            item_id="test-item-1",
            workflow="Catalogue",
            status="success"
        )
        self.storage.add_processing_result(self.processing_result)

        # Create test ProcessingOutput
        self.processing_output = ProcessingOutput(
            id="output-1",
            processing_result_id="result-1",
            collection_id="test-collection-1",
            item_id="test-item-1",
            step_name="transcribe",
            output_type="transcription",
            output_path="/test/path.json"
        )
        self.storage.add_processing_output(self.processing_output)

    def tearDown(self):
        """Clean up temporary directory"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _add_test_metadata(self, item_id: str, schema_type: str, key: str,
                          value: str, source_label: str, model_name: str = None,
                          provider_name: str = None, version: int = 1) -> ExtractedMetadata:
        """Helper to add test metadata"""
        import uuid
        metadata = ExtractedMetadata(
            id=f"meta-{uuid.uuid4()}",  # Unique ID for each metadata
            processing_output_id="output-1",
            collection_id="test-collection-1",
            item_id=item_id,
            schema_type=schema_type,
            source_label=source_label,
            version=version,
            schema_version="1.0",
            key=key,
            value=value,
            model_name=model_name,
            provider_name=provider_name
        )
        self.storage.add_extracted_metadata(metadata)
        return metadata

    # Tests for get_field_versions()
    def test_get_field_versions_single_version(self):
        """Test getting versions when only one version exists"""
        self._add_test_metadata(
            item_id="test-item-1",
            schema_type="transcription",
            key="text",
            value="Test transcription",
            source_label="ai_qwen",
            model_name="qwen-vl-ocr",
            version=1
        )

        versions = self.storage.get_field_versions(
            item_id="test-item-1",
            schema_type="transcription",
            key="text"
        )

        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0].value, "Test transcription")
        self.assertEqual(versions[0].version, 1)

    def test_get_field_versions_multiple_versions(self):
        """Test getting multiple versions of the same field"""
        # Add v1
        self._add_test_metadata(
            item_id="test-item-1",
            schema_type="transcription",
            key="text",
            value="Version 1 transcription",
            source_label="ai_qwen",
            model_name="qwen-vl-ocr",
            version=1
        )
        # Add v2
        self._add_test_metadata(
            item_id="test-item-1",
            schema_type="transcription",
            key="text",
            value="Version 2 transcription",
            source_label="ai_qwen",
            model_name="qwen-vl-ocr",
            version=2
        )
        # Add v3
        self._add_test_metadata(
            item_id="test-item-1",
            schema_type="transcription",
            key="text",
            value="Version 3 transcription",
            source_label="user_edit",
            model_name=None,
            version=3
        )

        versions = self.storage.get_field_versions(
            item_id="test-item-1",
            schema_type="transcription",
            key="text"
        )

        # Should return newest first
        self.assertEqual(len(versions), 3)
        self.assertEqual(versions[0].version, 3)
        self.assertEqual(versions[0].value, "Version 3 transcription")
        self.assertEqual(versions[1].version, 2)
        self.assertEqual(versions[2].version, 1)

    def test_get_field_versions_empty_for_nonexistent(self):
        """Test getting versions for nonexistent field returns empty list"""
        versions = self.storage.get_field_versions(
            item_id="nonexistent-item",
            schema_type="transcription",
            key="text"
        )

        self.assertEqual(len(versions), 0)

    # Tests for get_item_metadata_with_versions()
    def test_get_item_metadata_with_versions_grouped_by_key(self):
        """Test metadata is grouped by key with all versions"""
        # Add title versions
        self._add_test_metadata("test-item-1", "catalogue", "title", "Title v1", "ai_qwen", "qwen", version=1)
        self._add_test_metadata("test-item-1", "catalogue", "title", "Title v2", "user_edit", None, version=2)

        # Add date (single version)
        self._add_test_metadata("test-item-1", "catalogue", "date", "1931-05-15", "ai_qwen", "qwen", version=1)

        result = self.storage.get_item_metadata_with_versions(
            item_id="test-item-1",
            schema_type="catalogue"
        )

        self.assertIn("title", result)
        self.assertIn("date", result)
        self.assertEqual(len(result["title"]), 2)  # Two versions of title
        self.assertEqual(len(result["date"]), 1)   # One version of date

        # Title versions should be newest first
        self.assertEqual(result["title"][0].version, 2)
        self.assertEqual(result["title"][1].version, 1)

    def test_get_item_metadata_with_versions_filter_by_schema(self):
        """Test filtering by schema_type"""
        # Add catalogue metadata
        self._add_test_metadata("test-item-1", "catalogue", "title", "Test Title", "ai_qwen", "qwen", version=1)

        # Add transcription metadata
        self._add_test_metadata("test-item-1", "transcription", "text", "Test text", "ai_qwen", "qwen", version=1)

        # Get only catalogue
        result = self.storage.get_item_metadata_with_versions(
            item_id="test-item-1",
            schema_type="catalogue"
        )

        self.assertIn("title", result)
        self.assertNotIn("text", result)

    # Tests for get_model_versions_for_item()
    def test_get_model_versions_for_item_groups_by_source(self):
        """Test getting model versions grouped by source_label"""
        # Add metadata from qwen model
        self._add_test_metadata("test-item-1", "transcription", "text", "Qwen text", "ai_qwen", "qwen-vl-ocr", "dashscope", version=1)
        self._add_test_metadata("test-item-1", "catalogue", "title", "Qwen title", "ai_qwen", "qwen-vl-ocr", "dashscope", version=1)

        # Add metadata from gpt model
        self._add_test_metadata("test-item-1", "transcription", "text", "GPT text", "ai_gpt", "gpt-4-vision", "openai", version=1)
        self._add_test_metadata("test-item-1", "catalogue", "title", "GPT title", "ai_gpt", "gpt-4-vision", "openai", version=1)

        versions = self.storage.get_model_versions_for_item("test-item-1")

        # Should have 2 model versions (qwen and gpt)
        self.assertEqual(len(versions), 2)

        # Find qwen version
        qwen_version = next((v for v in versions if v['source_label'] == 'ai_qwen'), None)
        self.assertIsNotNone(qwen_version)
        self.assertEqual(qwen_version['model_name'], 'qwen-vl-ocr')
        self.assertEqual(qwen_version['provider_name'], 'dashscope')
        self.assertEqual(qwen_version['record_count'], 2)  # transcription + catalogue
        self.assertIn('transcription', qwen_version['schema_types'])
        self.assertIn('catalogue', qwen_version['schema_types'])

    def test_get_model_versions_for_item_excludes_user_edits(self):
        """Test that user_edit versions are excluded from AI model versions list"""
        # Add AI metadata
        self._add_test_metadata("test-item-1", "transcription", "text", "AI text", "ai_qwen", "qwen", version=1)

        # Add user edit
        self._add_test_metadata("test-item-1", "transcription", "text", "User text", "user_edit", None, version=2)

        versions = self.storage.get_model_versions_for_item("test-item-1")

        # Should only include AI model versions, not user_edit
        # (user edits are shown separately in the Preview Metadata Pane)
        self.assertEqual(len(versions), 1)
        source_labels = [v['source_label'] for v in versions]
        self.assertIn('ai_qwen', source_labels)
        self.assertNotIn('user_edit', source_labels)

    def test_get_model_versions_for_item_empty_for_no_metadata(self):
        """Test returns empty list for item with no metadata"""
        versions = self.storage.get_model_versions_for_item("nonexistent-item")
        self.assertEqual(len(versions), 0)

    # Tests for get_metadata_by_source()
    def test_get_metadata_by_source_filters_correctly(self):
        """Test getting metadata filtered by source_label"""
        # Add qwen metadata
        self._add_test_metadata("test-item-1", "transcription", "text", "Qwen text", "ai_qwen", "qwen-vl-ocr", version=1)
        self._add_test_metadata("test-item-1", "catalogue", "title", "Qwen title", "ai_qwen", "qwen-vl-ocr", version=1)

        # Add gpt metadata
        self._add_test_metadata("test-item-1", "transcription", "text", "GPT text", "ai_gpt", "gpt-4", version=1)

        # Get only qwen metadata
        result = self.storage.get_metadata_by_source(
            item_id="test-item-1",
            source_label="ai_qwen"
        )

        self.assertEqual(len(result), 2)
        for record in result:
            self.assertEqual(record.source_label, "ai_qwen")

    def test_get_metadata_by_source_with_model_name_filter(self):
        """Test filtering by both source_label and model_name"""
        # Add multiple models with same source
        self._add_test_metadata("test-item-1", "transcription", "text", "OCR text", "ai_qwen", "qwen-vl-ocr", version=1)
        self._add_test_metadata("test-item-1", "transcription", "text", "Max text", "ai_qwen", "qwen-max", version=2)

        # Get only qwen-vl-ocr
        result = self.storage.get_metadata_by_source(
            item_id="test-item-1",
            source_label="ai_qwen",
            model_name="qwen-vl-ocr"
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].model_name, "qwen-vl-ocr")

    # Tests for get_max_metadata_version()
    def test_get_max_metadata_version_returns_highest(self):
        """Test getting highest version number"""
        self._add_test_metadata("test-item-1", "transcription", "text", "v1", "ai_qwen", version=1)
        self._add_test_metadata("test-item-1", "transcription", "text", "v2", "ai_qwen", version=2)
        self._add_test_metadata("test-item-1", "transcription", "text", "v3", "ai_qwen", version=3)

        max_version = self.storage.get_max_metadata_version(
            item_id="test-item-1",
            schema_type="transcription",
            source_label="ai_qwen"
        )

        self.assertEqual(max_version, 3)

    def test_get_max_metadata_version_returns_zero_for_no_data(self):
        """Test returns 0 when no metadata exists"""
        max_version = self.storage.get_max_metadata_version(
            item_id="nonexistent-item",
            schema_type="transcription",
            source_label="ai_qwen"
        )

        self.assertEqual(max_version, 0)

    # Integration tests
    def test_version_workflow_complete(self):
        """Test complete workflow: add versions, query, compare"""
        # Step 1: AI processes item (v1)
        self._add_test_metadata("test-item-1", "transcription", "text", "AI transcription v1", "ai_qwen", "qwen", "dashscope", version=1)
        self._add_test_metadata("test-item-1", "catalogue", "title", "AI title", "ai_qwen", "qwen", "dashscope", version=1)
        self._add_test_metadata("test-item-1", "catalogue", "date", "1931", "ai_qwen", "qwen", "dashscope", version=1)

        # Step 2: User edits title (v2)
        self._add_test_metadata("test-item-1", "catalogue", "title", "User corrected title", "user_edit", None, None, version=2)

        # Step 3: Reprocess with different model (new AI version)
        self._add_test_metadata("test-item-1", "transcription", "text", "GPT transcription", "ai_gpt", "gpt-4", "openai", version=1)
        self._add_test_metadata("test-item-1", "catalogue", "title", "GPT title", "ai_gpt", "gpt-4", "openai", version=1)

        # Verify: Get all model versions (excludes user_edit)
        model_versions = self.storage.get_model_versions_for_item("test-item-1")
        self.assertEqual(len(model_versions), 2)  # ai_qwen, ai_gpt (user_edit excluded)

        # Verify: Get title versions (includes all sources)
        title_versions = self.storage.get_field_versions("test-item-1", "catalogue", "title")
        self.assertEqual(len(title_versions), 3)  # user v2, qwen v1, gpt v1

        # Verify: Get metadata by source
        qwen_metadata = self.storage.get_metadata_by_source("test-item-1", "ai_qwen")
        self.assertEqual(len(qwen_metadata), 3)  # text, title, date

        # Verify: Get max version for title (across all sources)
        max_title_version = self.storage.get_max_metadata_version(
            "test-item-1", "catalogue", source_label=None  # All sources
        )
        self.assertEqual(max_title_version, 2)  # user_edit is v2


class TestLibraryManagerVersionMethods(unittest.TestCase):
    """Test async version methods in LibraryManager"""

    def setUp(self):
        """Create temporary database and library manager"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_library.db"
        self.storage = LibraryStorage(self.db_path)

        # Create test collection and item
        self.collection = Collection(
            id="test-collection-1",
            name="Test Collection",
            type="local"
        )
        self.storage.add_collection(self.collection)

        self.item = CollectionItem(
            id="test-item-1",
            collection_id="test-collection-1",
            name="Test Document",
            type="file"
        )
        self.storage.add_collection_item(self.item)

        # Create ProcessingResult and ProcessingOutput
        result = ProcessingResult(
            id="result-1",
            item_id="test-item-1",
            workflow="Catalogue",
            status="success"
        )
        self.storage.add_processing_result(result)

        output = ProcessingOutput(
            id="output-1",
            processing_result_id="result-1",
            collection_id="test-collection-1",
            item_id="test-item-1",
            step_name="transcribe",
            output_type="transcription",
            output_path="/test/path.json"
        )
        self.storage.add_processing_output(output)

    def tearDown(self):
        """Clean up"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _add_metadata(self, source_label, model_name, schema_type, key, value, version=1):
        """Helper to add metadata"""
        metadata = ExtractedMetadata(
            id=f"meta-{source_label}-{schema_type}-{key}-v{version}",
            processing_output_id="output-1",
            collection_id="test-collection-1",
            item_id="test-item-1",
            schema_type=schema_type,
            source_label=source_label,
            version=version,
            schema_version="1.0",
            key=key,
            value=value,
            model_name=model_name
        )
        self.storage.add_extracted_metadata(metadata)
        return metadata

    @pytest.mark.asyncio
    async def test_library_manager_get_model_versions(self):
        """Test LibraryManager.get_model_versions_for_item()"""
        from fichero.library.library_manager import LibraryManager
        from unittest.mock import Mock, AsyncMock

        # Mock app
        mock_app = Mock()
        mock_app.paths = Mock()
        mock_app.paths.data = Path(self.temp_dir)

        # Add test metadata
        self._add_metadata("ai_qwen", "qwen-vl-ocr", "transcription", "text", "Test", version=1)
        self._add_metadata("ai_gpt", "gpt-4", "transcription", "text", "Test2", version=1)

        # Create library manager with our storage
        manager = LibraryManager(mock_app)
        manager.storage = self.storage

        # Test async method
        versions = await manager.get_model_versions_for_item("test-item-1")

        self.assertEqual(len(versions), 2)

    @pytest.mark.asyncio
    async def test_library_manager_get_metadata_by_source(self):
        """Test LibraryManager.get_metadata_by_source()"""
        from fichero.library.library_manager import LibraryManager
        from unittest.mock import Mock

        mock_app = Mock()
        mock_app.paths = Mock()
        mock_app.paths.data = Path(self.temp_dir)

        # Add test metadata
        self._add_metadata("ai_qwen", "qwen-vl-ocr", "transcription", "text", "Qwen text", version=1)
        self._add_metadata("ai_qwen", "qwen-vl-ocr", "catalogue", "title", "Qwen title", version=1)
        self._add_metadata("ai_gpt", "gpt-4", "transcription", "text", "GPT text", version=1)

        manager = LibraryManager(mock_app)
        manager.storage = self.storage

        # Get only qwen metadata
        metadata = await manager.get_metadata_by_source("test-item-1", "ai_qwen")

        self.assertEqual(len(metadata), 2)
        for record in metadata:
            self.assertEqual(record.source_label, "ai_qwen")

    @pytest.mark.asyncio
    async def test_library_manager_copy_to_user_pane(self):
        """Test LibraryManager.copy_metadata_to_user_pane()"""
        from fichero.library.library_manager import LibraryManager
        from unittest.mock import Mock

        mock_app = Mock()
        mock_app.paths = Mock()
        mock_app.paths.data = Path(self.temp_dir)

        # Add AI metadata
        self._add_metadata("ai_qwen", "qwen-vl-ocr", "catalogue", "title", "AI Title", version=1)
        self._add_metadata("ai_qwen", "qwen-vl-ocr", "catalogue", "date", "1931", version=1)

        manager = LibraryManager(mock_app)
        manager.storage = self.storage

        # Get AI metadata
        ai_metadata = await manager.get_metadata_by_source("test-item-1", "ai_qwen")

        # Copy to user pane
        success = await manager.copy_metadata_to_user_pane("test-item-1", ai_metadata)

        self.assertTrue(success)

        # Verify user_edit records were created
        user_metadata = self.storage.get_metadata_by_source("test-item-1", "user_edit")
        self.assertEqual(len(user_metadata), 2)

        # Verify values were copied
        titles = [m for m in user_metadata if m.key == "title"]
        self.assertEqual(len(titles), 1)
        self.assertEqual(titles[0].value, "AI Title")
        self.assertEqual(titles[0].edited_by, "user")


if __name__ == '__main__':
    unittest.main()
