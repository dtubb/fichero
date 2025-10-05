"""
Unit tests for Tool Output Editors
"""

import unittest
import tempfile
import json
from pathlib import Path
import shutil

from fichero.library.outputs.base_editor import BaseToolEditor
from fichero.library.outputs.json_editor import JSONEditor
from fichero.library.outputs.image_editor import ImageEditor
from fichero.library.outputs.editor_registry import EditorRegistry


class TestJSONEditor(unittest.TestCase):
    """Test JSONEditor"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.editor = JSONEditor()

    def tearDown(self):
        """Clean up"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_can_edit_json_file(self):
        """Test that JSON editor can edit JSON files"""
        json_file = Path(self.temp_dir) / "test.json"
        json_file.write_text('{"test": true}')

        self.assertTrue(self.editor.can_edit(json_file))

    def test_cannot_edit_non_json_file(self):
        """Test that JSON editor rejects non-JSON files"""
        txt_file = Path(self.temp_dir) / "test.txt"
        txt_file.write_text("plain text")

        self.assertFalse(self.editor.can_edit(txt_file))

    def test_load_json_content(self):
        """Test loading JSON content"""
        json_file = Path(self.temp_dir) / "test.json"
        test_data = {"text": "Sample transcription", "confidence": 0.95}
        json_file.write_text(json.dumps(test_data))

        content = self.editor.load_content(json_file)

        self.assertEqual(content, test_data)
        self.assertEqual(content["text"], "Sample transcription")

    def test_save_json_content(self):
        """Test saving JSON content"""
        json_file = Path(self.temp_dir) / "test.json"
        test_data = {"text": "Edited transcription", "confidence": 0.98}

        result = self.editor.save_content(json_file, test_data)

        self.assertTrue(result)
        self.assertTrue(json_file.exists())

        # Verify saved content
        with open(json_file) as f:
            saved_data = json.load(f)
        self.assertEqual(saved_data, test_data)

    def test_validate_content(self):
        """Test content validation"""
        # Valid JSON-serializable content
        valid_content = {"test": "data"}
        is_valid, error = self.editor.validate_content(valid_content)
        self.assertTrue(is_valid)
        self.assertEqual(error, "")

        # Invalid content (not JSON-serializable)
        invalid_content = {"func": lambda x: x}  # Functions can't be JSON-serialized
        is_valid, error = self.editor.validate_content(invalid_content)
        self.assertFalse(is_valid)
        self.assertIn("not JSON-serializable", error)

    def test_extract_text(self):
        """Test text extraction from transcription"""
        # Standard format
        content1 = {"text": "Extracted text"}
        self.assertEqual(self.editor.extract_text(content1), "Extracted text")

        # Alternative format
        content2 = {"transcription": "Alternative text"}
        self.assertEqual(self.editor.extract_text(content2), "Alternative text")

    def test_pretty_format(self):
        """Test pretty formatting"""
        content = {"text": "test", "number": 42}
        formatted = self.editor.pretty_format(content)

        self.assertIn('"text"', formatted)
        self.assertIn('"number"', formatted)
        # Check it's indented
        self.assertIn('\n', formatted)


class TestImageEditor(unittest.TestCase):
    """Test ImageEditor"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.editor = ImageEditor()

    def tearDown(self):
        """Clean up"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_can_edit_image_files(self):
        """Test that image editor recognizes image files"""
        jpg_file = Path(self.temp_dir) / "test.jpg"
        jpg_file.write_bytes(b"fake image")

        self.assertTrue(self.editor.can_edit(jpg_file))

    def test_cannot_edit_non_image_files(self):
        """Test that image editor rejects non-image files"""
        json_file = Path(self.temp_dir) / "test.json"
        json_file.write_text('{"test": true}')

        self.assertFalse(self.editor.can_edit(json_file))

    def test_load_metadata(self):
        """Test loading image metadata"""
        img_file = Path(self.temp_dir) / "test.jpg"
        img_file.write_bytes(b"fake image data")

        metadata = self.editor.load_content(img_file)

        self.assertIn('size', metadata)
        self.assertIn('name', metadata)
        self.assertEqual(metadata['name'], 'test.jpg')

    def test_cannot_save_images(self):
        """Test that direct image editing is not supported"""
        img_file = Path(self.temp_dir) / "test.jpg"
        img_file.write_bytes(b"fake image")

        result = self.editor.save_content(img_file, b"new data")

        self.assertFalse(result)  # Should fail - not implemented

    def test_get_format_info(self):
        """Test format info extraction"""
        jpg_file = Path(self.temp_dir) / "test.jpg"
        jpg_file.write_bytes(b"fake")

        # Without PIL, should return extension
        format_info = self.editor.get_format_info(jpg_file)
        self.assertIn('JPG', format_info.upper())


