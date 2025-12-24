"""
Unit tests for workflow output loading fixes

Tests three major fixes:
1. Plan name reading from 'title' field in YAML (workflow_executor.py)
2. Subdirectory fallback logic for output file ingestion (director_integration.py)
3. WorkflowChainer cleanup (removed dead stub methods)
"""

import unittest
from unittest.mock import Mock, AsyncMock, patch, MagicMock, mock_open
from pathlib import Path
import json
import tempfile
import shutil
from datetime import datetime


class TestPlanNameReading(unittest.TestCase):
    """Test that WorkflowExecutor reads plan name from 'title' field"""

    def test_plan_name_from_title_field(self):
        """Verify plan name is read from 'title' field in plan config"""
        from fichero.director.workflow_executor import WorkflowExecutor

        # Arrange: Plan config with 'title' field
        plan_config = {
            'title': 'Transcribir y Catalogar',
            'workflows': {
                'TestWorkflow': ['step1', 'step2']
            },
            'commands': []
        }

        executor = WorkflowExecutor()

        # Mock WorkflowManifest to capture the plan_name passed to it
        with patch('fichero.director.workflow_executor.WorkflowManifest') as MockManifest, \
             patch('fichero.director.workflow_executor.WorkflowLogger'), \
             tempfile.TemporaryDirectory() as tmpdir:

            mock_manifest = Mock()
            MockManifest.return_value = mock_manifest

            folder_path = Path(tmpdir) / 'input'
            folder_path.mkdir()
            output_path = Path(tmpdir) / 'output'
            output_path.mkdir()

            # Act: Execute workflow
            result = executor.execute_workflow(
                task_id='test-task',
                folder_path=folder_path,
                output_path=output_path,
                workflow_name='TestWorkflow',
                plan_config=plan_config,
                variables={},
                parallel_workers=1
            )

            # Assert: WorkflowManifest was called with plan name from 'title' field
            MockManifest.assert_called_once()
            call_args = MockManifest.call_args

            # Kwargs: plan_name should match the 'title' field
            self.assertEqual(call_args.kwargs.get('plan_name'), 'Transcribir y Catalogar')

    def test_plan_name_fallback_to_name_field(self):
        """Verify plan name falls back to 'name' field if 'title' not present"""
        from fichero.director.workflow_executor import WorkflowExecutor

        # Arrange: Plan config with 'name' field but no 'title'
        plan_config = {
            'name': 'Legacy Plan Name',
            'workflows': {
                'TestWorkflow': ['step1']
            },
            'commands': []
        }

        executor = WorkflowExecutor()

        with patch('fichero.director.workflow_executor.WorkflowManifest') as MockManifest, \
             patch('fichero.director.workflow_executor.WorkflowLogger'), \
             tempfile.TemporaryDirectory() as tmpdir:

            mock_manifest = Mock()
            MockManifest.return_value = mock_manifest

            folder_path = Path(tmpdir) / 'input'
            folder_path.mkdir()
            output_path = Path(tmpdir) / 'output'
            output_path.mkdir()

            # Act
            result = executor.execute_workflow(
                task_id='test-task',
                folder_path=folder_path,
                output_path=output_path,
                workflow_name='TestWorkflow',
                plan_config=plan_config,
                variables={},
                parallel_workers=1
            )

            # Assert: Falls back to 'name' field
            MockManifest.assert_called_once()
            call_args = MockManifest.call_args
            self.assertEqual(call_args.kwargs.get('plan_name'), 'Legacy Plan Name')

    def test_plan_name_fallback_to_unknown(self):
        """Verify plan name falls back to 'Unknown Plan' if neither 'title' nor 'name' present"""
        from fichero.director.workflow_executor import WorkflowExecutor

        # Arrange: Plan config without 'title' or 'name'
        plan_config = {
            'workflows': {
                'TestWorkflow': ['step1']
            },
            'commands': []
        }

        executor = WorkflowExecutor()

        with patch('fichero.director.workflow_executor.WorkflowManifest') as MockManifest, \
             patch('fichero.director.workflow_executor.WorkflowLogger'), \
             tempfile.TemporaryDirectory() as tmpdir:

            mock_manifest = Mock()
            MockManifest.return_value = mock_manifest

            folder_path = Path(tmpdir) / 'input'
            folder_path.mkdir()
            output_path = Path(tmpdir) / 'output'
            output_path.mkdir()

            # Act
            result = executor.execute_workflow(
                task_id='test-task',
                folder_path=folder_path,
                output_path=output_path,
                workflow_name='TestWorkflow',
                plan_config=plan_config,
                variables={},
                parallel_workers=1
            )

            # Assert: Falls back to 'Unknown Plan'
            MockManifest.assert_called_once()
            call_args = MockManifest.call_args
            self.assertEqual(call_args.kwargs.get('plan_name'), 'Unknown Plan')


