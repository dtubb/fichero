"""
Unit tests for OutputsManager

Tests the core workflow outputs management system.
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import json

from fichero.library.outputs_manager import OutputsManager, ToolOutput, OutputSession


class TestOutputsManager(unittest.TestCase):
    """Test OutputsManager core functionality"""

    def setUp(self):
        """Set up test fixtures"""
        # Create temp directory structure that mimics Director output
        self.temp_dir = tempfile.mkdtemp()
        self.output_path = Path(self.temp_dir) / "test_output"
        self.output_path.mkdir()

        # Create typical Director output structure
        self._create_test_structure()

        # Create OutputsManager instance
        self.manager = OutputsManager()

    def tearDown(self):
        """Clean up test fixtures"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def _create_test_structure(self):
        """Create realistic Director output structure"""
        # Documents folder (input)
        docs_dir = self.output_path / "documents"
        docs_dir.mkdir()
        (docs_dir / "test001.jpg").write_text("fake image 1")
        (docs_dir / "test002.jpg").write_text("fake image 2")

        # Assets folder
        assets_dir = self.output_path / "assets"
        assets_dir.mkdir()

        # Manifests
        manifests_dir = assets_dir / "manifests"
        manifests_dir.mkdir()

        # Documents manifest
        docs_manifest = manifests_dir / "documents_manifest.jsonl"
        with open(docs_manifest, 'w') as f:
            f.write(json.dumps({"source": "documents/test001.jpg", "size": 1000}) + "\n")
            f.write(json.dumps({"source": "documents/test002.jpg", "size": 2000}) + "\n")

        # Prepared images
        prepared_dir = assets_dir / "prepared"
        prepared_dir.mkdir()
        (prepared_dir / "test001.jpg").write_text("prepared image 1")
        (prepared_dir / "test002.jpg").write_text("prepared image 2")

        # Prepared manifest
        prepared_manifest = prepared_dir / "prepare_images_manifest.jsonl"
        with open(prepared_manifest, 'w') as f:
            f.write(json.dumps({
                "source": "documents/test001.jpg",
                "output": "assets/prepared/test001.jpg",
                "tool": "prepare_images",
                "params": {"output_format": "jpg", "compression_quality": 85}
            }) + "\n")
            f.write(json.dumps({
                "source": "documents/test002.jpg",
                "output": "assets/prepared/test002.jpg",
                "tool": "prepare_images",
                "params": {"output_format": "jpg", "compression_quality": 85}
            }) + "\n")

        # Transcriptions
        transcriptions_dir = assets_dir / "transcriptions"
        transcriptions_dir.mkdir()
        (transcriptions_dir / "test001.json").write_text('{"text": "Sample transcription 1"}')
        (transcriptions_dir / "test002.json").write_text('{"text": "Sample transcription 2"}')

        # Transcriptions manifest
        trans_manifest = transcriptions_dir / "transcriptions_manifest.jsonl"
        with open(trans_manifest, 'w') as f:
            f.write(json.dumps({
                "source": "assets/prepared/test001.jpg",
                "output": "assets/transcriptions/test001.json",
                "tool": "transcribe_qwen_max",
                "params": {}
            }) + "\n")
            f.write(json.dumps({
                "source": "assets/prepared/test002.jpg",
                "output": "assets/transcriptions/test002.json",
                "tool": "transcribe_qwen_max",
                "params": {}
            }) + "\n")

    def test_load_output_folder(self):
        """Test loading an output folder"""
        session = self.manager.load_output_folder(self.output_path)

        self.assertIsNotNone(session)
        self.assertIsInstance(session, OutputSession)
        self.assertEqual(session.output_path, self.output_path)

    def test_list_tools(self):
        """Test listing all tools in output folder"""
        session = self.manager.load_output_folder(self.output_path)
        tools = self.manager.list_tools(session)

        self.assertIsInstance(tools, list)
        self.assertGreater(len(tools), 0)

        # Should find prepare_images and transcribe_qwen_max
        tool_names = [t.tool_name for t in tools]
        self.assertIn("prepare_images", tool_names)
        self.assertIn("transcribe_qwen_max", tool_names)

    def test_get_tool_output(self):
        """Test getting specific tool output"""
        session = self.manager.load_output_folder(self.output_path)
        tool_output = self.manager.get_tool_output(session, "prepare_images")

        self.assertIsNotNone(tool_output)
        self.assertIsInstance(tool_output, ToolOutput)
        self.assertEqual(tool_output.tool_name, "prepare_images")
        self.assertTrue(tool_output.output_folder.exists())
        self.assertTrue(tool_output.manifest_path.exists())

    def test_get_tool_files(self):
        """Test getting files for a tool"""
        session = self.manager.load_output_folder(self.output_path)
        tool_output = self.manager.get_tool_output(session, "prepare_images")

        files = tool_output.files
        self.assertEqual(len(files), 2)
        self.assertTrue(all(f.exists() for f in files))

    def test_get_tool_parameters(self):
        """Test extracting tool parameters from manifest"""
        session = self.manager.load_output_folder(self.output_path)
        tool_output = self.manager.get_tool_output(session, "prepare_images")

        params = tool_output.parameters
        self.assertIsInstance(params, dict)
        self.assertIn("output_format", params)
        self.assertEqual(params["output_format"], "jpg")

    def test_nonexistent_tool(self):
        """Test requesting nonexistent tool"""
        session = self.manager.load_output_folder(self.output_path)
        tool_output = self.manager.get_tool_output(session, "nonexistent_tool")

        self.assertIsNone(tool_output)

    def test_invalid_output_folder(self):
        """Test loading invalid output folder"""
        invalid_path = Path(self.temp_dir) / "nonexistent"

        with self.assertRaises(FileNotFoundError):
            self.manager.load_output_folder(invalid_path)


class TestToolOutput(unittest.TestCase):
    """Test ToolOutput data class"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.output_folder = Path(self.temp_dir) / "output"
        self.output_folder.mkdir()

        # Create test files
        (self.output_folder / "test1.jpg").write_text("test")
        (self.output_folder / "test2.jpg").write_text("test")

        # Create manifest
        self.manifest_path = self.output_folder / "test_manifest.jsonl"
        with open(self.manifest_path, 'w') as f:
            f.write(json.dumps({"param1": "value1", "param2": 42}) + "\n")

    def tearDown(self):
        """Clean up"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_tool_output_creation(self):
        """Test creating ToolOutput instance"""
        tool = ToolOutput(
            tool_name="test_tool",
            output_folder=self.output_folder,
            manifest_path=self.manifest_path
        )

        self.assertEqual(tool.tool_name, "test_tool")
        self.assertEqual(tool.output_folder, self.output_folder)
        self.assertEqual(tool.manifest_path, self.manifest_path)

    def test_files_property(self):
        """Test files property lists all output files"""
        tool = ToolOutput(
            tool_name="test_tool",
            output_folder=self.output_folder,
            manifest_path=self.manifest_path
        )

        files = tool.files
        # Should exclude manifest file itself
        image_files = [f for f in files if f.suffix == '.jpg']
        self.assertEqual(len(image_files), 2)

    def test_parameters_property(self):
        """Test parameters property reads manifest"""
        tool = ToolOutput(
            tool_name="test_tool",
            output_folder=self.output_folder,
            manifest_path=self.manifest_path
        )

        params = tool.parameters
        self.assertIn("param1", params)
        self.assertEqual(params["param1"], "value1")
        self.assertEqual(params["param2"], 42)


if __name__ == '__main__':
    unittest.main()
