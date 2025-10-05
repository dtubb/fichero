"""
Unit tests for PreviewContent integration with OutputsManager and EditorRegistry
"""

import unittest
import tempfile
import json
from pathlib import Path
import shutil

from fichero.windows.preview.preview_content import PreviewContent
from fichero.library.outputs_manager import OutputsManager
from fichero.library.outputs.editor_registry import EditorRegistry


class MockApp:
    """Mock Toga app for testing"""
    pass


class TestPreviewContentIntegration(unittest.TestCase):
    """Test PreviewContent integration with outputs system"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.output_root = Path(self.temp_dir) / "test_output"

        # Create Director output structure
        self._create_test_output_structure()

        self.mock_app = MockApp()

    def tearDown(self):
        """Clean up"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def _create_test_output_structure(self):
        """Create realistic Director output structure"""
        # Create directories
        (self.output_root / "documents").mkdir(parents=True)
        (self.output_root / "assets" / "manifests").mkdir(parents=True)
        (self.output_root / "assets" / "prepared").mkdir(parents=True)
        (self.output_root / "assets" / "transcriptions").mkdir(parents=True)

        # Create documents
        doc1 = self.output_root / "documents" / "test001.jpg"
        doc2 = self.output_root / "documents" / "test002.jpg"
        doc1.write_bytes(b"fake image 1")
        doc2.write_bytes(b"fake image 2")

        # Create manifests
        doc_manifest = self.output_root / "assets" / "manifests" / "documents_manifest.jsonl"
        doc_manifest.write_text(
            json.dumps({"file": "test001.jpg", "size": 12}) + "\n" +
            json.dumps({"file": "test002.jpg", "size": 12}) + "\n"
        )

        prep_manifest = self.output_root / "assets" / "prepared" / "prepare_images_manifest.jsonl"
        prep_manifest.write_text(
            json.dumps({"input": "test001.jpg", "output": "test001.jpg"}) + "\n" +
            json.dumps({"input": "test002.jpg", "output": "test002.jpg"}) + "\n"
        )

        trans_manifest = self.output_root / "assets" / "transcriptions" / "transcriptions_manifest.jsonl"
        trans_manifest.write_text(
            json.dumps({"input": "test001.jpg", "output": "test001.json"}) + "\n" +
            json.dumps({"input": "test002.jpg", "output": "test002.json"}) + "\n"
        )

        # Create prepared images
        prep1 = self.output_root / "assets" / "prepared" / "test001.jpg"
        prep2 = self.output_root / "assets" / "prepared" / "test002.jpg"
        prep1.write_bytes(b"prepared image 1")
        prep2.write_bytes(b"prepared image 2")

        # Create transcriptions
        trans1 = self.output_root / "assets" / "transcriptions" / "test001.json"
        trans2 = self.output_root / "assets" / "transcriptions" / "test002.json"
        trans1.write_text(json.dumps({"text": "Transcription 1"}))
        trans2.write_text(json.dumps({"text": "Transcription 2"}))

    def test_find_output_root(self):
        """Test finding Director output root from file path"""
        # Create PreviewContent with a transcription file
        trans_file = self.output_root / "assets" / "transcriptions" / "test001.json"
        preview = PreviewContent(self.mock_app, file_path=str(trans_file))

        # Test finding output root
        output_root = preview._find_output_root(trans_file)

        self.assertIsNotNone(output_root)
        self.assertEqual(output_root, self.output_root)

    def test_find_output_root_non_output_file(self):
        """Test that non-Director files return None"""
        # Create a file outside Director structure
        other_file = Path(self.temp_dir) / "other.json"
        other_file.write_text('{"test": true}')

        preview = PreviewContent(self.mock_app, file_path=str(other_file))
        output_root = preview._find_output_root(other_file)

        self.assertIsNone(output_root)

    def test_detect_director_output(self):
        """Test detecting Director output and loading steps"""
        trans_file = self.output_root / "assets" / "transcriptions" / "test001.json"
        preview = PreviewContent(self.mock_app, file_path=str(trans_file))

        # Manually call detection (normally called in create())
        preview._detect_director_output()

        # Verify output session loaded
        self.assertIsNotNone(preview.output_session)
        self.assertGreater(len(preview.processing_steps), 0)

        # Verify we have the expected steps
        step_names = [step.tool_name for step in preview.processing_steps]
        self.assertIn("prepare_images", step_names)
        self.assertIn("transcribe_qwen_max", step_names)

    def test_find_current_step(self):
        """Test finding which step the current file belongs to"""
        trans_file = self.output_root / "assets" / "transcriptions" / "test001.json"
        preview = PreviewContent(self.mock_app, file_path=str(trans_file))

        # Load output session
        preview._detect_director_output()

        # Verify current step is transcription
        current_step = preview.processing_steps[preview.current_step_index]
        self.assertEqual(current_step.tool_name, "transcribe_qwen_max")

    def test_find_current_step_prepared_image(self):
        """Test finding step for prepared image file"""
        prep_file = self.output_root / "assets" / "prepared" / "test001.jpg"
        preview = PreviewContent(self.mock_app, file_path=str(prep_file))

        # Load output session
        preview._detect_director_output()

        # Verify current step is prepare_images
        current_step = preview.processing_steps[preview.current_step_index]
        self.assertEqual(current_step.tool_name, "prepare_images")

    def test_editor_detection_json(self):
        """Test that JSON files get JSONEditor"""
        trans_file = self.output_root / "assets" / "transcriptions" / "test001.json"
        preview = PreviewContent(self.mock_app, file_path=str(trans_file))

        # Test editor detection
        editor = preview.editor_registry.get_editor_for_file(Path(trans_file))

        self.assertIsNotNone(editor)
        self.assertEqual(editor.__class__.__name__, "JSONEditor")

    def test_can_edit_file_json(self):
        """Test that JSON files are editable"""
        trans_file = self.output_root / "assets" / "transcriptions" / "test001.json"
        preview = PreviewContent(self.mock_app, file_path=str(trans_file))

        # Test editability
        can_edit = preview._can_edit_file()

        self.assertTrue(can_edit)

    def test_can_edit_file_image(self):
        """Test that image files are not editable (yet)"""
        prep_file = self.output_root / "assets" / "prepared" / "test001.jpg"
        preview = PreviewContent(self.mock_app, file_path=str(prep_file))

        # Test editability
        can_edit = preview._can_edit_file()

        # Images should not be directly editable yet (ImageEditor.can_edit_files = False)
        self.assertFalse(can_edit)

    def test_step_navigation_boundaries(self):
        """Test step navigation at boundaries"""
        trans_file = self.output_root / "assets" / "transcriptions" / "test001.json"
        preview = PreviewContent(self.mock_app, file_path=str(trans_file))

        # Load output session
        preview._detect_director_output()

        # Test at last step
        preview.current_step_index = len(preview.processing_steps) - 1
        can_go_next = preview.current_step_index < len(preview.processing_steps) - 1
        can_go_prev = preview.current_step_index > 0

        self.assertFalse(can_go_next)  # Cannot go forward from last step
        self.assertTrue(can_go_prev)   # Can go back

        # Test at first step
        preview.current_step_index = 0
        can_go_next = preview.current_step_index < len(preview.processing_steps) - 1
        can_go_prev = preview.current_step_index > 0

        self.assertTrue(can_go_next)   # Can go forward
        self.assertFalse(can_go_prev)  # Cannot go back from first step

    def test_no_director_output_detection(self):
        """Test that non-Director files don't trigger step navigation"""
        # Create a file outside Director structure
        other_file = Path(self.temp_dir) / "other.json"
        other_file.write_text('{"test": true}')

        preview = PreviewContent(self.mock_app, file_path=str(other_file))
        preview._detect_director_output()

        # Verify no output session loaded
        self.assertIsNone(preview.output_session)
        self.assertEqual(len(preview.processing_steps), 0)


if __name__ == '__main__':
    unittest.main()