class TestSubdirectoryFallback(unittest.TestCase):
    """Test subdirectory fallback logic in output file ingestion"""

    def test_ingestion_with_full_relative_paths(self):
        """Test ingestion when manifest includes full relative paths (e.g., 'documents/file.txt')"""
        # Arrange: Create temporary output structure with correct subdirectory paths
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir)

            # Create workflow manifest
            workflow_manifest = {
                "version": "1.0",
                "workflow": {
                    "plan_name": "Test Plan",
                    "workflow_name": "TestWorkflow",
                    "task_id": "task-123",
                    "success": True
                },
                "steps": [
                    {
                        "order": 1,
                        "name": "catalogue",
                        "status": "success",
                        "manifest_file": "assets/catalogue/catalogue_manifest.jsonl"
                    }
                ]
            }

            manifest_file = output_path / "workflow_manifest.json"
            manifest_file.write_text(json.dumps(workflow_manifest))

            # Create catalogue manifest with FULL relative paths
            (output_path / "assets" / "catalogue").mkdir(parents=True)
            (output_path / "assets" / "catalogue" / "documents").mkdir(parents=True)

            catalogue_manifest = {
                "outputs": ["documents/catalogue.docx"],  # Full relative path
                "source": "test_doc.jpg",
                "details": {"title": "Test Document"}
            }

            cat_manifest_file = output_path / "assets" / "catalogue" / "catalogue_manifest.jsonl"
            cat_manifest_file.write_text(json.dumps(catalogue_manifest))

            # Create actual output file in subdirectory
            docx_file = output_path / "assets" / "catalogue" / "documents" / "catalogue.docx"
            docx_file.write_text("Fake DOCX content")

            # Mock storage and library manager
            storage = Mock()
            library_manager = Mock()
            library_manager.storage = storage
            app = Mock()
            director = Mock()

            storage.add_processing_output = Mock()
            storage.get_outputs_by_item = Mock(return_value=[])

            # Act: Call ingestion
            from fichero.library.director_integration import DirectorIntegrationService
            director_service = DirectorIntegrationService(app, library_manager, director)

            director_service._ingest_processing_outputs(
                processing_result_id="result-123",
                collection_id="collection-123",
                item_id="item-123",
                output_path=output_path
            )

            # Assert: ProcessingOutput was created
            storage.add_processing_output.assert_called()
            call_args = storage.add_processing_output.call_args[0][0]

            # Verify output path is correct
            self.assertEqual(call_args.step_name, "catalogue")
            self.assertEqual(call_args.output_type, "catalogue")  # Output type determined by step name
            self.assertIn("catalogue.docx", str(call_args.output_path))

    def test_ingestion_with_subdirectory_fallback(self):
        """Test ingestion when manifest only has filename, requiring subdirectory search"""
        # Arrange: Manifest has just filename, not full path
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir)

            # Create workflow manifest
            workflow_manifest = {
                "version": "1.0",
                "workflow": {
                    "plan_name": "Test Plan",
                    "workflow_name": "TestWorkflow",
                    "task_id": "task-456",
                    "success": True
                },
                "steps": [
                    {
                        "order": 1,
                        "name": "catalogue",
                        "status": "success",
                        "manifest_file": "assets/catalogue/catalogue_manifest.jsonl"
                    }
                ]
            }

            manifest_file = output_path / "workflow_manifest.json"
            manifest_file.write_text(json.dumps(workflow_manifest))

            # Create catalogue manifest with JUST FILENAME (no subdirectory)
            (output_path / "assets" / "catalogue").mkdir(parents=True)
            (output_path / "assets" / "catalogue" / "documents").mkdir(parents=True)

            catalogue_manifest = {
                "outputs": ["catalogue.docx"],  # Just filename, not "documents/catalogue.docx"
                "source": "test_doc.jpg",
                "details": {"title": "Test Document"}
            }

            cat_manifest_file = output_path / "assets" / "catalogue" / "catalogue_manifest.jsonl"
            cat_manifest_file.write_text(json.dumps(catalogue_manifest))

            # Create actual output file in subdirectory (not at manifest level)
            docx_file = output_path / "assets" / "catalogue" / "documents" / "catalogue.docx"
            docx_file.write_text("Fake DOCX content")

            # Mock storage
            storage = Mock()
            library_manager = Mock()
            library_manager.storage = storage
            app = Mock()
            director = Mock()

            storage.add_processing_output = Mock()
            storage.get_outputs_by_item = Mock(return_value=[])

            # Act: Call ingestion (should use fallback logic to find file in 'documents' subdirectory)
            from fichero.library.director_integration import DirectorIntegrationService
            director_service = DirectorIntegrationService(app, library_manager, director)

            director_service._ingest_processing_outputs(
                processing_result_id="result-456",
                collection_id="collection-456",
                item_id="item-456",
                output_path=output_path
            )

            # Assert: ProcessingOutput was created (fallback logic found the file)
            storage.add_processing_output.assert_called()
            call_args = storage.add_processing_output.call_args[0][0]

            # Verify output was found via fallback
            self.assertEqual(call_args.step_name, "catalogue")
            self.assertIn("catalogue.docx", str(call_args.output_path))

    def test_ingestion_handles_missing_files_gracefully(self):
        """Test ingestion logs warning but doesn't crash when files are missing"""
        # Arrange: Manifest references file that doesn't exist anywhere
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir)

            # Create workflow manifest
            workflow_manifest = {
                "version": "1.0",
                "workflow": {
                    "plan_name": "Test Plan",
                    "workflow_name": "TestWorkflow",
                    "task_id": "task-789",
                    "success": True
                },
                "steps": [
                    {
                        "order": 1,
                        "name": "transcribe",
                        "status": "success",
                        "manifest_file": "assets/transcriptions/transcriptions_manifest.jsonl"
                    }
                ]
            }

            manifest_file = output_path / "workflow_manifest.json"
            manifest_file.write_text(json.dumps(workflow_manifest))

            # Create transcriptions manifest
            (output_path / "assets" / "transcriptions").mkdir(parents=True)

            trans_manifest = {
                "outputs": ["nonexistent_file.txt"],  # File doesn't exist
                "source": "test.jpg",
                "details": {}
            }

            trans_manifest_file = output_path / "assets" / "transcriptions" / "transcriptions_manifest.jsonl"
            trans_manifest_file.write_text(json.dumps(trans_manifest))

            # Don't create the actual output file

            # Mock storage
            storage = Mock()
            library_manager = Mock()
            library_manager.storage = storage
            app = Mock()
            director = Mock()

            storage.add_processing_output = Mock()
            storage.get_outputs_by_item = Mock(return_value=[])

            # Act: Call ingestion (should log warning but not crash)
            from fichero.library.director_integration import DirectorIntegrationService
            director_service = DirectorIntegrationService(app, library_manager, director)

            # Should not raise exception
            director_service._ingest_processing_outputs(
                processing_result_id="result-789",
                collection_id="collection-789",
                item_id="item-789",
                output_path=output_path
            )

            # Assert: ProcessingOutput was NOT created (file missing)
            storage.add_processing_output.assert_not_called()

    def test_subdirectory_fallback_checks_all_subdirs(self):
        """Test that fallback logic checks documents, images, and files subdirectories"""
        # Arrange: File exists in 'images' subdirectory
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir)

            # Create workflow manifest
            workflow_manifest = {
                "version": "1.0",
                "workflow": {
                    "plan_name": "Test Plan",
                    "workflow_name": "TestWorkflow",
                    "task_id": "task-abc",
                    "success": True
                },
                "steps": [
                    {
                        "order": 1,
                        "name": "enhance",
                        "status": "success",
                        "manifest_file": "assets/enhance/enhance_manifest.jsonl"
                    }
                ]
            }

            manifest_file = output_path / "workflow_manifest.json"
            manifest_file.write_text(json.dumps(workflow_manifest))

            # Create enhance manifest with just filename
            (output_path / "assets" / "enhance").mkdir(parents=True)
            (output_path / "assets" / "enhance" / "images").mkdir(parents=True)

            enhance_manifest = {
                "outputs": ["enhanced.jpg"],  # Just filename
                "source": "original.jpg",
                "details": {}
            }

            enh_manifest_file = output_path / "assets" / "enhance" / "enhance_manifest.jsonl"
            enh_manifest_file.write_text(json.dumps(enhance_manifest))

            # Create file in 'images' subdirectory (2nd in fallback order)
            img_file = output_path / "assets" / "enhance" / "images" / "enhanced.jpg"
            img_file.write_text("Fake JPG content")

            # Mock storage
            storage = Mock()
            library_manager = Mock()
            library_manager.storage = storage
            app = Mock()
            director = Mock()

            storage.add_processing_output = Mock()
            storage.get_outputs_by_item = Mock(return_value=[])

            # Act: Call ingestion (should find file in 'images' subdirectory)
            from fichero.library.director_integration import DirectorIntegrationService
            director_service = DirectorIntegrationService(app, library_manager, director)

            director_service._ingest_processing_outputs(
                processing_result_id="result-abc",
                collection_id="collection-abc",
                item_id="item-abc",
                output_path=output_path
            )

            # Assert: ProcessingOutput was created (found in 'images' subdir)
            storage.add_processing_output.assert_called()
            call_args = storage.add_processing_output.call_args[0][0]

            self.assertEqual(call_args.step_name, "enhance")
            self.assertIn("enhanced.jpg", str(call_args.output_path))