class TestEditorRegistry(unittest.TestCase):
    """Test EditorRegistry"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.registry = EditorRegistry()

    def tearDown(self):
        """Clean up"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_get_editor_for_tool(self):
        """Test getting editor by tool name"""
        # JSON tool
        editor = self.registry.get_editor_for_tool('transcribe_qwen_max')
        self.assertIsNotNone(editor)
        self.assertIsInstance(editor, JSONEditor)

        # Image tool
        editor = self.registry.get_editor_for_tool('prepare_images')
        self.assertIsNotNone(editor)
        self.assertIsInstance(editor, ImageEditor)

    def test_get_editor_for_file(self):
        """Test getting editor by file extension"""
        json_file = Path(self.temp_dir) / "test.json"
        editor = self.registry.get_editor_for_file(json_file)
        self.assertIsInstance(editor, JSONEditor)

        jpg_file = Path(self.temp_dir) / "test.jpg"
        editor = self.registry.get_editor_for_file(jpg_file)
        self.assertIsInstance(editor, ImageEditor)

    def test_get_editor_for_tool_and_file(self):
        """Test getting editor by tool and file"""
        json_file = Path(self.temp_dir) / "test.json"

        editor = self.registry.get_editor_for_tool_and_file('transcribe_qwen_max', json_file)
        self.assertIsInstance(editor, JSONEditor)

    def test_can_edit_file(self):
        """Test checking if file can be edited"""
        json_file = Path(self.temp_dir) / "test.json"
        self.assertTrue(self.registry.can_edit_file(json_file))

        jpg_file = Path(self.temp_dir) / "test.jpg"
        self.assertFalse(self.registry.can_edit_file(jpg_file))  # Images not editable yet

    def test_list_editors(self):
        """Test listing all editors"""
        editors = self.registry.list_editors()

        self.assertGreater(len(editors), 0)
        # Should have at least JSON and Image editors
        editor_types = [type(e).__name__ for e in editors]
        self.assertIn('JSONEditor', editor_types)
        self.assertIn('ImageEditor', editor_types)

    def test_no_editor_for_unknown_file(self):
        """Test that unknown files return no editor"""
        unknown_file = Path(self.temp_dir) / "test.xyz"
        editor = self.registry.get_editor_for_file(unknown_file)
        self.assertIsNone(editor)


class TestBaseToolEditor(unittest.TestCase):
    """Test BaseToolEditor base class functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()

        # Create a concrete test editor
        class TestEditor(BaseToolEditor):
            tool_name = "test"
            supported_extensions = ['.txt']

            def can_edit(self, file_path):
                return file_path.suffix == '.txt'

            def load_content(self, file_path):
                return file_path.read_text()

            def save_content(self, file_path, content):
                file_path.write_text(content)
                return True

        self.editor = TestEditor()

    def tearDown(self):
        """Clean up"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_get_metadata(self):
        """Test getting file metadata"""
        test_file = Path(self.temp_dir) / "test.txt"
        test_file.write_text("test content")

        metadata = self.editor.get_metadata(test_file)

        self.assertIn('size', metadata)
        self.assertIn('name', metadata)
        self.assertIn('extension', metadata)
        self.assertEqual(metadata['name'], 'test.txt')
        self.assertEqual(metadata['extension'], '.txt')

    def test_validate_content_default(self):
        """Test default content validation (always valid)"""
        is_valid, error = self.editor.validate_content("any content")
        self.assertTrue(is_valid)
        self.assertEqual(error, "")


if __name__ == '__main__':
    unittest.main()
