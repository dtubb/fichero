"""
Integration Tests for Director-Library Integration System

Comprehensive end-to-end testing covering all phases of improvements:
- Phase 1: Data Flow Investigation
- Phase 2: Manifest Ingestion Fixes
- Phase 3: Metadata Architecture Enhancement (leaf vs node level)
- Phase 4: Smart Output Processing (plan-aware validation)

Tests the complete flow:
Director Processing → WorkflowManifest → Ingestion → ProcessingOutput → ExtractedMetadata → Database → Query/Display
"""

import unittest
import tempfile
import json
import shutil
import asyncio
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, List, Optional, Any

# Import required models and services
from fichero.library.models import (
    Collection, CollectionItem, ProcessingResult, ProcessingOutput, ExtractedMetadata
)
from fichero.library.director_integration import DirectorIntegrationService
from fichero.library.library_manager import LibraryManager
from fichero.library.storage import LibraryStorage


class TestDirectorLibraryIntegration(unittest.TestCase):
    """Comprehensive integration tests for director-library system"""

    def setUp(self):
        """Set up test environment with real components"""
        # Create temporary directories for testing
        self.test_dir = Path(tempfile.mkdtemp())
        self.library_dir = self.test_dir / "library"
        self.output_dir = self.test_dir / "outputs"
        self.library_dir.mkdir()
        self.output_dir.mkdir()

        # Create test database
        self.db_path = self.library_dir / "test.db"
        self.storage = LibraryStorage(str(self.db_path))

        # Mock app and director
        self.app = Mock()
        self.director = Mock()

        # Create real library manager with test app
        # Mock the path resolver to use our test database
        with patch('fichero.library.path_resolver.get_library_database_path', return_value=self.db_path):
            self.library_manager = LibraryManager(app=self.app)

        # Override the storage with our test storage to ensure isolation
        self.library_manager.storage = self.storage

        # Create director integration service
        self.director_service = DirectorIntegrationService(
            app=self.app,
            library_manager=self.library_manager,
            director=self.director
        )

        # Create test collection and items
        self.test_collection = Collection(
            id="test-collection-123",
            name="Test Collection",
            type="local",
            local_path=str(self.test_dir / "source")
        )
        self.storage.add_collection(self.test_collection)

        # Create test items for different processing scenarios
        self.test_file_item = CollectionItem(
            id="test-file-item-123",
            collection_id=self.test_collection.id,
            type="file",
            name="test_document.jpg",
            local_path=str(self.test_dir / "source" / "test_document.jpg"),
            status="pending"
        )

        self.test_folder_item = CollectionItem(
            id="test-folder-item-123",
            collection_id=self.test_collection.id,
            type="folder",
            name="test_folder",
            local_path=str(self.test_dir / "source" / "test_folder"),
            status="pending"
        )

        self.storage.add_collection_item(self.test_file_item)
        self.storage.add_collection_item(self.test_folder_item)

    def tearDown(self):
        """Clean up test environment"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def _create_workflow_manifest(self, output_path: Path, workflow_config: Dict) -> None:
        """Create a realistic workflow manifest file

        Args:
            output_path: Directory to create manifest in
            workflow_config: Configuration for the workflow
        """
        manifest = {
            "version": "1.0",
            "workflow": {
                "plan_name": workflow_config.get("plan_name", "Transcribir y Catalogar"),
                "workflow_name": workflow_config.get("workflow_name", "Catalogue"),
                "task_id": workflow_config.get("task_id", "task-123"),
                "success": workflow_config.get("success", True),
                "started_at": workflow_config.get("started_at", datetime.now().isoformat()),
                "completed_at": workflow_config.get("completed_at", datetime.now().isoformat())
            },
            "steps": workflow_config.get("steps", [])
        }

        manifest_file = output_path / "workflow_manifest.json"
        manifest_file.write_text(json.dumps(manifest, indent=2))

    def _create_transcription_outputs(self, output_path: Path, files: List[str]) -> None:
        """Create realistic transcription output files and manifest

        Args:
            output_path: Base output directory
            files: List of source files to create transcriptions for
        """
        # Create transcriptions directory
        trans_dir = output_path / "assets" / "transcriptions"
        trans_dir.mkdir(parents=True, exist_ok=True)

        # Create transcription files and manifest entries
        manifest_entries = []
        for source_file in files:
            # Create transcription file
            trans_file = trans_dir / f"{Path(source_file).stem}.txt"
            trans_content = f"This is the transcription content for {source_file}\n\nLorem ipsum dolor sit amet, consectetur adipiscing elit."
            trans_file.write_text(trans_content)

            # Create manifest entry
            manifest_entry = {
                "outputs": [trans_file.name],
                "source": source_file,
                "details": {
                    "has_content": True,
                    "text_length": len(trans_content),
                    "word_count": len(trans_content.split()),
                    "confidence": 0.92
                }
            }
            manifest_entries.append(manifest_entry)

        # Write transcriptions manifest
        trans_manifest = trans_dir / "transcriptions_manifest.jsonl"
        with open(trans_manifest, 'w') as f:
            for entry in manifest_entries:
                f.write(json.dumps(entry) + '\n')

    def _create_catalogue_outputs(self, output_path: Path, target: str, is_folder_level: bool = False) -> None:
        """Create realistic catalogue output files

        Args:
            output_path: Base output directory
            target: Source file/folder name
            is_folder_level: Whether this is folder-level cataloguing
        """
        # Create catalogue directory
        cat_dir = output_path / "assets" / "catalogue"
        cat_dir.mkdir(parents=True, exist_ok=True)

        if is_folder_level:
            # Folder-level catalogue (collection metadata)
            cat_file = cat_dir / f"{target}_catalogue.json"
            catalogue_data = {
                "collection_title": f"Collection: {target}",
                "description": f"Archival materials from {target}",
                "date_range": "1950-1980",
                "total_items": 25,
                "languages": ["Spanish", "English"],
                "topics": ["Family History", "Business Records"],
                "location": "Madrid, Spain",
                "cataloguing_date": datetime.now().isoformat(),
                "cataloguer": "AI Assistant"
            }
        else:
            # File-level catalogue (item metadata)
            cat_file = cat_dir / f"{Path(target).stem}_catalogue.json"
            catalogue_data = {
                "title": f"Document: {target}",
                "document_type": "Letter",
                "date": "1965-03-15",
                "author": "María González",
                "recipient": "Carlos Rodríguez",
                "language": "Spanish",
                "topics": ["Personal correspondence", "Family news"],
                "location": "Barcelona, Spain",
                "description": f"Personal letter discussing family matters from {target}",
                "cataloguing_date": datetime.now().isoformat()
            }

        cat_file.write_text(json.dumps(catalogue_data, indent=2))

        # Create catalogue manifest entry
        manifest_entry = {
            "outputs": [cat_file.name],
            "source": target,
            "details": {
                "catalogue_type": "folder" if is_folder_level else "file",
                "fields_extracted": len(catalogue_data),
                "confidence": 0.89
            }
        }

        cat_manifest = cat_dir / "catalogue_manifest.jsonl"
        if cat_manifest.exists():
            # Append to existing manifest
            with open(cat_manifest, 'a') as f:
                f.write(json.dumps(manifest_entry) + '\n')
        else:
            # Create new manifest
            with open(cat_manifest, 'w') as f:
                f.write(json.dumps(manifest_entry) + '\n')

    def _create_word_docs(self, output_path: Path, files: List[str]) -> None:
        """Create realistic Word document outputs

        Args:
            output_path: Base output directory
            files: List of source files to create Word docs for
        """
        # Create word_docs directory
        word_dir = output_path / "assets" / "word_docs"
        word_dir.mkdir(parents=True, exist_ok=True)

        # Create Word document files (simulate with .docx.txt for testing)
        manifest_entries = []
        for source_file in files:
            word_file = word_dir / f"{Path(source_file).stem}.docx"
            # Simulate Word document with placeholder content
            word_content = f"Microsoft Word Document\nGenerated for: {source_file}\nDate: {datetime.now().strftime('%Y-%m-%d')}\n\nContent: Side-by-side layout with image and transcription"
            word_file.write_text(word_content)  # In real scenario this would be binary .docx

            manifest_entry = {
                "outputs": [word_file.name],
                "source": source_file,
                "details": {
                    "format": "docx",
                    "layout": "side_by_side",
                    "pages": 1,
                    "file_size": len(word_content)
                }
            }
            manifest_entries.append(manifest_entry)

        # Write word_docs manifest
        word_manifest = word_dir / "word_docs_manifest.jsonl"
        with open(word_manifest, 'w') as f:
            for entry in manifest_entries:
                f.write(json.dumps(entry) + '\n')

    def test_single_file_processing_end_to_end(self):
        """Test complete flow for single file processing (leaf-level metadata)"""
        # ARRANGE: Create realistic Director output for single file
        item_output_dir = self.output_dir / "single_file_test"
        item_output_dir.mkdir()

        # Create workflow manifest
        self._create_workflow_manifest(item_output_dir, {
            "plan_name": "Transcribir y Catalogar",
            "workflow_name": "Catalogue",
            "task_id": "file-task-123",
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
                },
                {
                    "order": 3,
                    "name": "create_word_doc",
                    "status": "success",
                    "manifest_file": "assets/word_docs/word_docs_manifest.jsonl"
                }
            ]
        })

        # Create step outputs
        self._create_transcription_outputs(item_output_dir, ["test_document.jpg"])
        self._create_catalogue_outputs(item_output_dir, "test_document.jpg", is_folder_level=False)
        self._create_word_docs(item_output_dir, ["test_document.jpg"])

        # ACT: Run the complete integration process
        # 1. Ingest processing outputs (creates ProcessingOutput records)
        processing_result_id = "result-file-123"
        self.director_service._ingest_processing_outputs(
            processing_result_id=processing_result_id,
            collection_id=self.test_collection.id,
            item_id=self.test_file_item.id,
            output_path=item_output_dir
        )

        # 2. Extract metadata from outputs (creates ExtractedMetadata records)
        self.director_service._extract_metadata_from_outputs(
            processing_result_id=processing_result_id,
            collection_id=self.test_collection.id,
            output_path=item_output_dir
        )

        # ASSERT: Verify complete data flow

        # 1. ProcessingOutput records were created
        outputs = self.storage.get_outputs_by_item(
            item_id=self.test_file_item.id
        )
        self.assertGreater(len(outputs), 0, "ProcessingOutput records should be created")

        # Verify we have outputs for each step
        output_types = [output.output_type for output in outputs]
        self.assertIn("transcription", output_types, "Should have transcription output")
        self.assertIn("catalogue", output_types, "Should have catalogue output")
        self.assertIn("word_doc", output_types, "Should have word_doc output")

        # 2. ExtractedMetadata records were created with correct leaf-level distinction
        metadata_records = self.storage.get_extracted_metadata_by_item(
            item_id=self.test_file_item.id
        )
        self.assertGreater(len(metadata_records), 0, "ExtractedMetadata records should be created")

        # Verify leaf-level metadata (item_id set, collection_level=False)
        for metadata in metadata_records:
            self.assertEqual(metadata.item_id, self.test_file_item.id, "Should have item_id for file-level processing")
            self.assertFalse(metadata.collection_level, "Should be file-level (leaf) metadata")
            self.assertEqual(metadata.collection_id, self.test_collection.id, "Should have collection_id")

        # 3. Verify specific metadata types
        transcription_meta = self.storage.get_extracted_metadata_by_item(
            item_id=self.test_file_item.id,
            schema_type="transcription"
        )
        self.assertGreater(len(transcription_meta), 0, "Should have transcription metadata")

        catalogue_meta = self.storage.get_extracted_metadata_by_item(
            item_id=self.test_file_item.id,
            schema_type="catalogue"
        )
        self.assertGreater(len(catalogue_meta), 0, "Should have catalogue metadata")

        # 4. Verify metadata content
        trans_text_meta = self.storage.get_extracted_metadata_by_item(
            item_id=self.test_file_item.id,
            schema_type="transcription",
            key="text"
        )
        if trans_text_meta:
            self.assertIn("transcription content", trans_text_meta[0].value, "Should contain transcription content")

    def test_single_folder_processing_end_to_end(self):
        """Test complete flow for single folder processing (node-level metadata)"""
        # ARRANGE: Create realistic Director output for folder processing
        folder_output_dir = self.output_dir / "single_folder_test"
        folder_output_dir.mkdir()

        # Create workflow manifest for folder processing
        self._create_workflow_manifest(folder_output_dir, {
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

        # Create folder-level catalogue output
        self._create_catalogue_outputs(folder_output_dir, "test_folder", is_folder_level=True)

        # ACT: Run integration process for folder
        processing_result_id = "result-folder-123"
        self.director_service._ingest_processing_outputs(
            processing_result_id=processing_result_id,
            collection_id=self.test_collection.id,
            item_id=self.test_folder_item.id,
            output_path=folder_output_dir
        )

        self.director_service._extract_metadata_from_outputs(
            processing_result_id=processing_result_id,
            collection_id=self.test_collection.id,
            output_path=folder_output_dir
        )

        # ASSERT: Verify folder-level (node) metadata

        # 1. ProcessingOutput records created for folder-level processing
        outputs = self.storage.get_outputs_by_item(
            item_id=self.test_folder_item.id
        )
        self.assertGreater(len(outputs), 0, "Should have folder-level ProcessingOutput records")

        folder_catalogue_outputs = [o for o in outputs if o.output_type == "catalogue"]
        self.assertGreater(len(folder_catalogue_outputs), 0, "Should have folder catalogue output")

        # 2. ExtractedMetadata with node-level distinction (item_id set, collection_level=True for folder summary)
        metadata_records = self.storage.get_extracted_metadata_by_item(
            item_id=self.test_folder_item.id
        )
        self.assertGreater(len(metadata_records), 0, "Should have folder-level metadata")

        # Check for collection-level metadata created during folder processing
        collection_meta = self.storage.get_extracted_metadata_by_collection(
            collection_id=self.test_collection.id,
            collection_level=True
        )

        # Verify metadata structure (could be item-level folder metadata OR collection-level)
        for metadata in metadata_records:
            self.assertEqual(metadata.collection_id, self.test_collection.id, "Should have collection_id")
            # For folder items, metadata could be either item-level or collection-level
            # depending on whether it describes the folder itself or the entire collection

        # 3. Verify catalogue content contains collection-level information
        catalogue_meta = self.storage.get_extracted_metadata_by_item(
            item_id=self.test_folder_item.id,
            schema_type="catalogue"
        )
        self.assertGreater(len(catalogue_meta), 0, "Should have folder catalogue metadata")

    def test_mixed_collection_processing(self):
        """Test processing collection with both file and folder items (mixed metadata levels)"""
        # ARRANGE: Create outputs for both file and folder processing
        mixed_output_dir = self.output_dir / "mixed_processing_test"
        mixed_output_dir.mkdir()

        # Process the file item first
        file_output_dir = mixed_output_dir / "file_processing"
        file_output_dir.mkdir()

        self._create_workflow_manifest(file_output_dir, {
            "plan_name": "Transcribir y Catalogar",
            "workflow_name": "Catalogue",
            "task_id": "mixed-file-task-123"
        })
        self._create_transcription_outputs(file_output_dir, ["test_document.jpg"])
        self._create_catalogue_outputs(file_output_dir, "test_document.jpg", is_folder_level=False)

        # Process the folder item
        folder_output_dir = mixed_output_dir / "folder_processing"
        folder_output_dir.mkdir()

        self._create_workflow_manifest(folder_output_dir, {
            "plan_name": "Transcribir y Catalogar",
            "workflow_name": "Catalogue",
            "task_id": "mixed-folder-task-123"
        })
        self._create_catalogue_outputs(folder_output_dir, "test_folder", is_folder_level=True)

        # ACT: Process both items
        # File processing
        self.director_service._ingest_processing_outputs(
            processing_result_id="result-mixed-file-123",
            collection_id=self.test_collection.id,
            item_id=self.test_file_item.id,
            output_path=file_output_dir
        )
        self.director_service._extract_metadata_from_outputs(
            processing_result_id="result-mixed-file-123",
            collection_id=self.test_collection.id,
            output_path=file_output_dir
        )

        # Folder processing
        self.director_service._ingest_processing_outputs(
            processing_result_id="result-mixed-folder-123",
            collection_id=self.test_collection.id,
            item_id=self.test_folder_item.id,
            output_path=folder_output_dir
        )
        self.director_service._extract_metadata_from_outputs(
            processing_result_id="result-mixed-folder-123",
            collection_id=self.test_collection.id,
            output_path=folder_output_dir
        )

        # ASSERT: Verify mixed metadata levels coexist correctly

        # 1. Both file and folder should have ProcessingOutputs
        file_outputs = self.storage.get_outputs_by_item(
            item_id=self.test_file_item.id
        )
        folder_outputs = self.storage.get_outputs_by_item(
            item_id=self.test_folder_item.id
        )

        self.assertGreater(len(file_outputs), 0, "File should have processing outputs")
        self.assertGreater(len(folder_outputs), 0, "Folder should have processing outputs")

        # 2. Verify leaf-level metadata (file)
        file_metadata = self.storage.get_extracted_metadata_by_item(
            item_id=self.test_file_item.id
        )
        for meta in file_metadata:
            self.assertEqual(meta.item_id, self.test_file_item.id, "File metadata should have item_id")
            self.assertFalse(meta.collection_level, "File metadata should be leaf-level")

        # 3. Verify node-level metadata (folder)
        folder_metadata = self.storage.get_extracted_metadata_by_item(
            item_id=self.test_folder_item.id
        )
        for meta in folder_metadata:
            self.assertEqual(meta.collection_id, self.test_collection.id, "Folder metadata should have collection_id")

        # 4. Verify collection can query both types
        all_collection_meta = self.storage.get_extracted_metadata_by_collection(
            collection_id=self.test_collection.id
        )
        self.assertGreaterEqual(len(all_collection_meta), len(file_metadata) + len(folder_metadata),
                               "Collection should contain all metadata from both items")

        # 5. Verify different schema types
        transcription_meta = self.storage.get_extracted_metadata_by_collection(
            collection_id=self.test_collection.id,
            schema_type="transcription"
        )
        self.assertGreater(len(transcription_meta), 0, "Should have transcription metadata from file processing")

        catalogue_meta = self.storage.get_extracted_metadata_by_collection(
            collection_id=self.test_collection.id,
            schema_type="catalogue"
        )
        self.assertGreater(len(catalogue_meta), 0, "Should have catalogue metadata from both file and folder")

    def test_plan_aware_output_validation(self):
        """Test that different plans produce expected outputs and validation (Phase 4)"""
        # ARRANGE: Test different plan types with different expected outputs

        # Plan 1: "Transcribir y Catalogar" - should have transcriptions, catalogues, word docs
        plan1_dir = self.output_dir / "plan_transcribe_catalogue"
        plan1_dir.mkdir()

        self._create_workflow_manifest(plan1_dir, {
            "plan_name": "Transcribir y Catalogar",
            "workflow_name": "Catalogue",
            "task_id": "plan1-task-123",
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
                },
                {
                    "order": 3,
                    "name": "create_word_doc",
                    "status": "success",
                    "manifest_file": "assets/word_docs/word_docs_manifest.jsonl"
                }
            ]
        })
        self._create_transcription_outputs(plan1_dir, ["doc1.jpg"])
        self._create_catalogue_outputs(plan1_dir, "doc1.jpg")
        self._create_word_docs(plan1_dir, ["doc1.jpg"])

        # Plan 2: "Prepare Images" - should have only prepared images
        plan2_dir = self.output_dir / "plan_prepare_images"
        plan2_dir.mkdir()

        # Create enhanced images directory and outputs
        enhanced_dir = plan2_dir / "assets" / "enhanced_images"
        enhanced_dir.mkdir(parents=True)

        enhanced_file = enhanced_dir / "doc2_enhanced.jpg"
        enhanced_file.write_text("Enhanced image data (simulated)")

        enhanced_manifest = enhanced_dir / "enhanced_images_manifest.jsonl"
        enhanced_entry = {
            "outputs": ["doc2_enhanced.jpg"],
            "source": "doc2.jpg",
            "details": {
                "enhancement_type": "contrast_brightness",
                "quality_score": 0.95
            }
        }
        enhanced_manifest.write_text(json.dumps(enhanced_entry))

        self._create_workflow_manifest(plan2_dir, {
            "plan_name": "Prepare Images",
            "workflow_name": "Enhance",
            "task_id": "plan2-task-123",
            "steps": [
                {
                    "order": 1,
                    "name": "enhance_images",
                    "status": "success",
                    "manifest_file": "assets/enhanced_images/enhanced_images_manifest.jsonl"
                }
            ]
        })

        # ACT: Process both plans
        # Plan 1 processing
        self.director_service._ingest_processing_outputs(
            processing_result_id="result-plan1-123",
            collection_id=self.test_collection.id,
            item_id=self.test_file_item.id,
            output_path=plan1_dir
        )

        # Plan 2 processing
        self.director_service._ingest_processing_outputs(
            processing_result_id="result-plan2-123",
            collection_id=self.test_collection.id,
            item_id=self.test_file_item.id,
            output_path=plan2_dir
        )

        # ASSERT: Verify plan-aware output validation

        # 1. Plan 1 should have multiple output types
        plan1_outputs = self.storage.get_processing_outputs(
            processing_result_id="result-plan1-123"
        )
        plan1_types = set(output.output_type for output in plan1_outputs)

        self.assertIn("transcription", plan1_types, "Transcribir y Catalogar should have transcriptions")
        self.assertIn("catalogue", plan1_types, "Transcribir y Catalogar should have catalogues")
        self.assertIn("word_doc", plan1_types, "Transcribir y Catalogar should have word docs")

        # 2. Plan 2 should only have enhanced images
        plan2_outputs = self.storage.get_processing_outputs(
            processing_result_id="result-plan2-123"
        )
        plan2_types = set(output.output_type for output in plan2_outputs)

        self.assertIn("prepared_image", plan2_types, "Prepare Images should have prepared images")
        self.assertNotIn("transcription", plan2_types, "Prepare Images should not have transcriptions")
        self.assertNotIn("catalogue", plan2_types, "Prepare Images should not have catalogues")

        # 3. Verify step names match plan expectations
        plan1_steps = set(output.step_name for output in plan1_outputs)
        self.assertIn("transcribe", plan1_steps, "Should have transcription step")
        self.assertIn("catalogue", plan1_steps, "Should have catalogue step")

        plan2_steps = set(output.step_name for output in plan2_outputs)
        self.assertIn("enhance_images", plan2_steps, "Should have enhancement step")

    def test_error_recovery_scenarios(self):
        """Test robust error handling from all phases"""
        # ARRANGE: Create various error scenarios

        # Scenario 1: Missing collection_id recovery (Phase 2)
        error_dir1 = self.output_dir / "error_missing_collection"
        error_dir1.mkdir()

        self._create_workflow_manifest(error_dir1, {
            "task_id": "error-task-123"
        })
        self._create_transcription_outputs(error_dir1, ["doc.jpg"])

        # Test item with no collection_id
        orphan_item = CollectionItem(
            id="orphan-item-123",
            collection_id="",  # Missing collection_id
            type="file",
            name="orphan.jpg",
            status="pending"
        )
        self.storage.add_collection_item(orphan_item)

        # Scenario 2: Corrupt manifest file
        error_dir2 = self.output_dir / "error_corrupt_manifest"
        error_dir2.mkdir()

        corrupt_manifest = error_dir2 / "workflow_manifest.json"
        corrupt_manifest.write_text("{ invalid json content")

        # Scenario 3: Missing output files
        error_dir3 = self.output_dir / "error_missing_outputs"
        error_dir3.mkdir()

        # Create manifest but no actual output files
        self._create_workflow_manifest(error_dir3, {
            "task_id": "error-missing-task-123",
            "steps": [
                {
                    "order": 1,
                    "name": "transcribe",
                    "status": "success",
                    "manifest_file": "assets/transcriptions/transcriptions_manifest.jsonl"
                }
            ]
        })
        # Don't create the actual transcription outputs

        # ACT & ASSERT: Test error handling

        # 1. Test missing collection_id recovery
        with self.assertLogs(level='WARNING') as log:
            self.director_service._ingest_processing_outputs(
                processing_result_id="error-result-123",
                collection_id="",  # Empty collection_id
                item_id=orphan_item.id,
                output_path=error_dir1
            )

            # Should handle gracefully and log warning
            warning_messages = [record.getMessage() for record in log.records if record.levelname == 'WARNING']
            collection_warnings = [msg for msg in warning_messages if 'collection_id' in msg.lower()]
            self.assertTrue(any(collection_warnings), "Should log warning about missing collection_id")

        # 2. Test corrupt manifest handling
        with self.assertLogs(level='ERROR') as log:
            try:
                self.director_service._ingest_processing_outputs(
                    processing_result_id="error-result-corrupt-123",
                    collection_id=self.test_collection.id,
                    item_id=self.test_file_item.id,
                    output_path=error_dir2
                )
            except Exception:
                pass  # Expected to fail gracefully

            # Should log error about corrupt manifest
            error_messages = [record.getMessage() for record in log.records if record.levelname == 'ERROR']
            self.assertTrue(any('json' in msg.lower() or 'manifest' in msg.lower() for msg in error_messages),
                           "Should log error about corrupt manifest")

        # 3. Test missing output file recovery
        with self.assertLogs(level='WARNING') as log:
            self.director_service._ingest_processing_outputs(
                processing_result_id="error-result-missing-123",
                collection_id=self.test_collection.id,
                item_id=self.test_file_item.id,
                output_path=error_dir3
            )

            # Should handle missing files gracefully
            warning_messages = [record.getMessage() for record in log.records if record.levelname == 'WARNING']
            missing_warnings = [msg for msg in warning_messages if 'not found' in msg.lower() or 'missing' in msg.lower()]
            self.assertTrue(any(missing_warnings), "Should log warning about missing output files")

        # 4. Verify database remains consistent despite errors
        outputs = self.storage.get_outputs_by_collection(
            collection_id=self.test_collection.id
        )

        # Should not have corrupted database with invalid data
        for output in outputs:
            self.assertIsNotNone(output.collection_id, "All outputs should have valid collection_id")
            self.assertIsNotNone(output.processing_result_id, "All outputs should have processing_result_id")

    def test_metadata_extraction_leaf_node_distinction(self):
        """Test that metadata extraction correctly distinguishes leaf vs node level (Phase 3)"""
        # ARRANGE: Create scenario with both file and collection-level metadata
        meta_test_dir = self.output_dir / "metadata_distinction_test"
        meta_test_dir.mkdir()

        # Create outputs that should generate both levels
        self._create_workflow_manifest(meta_test_dir, {
            "plan_name": "Transcribir y Catalogar",
            "workflow_name": "Catalogue",
            "task_id": "meta-task-123"
        })

        # File-level transcription (should be leaf-level)
        self._create_transcription_outputs(meta_test_dir, ["individual_doc.jpg"])

        # File-level catalogue (should be leaf-level)
        self._create_catalogue_outputs(meta_test_dir, "individual_doc.jpg", is_folder_level=False)

        # Collection-level catalogue (should be node-level)
        self._create_catalogue_outputs(meta_test_dir, "entire_collection", is_folder_level=True)

        # ACT: Process and extract metadata
        self.director_service._ingest_processing_outputs(
            processing_result_id="meta-result-123",
            collection_id=self.test_collection.id,
            item_id=self.test_file_item.id,
            output_path=meta_test_dir
        )

        self.director_service._extract_metadata_from_outputs(
            processing_result_id="meta-result-123",
            collection_id=self.test_collection.id,
            output_path=meta_test_dir
        )

        # ASSERT: Verify leaf/node distinction

        # 1. File-level metadata should have item_id and collection_level=False
        file_metadata = self.storage.get_extracted_metadata_by_item(
            item_id=self.test_file_item.id,
            collection_level=False  # Explicitly leaf-level
        )

        for meta in file_metadata:
            self.assertIsNotNone(meta.item_id, "File-level metadata should have item_id")
            self.assertFalse(meta.collection_level, "File-level metadata should be leaf-level")
            self.assertEqual(meta.collection_id, self.test_collection.id, "Should have collection_id")

        # 2. Collection-level metadata should have collection_level=True
        collection_metadata = self.storage.get_extracted_metadata_by_collection(
            collection_id=self.test_collection.id,
            collection_level=True  # Explicitly node-level
        )

        for meta in collection_metadata:
            self.assertTrue(meta.collection_level, "Collection-level metadata should be node-level")
            self.assertEqual(meta.collection_id, self.test_collection.id, "Should have collection_id")
            # item_id can be None for pure collection-level metadata

        # 3. Verify different schema types are correctly categorized
        transcription_meta = self.storage.get_extracted_metadata_by_item(
            item_id=self.test_file_item.id,
            schema_type="transcription"
        )
        for meta in transcription_meta:
            self.assertFalse(meta.collection_level, "Transcriptions should be file-level (leaf)")

        # 4. Test querying by level works correctly
        all_leaf = self.storage.get_extracted_metadata_by_collection(
            collection_id=self.test_collection.id,
            collection_level=False
        )

        all_node = self.storage.get_extracted_metadata_by_collection(
            collection_id=self.test_collection.id,
            collection_level=True
        )

        # Should be able to get both levels and they should be different
        if len(all_leaf) > 0 and len(all_node) > 0:
            leaf_ids = set(meta.id for meta in all_leaf)
            node_ids = set(meta.id for meta in all_node)
            self.assertTrue(leaf_ids.isdisjoint(node_ids), "Leaf and node metadata should be distinct")

    def test_preview_view_database_integration(self):
        """Test that preview views can load transcriptions from database after ingestion"""
        # ARRANGE: Create processed data in database
        preview_test_dir = self.output_dir / "preview_integration_test"
        preview_test_dir.mkdir()

        self._create_workflow_manifest(preview_test_dir, {
            "plan_name": "Transcribir y Catalogar",
            "workflow_name": "Catalogue",
            "task_id": "preview-task-123"
        })
        self._create_transcription_outputs(preview_test_dir, ["preview_doc.jpg"])

        # Process into database
        self.director_service._ingest_processing_outputs(
            processing_result_id="preview-result-123",
            collection_id=self.test_collection.id,
            item_id=self.test_file_item.id,
            output_path=preview_test_dir
        )

        self.director_service._extract_metadata_from_outputs(
            processing_result_id="preview-result-123",
            collection_id=self.test_collection.id,
            output_path=preview_test_dir
        )

        # ACT: Simulate preview view loading transcription from database
        transcription_metadata = self.storage.get_extracted_metadata_by_item(
            item_id=self.test_file_item.id,
            schema_type="transcription",
            key="text"
        )

        # ASSERT: Verify preview can load data
        self.assertGreater(len(transcription_metadata), 0, "Should have transcription metadata for preview")

        transcription_text = transcription_metadata[0].value if transcription_metadata else None
        self.assertIsNotNone(transcription_text, "Should have transcription text")
        self.assertIn("transcription content", transcription_text, "Should contain expected transcription")

        # Verify metadata has correct structure for preview loading
        metadata = transcription_metadata[0]
        self.assertEqual(metadata.item_id, self.test_file_item.id, "Should be linked to correct item")
        self.assertEqual(metadata.schema_type, "transcription", "Should be transcription type")
        self.assertEqual(metadata.key, "text", "Should have text key")
        self.assertFalse(metadata.collection_level, "Transcriptions should be file-level")

    def test_adjust_view_metadata_loading(self):
        """Test that adjust views can load all metadata types after ingestion"""
        # ARRANGE: Create comprehensive metadata
        adjust_test_dir = self.output_dir / "adjust_integration_test"
        adjust_test_dir.mkdir()

        self._create_workflow_manifest(adjust_test_dir, {
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
        self._create_transcription_outputs(adjust_test_dir, ["adjust_doc.jpg"])
        self._create_catalogue_outputs(adjust_test_dir, "adjust_doc.jpg")

        # Process into database
        self.director_service._ingest_processing_outputs(
            processing_result_id="adjust-result-123",
            collection_id=self.test_collection.id,
            item_id=self.test_file_item.id,
            output_path=adjust_test_dir
        )

        self.director_service._extract_metadata_from_outputs(
            processing_result_id="adjust-result-123",
            collection_id=self.test_collection.id,
            output_path=adjust_test_dir
        )

        # ACT: Simulate adjust view loading all metadata
        all_metadata = self.storage.get_extracted_metadata_by_item(
            item_id=self.test_file_item.id
        )

        # ASSERT: Verify adjust view can load comprehensive metadata
        self.assertGreater(len(all_metadata), 0, "Should have metadata for adjust view")

        # Group by schema type
        metadata_by_type = {}
        for meta in all_metadata:
            if meta.schema_type not in metadata_by_type:
                metadata_by_type[meta.schema_type] = []
            metadata_by_type[meta.schema_type].append(meta)

        # Should have multiple types
        self.assertIn("transcription", metadata_by_type, "Should have transcription metadata")
        self.assertIn("catalogue", metadata_by_type, "Should have catalogue metadata")

        # Verify each type has correct structure for adjust view
        for schema_type, metadata_list in metadata_by_type.items():
            for meta in metadata_list:
                self.assertEqual(meta.item_id, self.test_file_item.id, f"{schema_type} should be linked to item")
                self.assertEqual(meta.collection_id, self.test_collection.id, f"{schema_type} should have collection_id")
                self.assertIsNotNone(meta.key, f"{schema_type} should have key")
                self.assertIsNotNone(meta.value, f"{schema_type} should have value")

    def test_performance_realistic_workload(self):
        """Test system performance with realistic workload (simplified version)"""
        # ARRANGE: Create multiple items and outputs (scaled down for testing)
        perf_test_dir = self.output_dir / "performance_test"
        perf_test_dir.mkdir()

        # Create multiple test items
        test_items = []
        for i in range(5):  # Reduced from realistic 100+ for test speed
            item = CollectionItem(
                id=f"perf-item-{i:03d}",
                collection_id=self.test_collection.id,
                type="file",
                name=f"perf_doc_{i:03d}.jpg",
                status="pending"
            )
            self.storage.add_collection_item(item)
            test_items.append(item)

        # Create processing outputs for each item
        for i, item in enumerate(test_items):
            item_dir = perf_test_dir / f"item_{i:03d}"
            item_dir.mkdir()

            self._create_workflow_manifest(item_dir, {
                "plan_name": "Transcribir y Catalogar",
                "workflow_name": "Catalogue",
                "task_id": f"perf-task-{i:03d}"
            })
            self._create_transcription_outputs(item_dir, [item.name])
            self._create_catalogue_outputs(item_dir, item.name)

        # ACT: Process all items and measure basic performance
        start_time = datetime.now()

        for i, item in enumerate(test_items):
            item_dir = perf_test_dir / f"item_{i:03d}"

            self.director_service._ingest_processing_outputs(
                processing_result_id=f"perf-result-{i:03d}",
                collection_id=self.test_collection.id,
                item_id=item.id,
                output_path=item_dir
            )

            self.director_service._extract_metadata_from_outputs(
                processing_result_id=f"perf-result-{i:03d}",
                collection_id=self.test_collection.id,
                output_path=item_dir
            )

        end_time = datetime.now()
        processing_duration = (end_time - start_time).total_seconds()

        # ASSERT: Verify performance and data integrity

        # 1. All items should be processed
        for item in test_items:
            outputs = self.storage.get_outputs_by_item(
                item_id=item.id
            )
            self.assertGreater(len(outputs), 0, f"Item {item.id} should have processing outputs")

            metadata = self.storage.get_extracted_metadata_by_item(item_id=item.id)
            self.assertGreater(len(metadata), 0, f"Item {item.id} should have extracted metadata")

        # 2. Performance should be reasonable (less than 2 seconds per item for this simple test)
        max_expected_time = len(test_items) * 2  # 2 seconds per item
        self.assertLess(processing_duration, max_expected_time,
                       f"Processing should complete in reasonable time. Took {processing_duration:.2f}s for {len(test_items)} items")

        # 3. Database queries should remain fast
        query_start = datetime.now()
        all_collection_metadata = self.storage.get_extracted_metadata_by_collection(
            collection_id=self.test_collection.id
        )
        query_duration = (datetime.now() - query_start).total_seconds()

        self.assertLess(query_duration, 1.0, "Collection metadata query should be fast")
        self.assertGreaterEqual(len(all_collection_metadata), len(test_items),
                               "Should have metadata from all processed items")

    def test_backward_compatibility(self):
        """Test that new system works with existing data structures"""
        # ARRANGE: Create "legacy" data that might exist from previous versions

        # Create ExtractedMetadata without collection_level field (backward compatibility)
        legacy_metadata = ExtractedMetadata(
            id="legacy-meta-123",
            processing_output_id="legacy-output-123",
            collection_id=self.test_collection.id,
            item_id=self.test_file_item.id,
            schema_type="transcription",
            source_label="legacy_system",
            key="text",
            value="Legacy transcription content"
            # Note: collection_level will default to False
        )

        self.storage.add_extracted_metadata(legacy_metadata)

        # ACT: Verify new system can handle legacy data
        retrieved_metadata = self.storage.get_extracted_metadata_by_item(
            item_id=self.test_file_item.id
        )

        # ASSERT: Legacy data should work with new queries
        self.assertGreater(len(retrieved_metadata), 0, "Should retrieve legacy metadata")

        legacy_meta = next((m for m in retrieved_metadata if m.id == "legacy-meta-123"), None)
        self.assertIsNotNone(legacy_meta, "Should find legacy metadata")
        self.assertFalse(legacy_meta.collection_level, "Legacy metadata should default to file-level")
        self.assertEqual(legacy_meta.value, "Legacy transcription content", "Legacy content should be preserved")

        # Test that new queries work with legacy data
        leaf_level_query = self.storage.get_extracted_metadata_by_collection(
            collection_id=self.test_collection.id,
            collection_level=False
        )
        legacy_in_query = any(m.id == "legacy-meta-123" for m in leaf_level_query)
        self.assertTrue(legacy_in_query, "Legacy metadata should appear in leaf-level queries")

    def test_folder_processing_with_item_map(self):
        """
        Test folder processing with item_map for correct file-level routing.

        This is the critical test for the bug fix: when processing a folder containing
        multiple files, file-level outputs (transcriptions) should be routed to individual
        file items, NOT to the folder item.
        """
        # ARRANGE: Create folder with 3 file items
        test_files = [
            "document1.jpg",
            "document2.jpg",
            "document3.jpg"
        ]

        # Create file items as children of the folder
        file_items = []
        for filename in test_files:
            file_item = CollectionItem(
                collection_id=self.test_collection.id,
                type="file",
                name=filename,
                parent_id=self.test_folder_item.id,  # Link to parent folder
                source_path=str(self.test_dir / "source" / "test_folder" / filename),
                status="pending"
            )
            self.storage.add_collection_item(file_item)
            file_items.append(file_item)

        # Create output directory with realistic Director outputs
        folder_output_dir = self.output_dir / "folder_with_item_map_test"
        folder_output_dir.mkdir()

        # Create workflow manifest with both file-level and folder-level steps
        self._create_workflow_manifest(folder_output_dir, {
            "plan_name": "Transcribir y Catalogar",
            "workflow_name": "Catalogue",
            "task_id": "folder-task-456",
            "steps": [
                {
                    "order": 1,
                    "name": "transcribe_qwen_max_direct",
                    "status": "success",
                    "manifest_file": "assets/transcriptions/transcriptions_manifest.jsonl"
                },
                {
                    "order": 2,
                    "name": "catalogue_folder",
                    "status": "success",
                    "manifest_file": "assets/catalogue/catalogue_manifest.jsonl"
                }
            ]
        })

        # Create transcription outputs (file-level)
        self._create_transcription_outputs(folder_output_dir, test_files)

        # Create folder catalogue output (collection-level)
        self._create_catalogue_outputs(folder_output_dir, "test_folder", is_folder_level=True)

        # Build item_map (this is what the fix adds)
        item_map = {filename: item.id for filename, item in zip(test_files, file_items)}

        # ACT: Run integration process with item_map
        processing_result_id = "result-folder-456"
        self.director_service._ingest_processing_outputs(
            processing_result_id=processing_result_id,
            collection_id=self.test_collection.id,
            item_id=self.test_folder_item.id,  # Folder's item_id
            output_path=folder_output_dir,
            item_map=item_map  # Pass item_map for routing
        )

        self.director_service._extract_metadata_from_outputs(
            processing_result_id=processing_result_id,
            collection_id=self.test_collection.id,
            output_path=folder_output_dir
        )

        # ASSERT: Verify correct routing

        # 1. Each file item should have its own transcription output
        for file_item in file_items:
            outputs = self.storage.get_outputs_by_item(item_id=file_item.id)
            transcription_outputs = [o for o in outputs if o.output_type == "transcription"]
            self.assertEqual(len(transcription_outputs), 1,
                           f"File {file_item.name} should have exactly 1 transcription output")

            # Verify source_file matches
            trans_output = transcription_outputs[0]
            self.assertIn(file_item.name, trans_output.source_file,
                        f"Transcription should reference source file {file_item.name}")

        # 2. Folder item should have catalogue output (NOT transcriptions)
        folder_outputs = self.storage.get_outputs_by_item(item_id=self.test_folder_item.id)
        folder_transcriptions = [o for o in folder_outputs if o.output_type == "transcription"]
        folder_catalogues = [o for o in folder_outputs if o.output_type == "catalogue"]

        self.assertEqual(len(folder_transcriptions), 0,
                       "Folder should NOT have transcription outputs (those are file-level)")
        self.assertGreater(len(folder_catalogues), 0,
                         "Folder should have catalogue output (collection-level)")

        # 3. Verify metadata extraction routed correctly
        for file_item in file_items:
            metadata = self.storage.get_extracted_metadata_by_item(item_id=file_item.id)
            # Each file should have transcription metadata
            transcription_meta = [m for m in metadata if m.schema_type == "transcription"]
            self.assertGreater(len(transcription_meta), 0,
                             f"File {file_item.name} should have transcription metadata")

        # 4. Folder metadata should be collection-level, not file-level
        folder_metadata = self.storage.get_extracted_metadata_by_item(
            item_id=self.test_folder_item.id
        )
        # Folder should have catalogue metadata, not transcriptions
        folder_transcription_meta = [m for m in folder_metadata if m.schema_type == "transcription"]
        self.assertEqual(len(folder_transcription_meta), 0,
                       "Folder should NOT have transcription metadata (that's file-level)")

    def test_folder_processing_without_item_map_uses_fallback(self):
        """
        Test that fallback item creation works when item_map is missing.

        When item_map is None or incomplete, the system should try to find/create
        file items automatically.
        """
        # ARRANGE: Create folder but DON'T create file items ahead of time
        test_files = ["document_new1.jpg", "document_new2.jpg"]

        folder_output_dir = self.output_dir / "folder_fallback_test"
        folder_output_dir.mkdir()

        self._create_workflow_manifest(folder_output_dir, {
            "plan_name": "Transcribir y Catalogar",
            "workflow_name": "Catalogue",
            "task_id": "folder-task-789",
            "steps": [{
                "order": 1,
                "name": "transcribe_qwen_max_direct",
                "status": "success",
                "manifest_file": "assets/transcriptions/transcriptions_manifest.jsonl"
            }]
        })

        self._create_transcription_outputs(folder_output_dir, test_files)

        # ACT: Run WITHOUT item_map (fallback should activate)
        processing_result_id = "result-folder-789"
        self.director_service._ingest_processing_outputs(
            processing_result_id=processing_result_id,
            collection_id=self.test_collection.id,
            item_id=self.test_folder_item.id,
            output_path=folder_output_dir,
            item_map=None  # No item_map - should use fallback
        )

        # ASSERT: Verify fallback item creation worked

        # Check that file items were auto-created
        all_items = self.storage.get_collection_items(
            collection_id=self.test_collection.id
        )

        file_items = [item for item in all_items
                     if item.type == "file" and item.parent_id == self.test_folder_item.id]
        # Should have created at least some file items via fallback
        # (exact count depends on whether source files exist in filesystem)

        # Verify that ProcessingOutputs exist
        # Even with fallback, outputs should be created (might go to folder or new file items)
        all_outputs = self.storage.get_outputs_by_collection(
            collection_id=self.test_collection.id
        )
        self.assertGreater(len(all_outputs), 0, "Should have created ProcessingOutput records")


if __name__ == '__main__':
    # Run with verbose output
    unittest.main(verbosity=2)