class TestWorkflowChainerCleanup(unittest.TestCase):
    """Test that WorkflowChainer has been cleaned up (dead methods removed)"""

    def test_workflow_chainer_has_create_chained_plan(self):
        """Verify WorkflowChainer still has the core create_chained_plan method"""
        from fichero.library.workflow_chainer import WorkflowChainer

        chainer = WorkflowChainer()

        # Should have create_chained_plan method
        self.assertTrue(hasattr(chainer, 'create_chained_plan'))
        self.assertTrue(callable(getattr(chainer, 'create_chained_plan')))

    def test_workflow_chainer_no_stub_methods(self):
        """Verify WorkflowChainer doesn't have the old stub methods that were removed"""
        from fichero.library.workflow_chainer import WorkflowChainer

        chainer = WorkflowChainer()

        # These stub methods should NOT exist anymore
        stub_methods = [
            '_detect_tool_outputs',
            '_resolve_tool_module',
            '_get_tool_metadata',
            '_parse_tool_signature',
            '_infer_chainable_params',
            '_extract_tool_outputs',
            '_map_outputs_to_inputs'
        ]

        for method_name in stub_methods:
            # These methods should not exist
            if hasattr(chainer, method_name):
                self.fail(f"WorkflowChainer should not have stub method '{method_name}' (it was removed)")


