"""
Test metadata scope routing - leaf vs node level distinction

Validates that the director-library integration properly routes metadata based on
workflow manifest output_scope information and that UI can query the different levels.
"""

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from fichero.library.director_integration import DirectorIntegrationService
from fichero.library.library_manager import LibraryManager
from fichero.library.metadata_extractors import UniversalExtractor
from fichero.library.models import Collection, CollectionItem, ProcessingResult, ProcessingOutput, ExtractedMetadata
from fichero.library.storage import LibraryStorage


class TestMetadataScopeRouting(unittest.TestCase):
    """Test metadata scope routing based on workflow manifest"""

    def setUp(self):
        """Set up test environment with temporary storage"""
        self.temp_dir = tempfile.mkdtemp()
        self.storage_path = Path(self.temp_dir) / "test_library.db"
        self.storage = LibraryStorage(str(self.storage_path))

        # Mock the path resolver to return our test storage path
        self.patcher = patch('fichero.library.path_resolver.get_library_database_path')
        self.mock_get_path = self.patcher.start()
        self.mock_get_path.return_value = self.storage_path

        # Create mock app and library manager
        mock_app = Mock()
        self.library_manager = LibraryManager(mock_app)

        # Create test collection and item
        self.collection = Collection(
            id="test-collection",
            name="Test Collection",
            metadata={"description": "Test collection for scope routing"}
        )
        self.library_manager.storage.add_collection(self.collection)

        self.test_item = CollectionItem(
            id="test-item-001",
            collection_id=self.collection.id,
            name="test_document.jpg",
            type="file",
            source_path="/test/documents/test_document.jpg"
        )
        self.library_manager.storage.add_collection_item(self.test_item)

    def tearDown(self):
        """Clean up test environment"""
        self.patcher.stop()
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_workflow_manifest_scope_detection(self):
        """Test that workflow manifest scope is properly detected"""
        # Create a workflow manifest with scope information
        workflow_manifest = {
            "version": "1.0",
            "workflow": {
                "plan_name": "Test Plan",
                "workflow_name": "Default"
            },
            "steps": [
                {
                    "order": 1,
                    "name": "enhance",
                    "status": "success",
                    "output_scope": "leaf"  # File-level output
                },
                {
                    "order": 2,
                    "name": "fuzzy_clean",
                    "status": "success",
                    "output_scope": "leaf"  # File-level output
                },
                {
                    "order": 3,
                    "name": "catalogue_folder",
                    "status": "success",
                    "output_scope": "node"  # Collection-level output
                },
                {
                    "order": 4,
                    "name": "segment",
                    "status": "success",
                    "output_scope": "intermediate"  # Processing-only output
                }
            ]
        }

        # Create universal extractor
        extractor = UniversalExtractor(self.storage)

        # Test leaf-level detection
        is_collection_level = extractor._is_collection_level_output(
            step_name="enhance",
            output_type="prepared_image",
            output_path=Path("/test/enhanced/test_document.jpg"),
            item_id="test-item-001",
            workflow_manifest=workflow_manifest
        )
        self.assertFalse(is_collection_level, "enhance step should be leaf-level")

        # Test node-level detection
        is_collection_level = extractor._is_collection_level_output(
            step_name="catalogue_folder",
            output_type="catalogue",
            output_path=Path("/test/catalogue/collection_summary.json"),
            item_id=None,
            workflow_manifest=workflow_manifest
        )
        self.assertTrue(is_collection_level, "catalogue_folder step should be node-level")

        # Test intermediate processing detection (depends on item_id)
        is_collection_level = extractor._is_collection_level_output(
            step_name="segment",
            output_type="prepared_image",
            output_path=Path("/test/segmented/test_segment_01.jpg"),
            item_id="test-item-001",
            workflow_manifest=workflow_manifest
        )
        self.assertFalse(is_collection_level, "segment with item_id should be file-level")

        is_collection_level = extractor._is_collection_level_output(
            step_name="segment",
            output_type="prepared_image",
            output_path=Path("/test/segmented/batch_summary.json"),
            item_id=None,
            workflow_manifest=workflow_manifest
        )
        self.assertTrue(is_collection_level, "segment without item_id should be collection-level")

    def test_fallback_heuristic_detection(self):
        """Test fallback to heuristic detection when no manifest scope"""
        extractor = UniversalExtractor(self.storage)

        # Test without workflow manifest - should use heuristics
        is_collection_level = extractor._is_collection_level_output(
            step_name="catalogue_folder",
            output_type="catalogue",
            output_path=Path("/test/catalogue/collection_summary.json"),
            item_id=None,
            workflow_manifest=None  # No manifest provided
        )
        self.assertTrue(is_collection_level, "Should fallback to heuristic detection for catalogue_folder")

        is_collection_level = extractor._is_collection_level_output(
            step_name="enhance",
            output_type="prepared_image",
            output_path=Path("/test/enhanced/test_document.jpg"),
            item_id="test-item-001",
            workflow_manifest=None  # No manifest provided
        )
        self.assertFalse(is_collection_level, "Should fallback to heuristic detection for enhance")

    def test_metadata_storage_queries(self):
        """Test that leaf vs node metadata can be properly queried"""

        # Create leaf-level metadata (file-specific)
        leaf_metadata = ExtractedMetadata(
            id="leaf-001",
            processing_output_id="output-001",
            collection_id=self.collection.id,
            item_id=self.test_item.id,
            collection_level=False,  # File-level
            schema_type="transcription",
            source_label="ai_qwen",
            version=1,
            schema_version="1.0",
            key="text",
            value="Enhanced image transcription text for specific document",
            confidence=0.95
        )
        self.storage.add_extracted_metadata(leaf_metadata)

        # Create node-level metadata (collection-wide)
        node_metadata = ExtractedMetadata(
            id="node-001",
            processing_output_id="output-002",
            collection_id=self.collection.id,
            item_id=None,  # Collection-level, no specific item
            collection_level=True,  # Collection-level
            schema_type="catalogue",
            source_label="ai_catalogue",
            version=1,
            schema_version="1.0",
            key="summary",
            value="Collection contains historical documents from 1926-1931 period",
            confidence=0.88
        )
        self.storage.add_extracted_metadata(node_metadata)

        # Test querying leaf-level metadata
        leaf_results = self.storage.get_leaf_level_metadata(
            collection_id=self.collection.id,
            schema_type="transcription"
        )
        self.assertEqual(len(leaf_results), 1)
        self.assertEqual(leaf_results[0].item_id, self.test_item.id)
        self.assertEqual(leaf_results[0].value, "Enhanced image transcription text for specific document")

        # Test querying node-level metadata
        node_results = self.storage.get_collection_level_metadata(
            collection_id=self.collection.id,
            schema_type="catalogue"
        )
        self.assertEqual(len(node_results), 1)
        self.assertIsNone(node_results[0].item_id)
        self.assertEqual(node_results[0].value, "Collection contains historical documents from 1926-1931 period")

        # Test querying specific item's metadata (should only return leaf-level)
        item_results = self.storage.get_extracted_metadata_by_item(
            item_id=self.test_item.id,
            collection_level=False
        )
        self.assertEqual(len(item_results), 1)
        self.assertEqual(item_results[0].schema_type, "transcription")

    def test_integration_end_to_end(self):
        """Test end-to-end integration with director integration service"""

        # Create a processing result
        processing_result = ProcessingResult(
            id="result-001",
            item_id=self.test_item.id,
            workflow="Default",
            status="success",
            started_at=datetime.now()
        )
        self.library_manager.storage.add_processing_result(processing_result)

        # Create processing outputs with different scopes
        enhance_output = ProcessingOutput(
            id="output-enhance",
            processing_result_id=processing_result.id,
            collection_id=self.collection.id,
            item_id=self.test_item.id,  # File-specific
            step_name="enhance",
            output_type="prepared_image",
            output_path="assets/enhanced/test_document.jpg",
            file_format="jpg",
            file_size=1024,
            file_modified=datetime.now(),
            created_at=datetime.now(),
            metadata_extracted=False,
            is_valid=True
        )
        self.library_manager.storage.add_processing_output(enhance_output)

        catalogue_output = ProcessingOutput(
            id="output-catalogue",
            processing_result_id=processing_result.id,
            collection_id=self.collection.id,
            item_id=None,  # Collection-level
            step_name="catalogue_folder",
            output_type="catalogue",
            output_path="assets/llm_catalogue/collection_summary.json",
            file_format="json",
            file_size=512,
            file_modified=datetime.now(),
            created_at=datetime.now(),
            metadata_extracted=False,
            is_valid=True
        )
        self.library_manager.storage.add_processing_output(catalogue_output)

        # Create temporary output files and manifest in the collection root
        # Based on path calculation, files should be at: collection_root / output.output_path
        collection_root = Path(self.temp_dir)

        # Create workflow manifest in processing directory
        output_dir = Path(self.temp_dir) / "collection" / "workflow" / "processing"
        output_dir.mkdir(parents=True)

        manifest_data = {
            "version": "1.0",
            "workflow": {"plan_name": "Test Plan", "workflow_name": "Default"},
            "steps": [
                {"order": 1, "name": "enhance", "status": "success", "output_scope": "leaf"},
                {"order": 2, "name": "catalogue_folder", "status": "success", "output_scope": "node"}
            ]
        }
        manifest_file = output_dir / "workflow_manifest.json"
        manifest_file.write_text(json.dumps(manifest_data))

        # Create fake output files at collection root (where the service expects them)
        (collection_root / "assets" / "enhanced").mkdir(parents=True)
        (collection_root / "assets" / "enhanced" / "test_document.jpg").write_text("fake image")

        (collection_root / "assets" / "llm_catalogue").mkdir(parents=True)
        catalogue_file = collection_root / "assets" / "llm_catalogue" / "collection_summary.json"
        catalogue_file.write_text(json.dumps({"summary": "Test collection summary"}))

        # Create director integration service with our existing library_manager
        from unittest.mock import Mock
        mock_app = Mock()
        mock_director = Mock()
        director_service = DirectorIntegrationService(mock_app, self.library_manager, mock_director)

        # Mock the metadata extractor to actually extract and save test data
        def mock_extract(output_path, output_type, collection_id, item_id, processing_output_id, step_name, workflow_manifest=None):
            metadata_list = []

            if step_name == "enhance":
                metadata = ExtractedMetadata(
                    processing_output_id=processing_output_id,
                    collection_id=collection_id,
                    item_id=item_id,
                    collection_level=False,
                    schema_type="prepared_image",
                    source_label="enhance",
                    version=1,
                    schema_version="1.0",
                    key="file_path",
                    value=str(output_path)
                )
                # Save to storage (like the real UniversalExtractor does)
                director_service.metadata_extractor.storage.add_extracted_metadata(metadata)
                metadata_list = [metadata]
            elif step_name == "catalogue_folder":
                metadata = ExtractedMetadata(
                    processing_output_id=processing_output_id,
                    collection_id=collection_id,
                    item_id=None,
                    collection_level=True,
                    schema_type="catalogue",
                    source_label="ai_catalogue",
                    version=1,
                    schema_version="1.0",
                    key="summary",
                    value="Test collection summary"
                )
                # Save to storage (like the real UniversalExtractor does)
                director_service.metadata_extractor.storage.add_extracted_metadata(metadata)
                metadata_list = [metadata]

            return metadata_list

        director_service.metadata_extractor.extract_from_output = mock_extract


        # Run metadata extraction using the processing output directory
        director_service._extract_metadata_from_outputs(
            processing_result.id,
            self.collection.id,
            output_dir
        )

        # Verify that leaf and node metadata were stored correctly
        leaf_metadata = self.library_manager.storage.get_leaf_level_metadata(
            collection_id=self.collection.id,
            schema_type="prepared_image"
        )
        self.assertEqual(len(leaf_metadata), 1)
        self.assertEqual(leaf_metadata[0].item_id, self.test_item.id)

        node_metadata = self.library_manager.storage.get_collection_level_metadata(
            collection_id=self.collection.id,
            schema_type="catalogue"
        )
        self.assertEqual(len(node_metadata), 1)
        self.assertIsNone(node_metadata[0].item_id)
        self.assertEqual(node_metadata[0].value, "Test collection summary")


if __name__ == "__main__":
    unittest.main()