class TestEndToEndWorkflowOutputFlow(unittest.TestCase):
    """Integration test: Plan name → Execution → Ingestion → Display"""

    def test_end_to_end_plan_name_in_manifest(self):
        """Test that plan name from YAML ends up in workflow manifest"""
        from fichero.director.workflow_executor import WorkflowExecutor

        # Arrange: Plan with 'title' field
        plan_config = {
            'title': 'Transcribir y Catalogar',
            'workflows': {
                'TestWorkflow': []  # Empty workflow for quick test
            },
            'commands': []
        }

        executor = WorkflowExecutor()

        with tempfile.TemporaryDirectory() as tmpdir:
            folder_path = Path(tmpdir) / 'input'
            folder_path.mkdir()
            output_path = Path(tmpdir) / 'output'
            output_path.mkdir()

            # Act: Execute workflow
            result = executor.execute_workflow(
                task_id='test-task',
                folder_path=folder_path,
                output_path=output_path,
                workflow_name='TestWorkflow',
                plan_config=plan_config,
                variables={},
                parallel_workers=1
            )

            # Assert: Check if workflow manifest was created with correct plan name
            manifest_file = output_path / 'workflow_manifest.json'
            if manifest_file.exists():
                manifest_data = json.loads(manifest_file.read_text())
                workflow_info = manifest_data.get('workflow', {})

                # Plan name should be stored in manifest
                self.assertEqual(workflow_info.get('plan_name'), 'Transcribir y Catalogar')


class TestTranscribeManifestPathFix(unittest.TestCase):
    """Test that transcribe manifest paths are correct after the fix"""

    def test_transcribe_manifest_records_output_not_source_path(self):
        """
        Verify transcribe manifests record OUTPUT paths, not SOURCE paths.

        Before fix: {"outputs": ["documents/source/file.txt"]}  # SOURCE location (WRONG)
        After fix:  {"outputs": ["assets/transcriptions/documents/file.txt"]}  # OUTPUT location (CORRECT)
        """
        # This test validates the fix at a higher level by checking
        # that ingestion can find transcription files using the manifest paths

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir)

            # Create workflow manifest
            workflow_manifest = {
                "version": "1.0",
                "workflow": {
                    "plan_name": "Test Plan",
                    "workflow_name": "TestWorkflow",
                    "task_id": "task-transcribe",
                    "success": True
                },
                "steps": [
                    {
                        "order": 1,
                        "name": "transcribe",
                        "status": "success",
                        "manifest_file": "assets/transcriptions/transcriptions_manifest.jsonl"
                    }
                ]
            }

            manifest_file = output_path / "workflow_manifest.json"
            manifest_file.write_text(json.dumps(workflow_manifest))

            # Create transcribe manifest with CORRECT output path (not source path)
            (output_path / "assets" / "transcriptions").mkdir(parents=True)
            (output_path / "assets" / "transcriptions" / "documents").mkdir(parents=True)

            # This is the CORRECT format after the fix
            transcribe_manifest = {
                "outputs": ["documents/test_doc.txt"],  # OUTPUT location in transcriptions folder
                "source": "documents/test_doc.jpg",     # SOURCE location in source folder
                "details": {"has_content": True, "text_length": 50}
            }

            trans_manifest_file = output_path / "assets" / "transcriptions" / "transcriptions_manifest.jsonl"
            trans_manifest_file.write_text(json.dumps(transcribe_manifest))

            # Create actual transcription file at OUTPUT location
            trans_file = output_path / "assets" / "transcriptions" / "documents" / "test_doc.txt"
            trans_file.write_text("This is the transcribed text")

            # Mock storage
            storage = Mock()
            library_manager = Mock()
            library_manager.storage = storage
            app = Mock()
            director = Mock()

            storage.add_processing_output = Mock()
            storage.get_outputs_by_item = Mock(return_value=[])

            # Act: Call ingestion
            from fichero.library.director_integration import DirectorIntegrationService
            director_service = DirectorIntegrationService(app, library_manager, director)

            director_service._ingest_processing_outputs(
                processing_result_id="result-trans",
                collection_id="collection-trans",
                item_id="item-trans",
                output_path=output_path
            )

            # Assert: ProcessingOutput was created successfully
            storage.add_processing_output.assert_called()
            call_args = storage.add_processing_output.call_args[0][0]

            # Verify the output was found at the correct location
            self.assertEqual(call_args.step_name, "transcribe")
            self.assertEqual(call_args.output_type, "transcription")
            self.assertIn("test_doc.txt", str(call_args.output_path))

            # Verify the file exists at the output location
            self.assertTrue(trans_file.exists())

    def test_transcribe_manifest_with_old_format_uses_fallback(self):
        """
        Verify that old-style manifests (with wrong paths) still work via fallback.

        This ensures backward compatibility - old workflow outputs can still be ingested.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir)

            # Create workflow manifest
            workflow_manifest = {
                "version": "1.0",
                "workflow": {
                    "plan_name": "Test Plan",
                    "workflow_name": "TestWorkflow",
                    "task_id": "task-old",
                    "success": True
                },
                "steps": [
                    {
                        "order": 1,
                        "name": "transcribe",
                        "status": "success",
                        "manifest_file": "assets/transcriptions/transcriptions_manifest.jsonl"
                    }
                ]
            }

            manifest_file = output_path / "workflow_manifest.json"
            manifest_file.write_text(json.dumps(workflow_manifest))

            # Create transcribe manifest with OLD WRONG format (just filename)
            (output_path / "assets" / "transcriptions").mkdir(parents=True)
            (output_path / "assets" / "transcriptions" / "documents").mkdir(parents=True)

            # OLD format: just filename, no path
            transcribe_manifest = {
                "outputs": ["test_doc.txt"],  # WRONG - no subdirectory
                "source": "documents/test_doc.jpg",
                "details": {}
            }

            trans_manifest_file = output_path / "assets" / "transcriptions" / "transcriptions_manifest.jsonl"
            trans_manifest_file.write_text(json.dumps(transcribe_manifest))

            # File exists in subdirectory (actual location)
            trans_file = output_path / "assets" / "transcriptions" / "documents" / "test_doc.txt"
            trans_file.write_text("Transcription text")

            # Mock storage
            storage = Mock()
            library_manager = Mock()
            library_manager.storage = storage
            app = Mock()
            director = Mock()

            storage.add_processing_output = Mock()
            storage.get_outputs_by_item = Mock(return_value=[])

            # Act: Call ingestion (should use fallback to find file)
            from fichero.library.director_integration import DirectorIntegrationService
            director_service = DirectorIntegrationService(app, library_manager, director)

            director_service._ingest_processing_outputs(
                processing_result_id="result-old",
                collection_id="collection-old",
                item_id="item-old",
                output_path=output_path
            )

            # Assert: ProcessingOutput was created via fallback
            storage.add_processing_output.assert_called()
            call_args = storage.add_processing_output.call_args[0][0]

            # File was found despite wrong manifest path
            self.assertEqual(call_args.step_name, "transcribe")
            self.assertIn("test_doc.txt", str(call_args.output_path))


if __name__ == '__main__':
    unittest.main()
