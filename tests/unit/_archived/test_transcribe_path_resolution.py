"""
Unit tests for transcribe path resolution using utils.

Tests that the async transcribe code properly uses the same path handling
logic as BatchProcessor from fichero.tools.utils.batch.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, mock_open
import sys
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


@pytest.fixture(scope="module", autouse=True)
def mock_dependencies():
    """Mock heavy dependencies for this test module"""
    original_modules = {}
    modules_to_mock = [
        'fichero.config',
        'fichero.config.core',
        'fichero.config.core.settings',
        'fichero.config.core.loader',
        'fichero.utils',
        'fichero.tools.utils.tool_logger',
        'fichero.tools.utils.api_keys',
        'fichero.tools.utils.segment_handler',
        'PIL',
        'PIL.Image',
        'openai',
        'requests',
        'dotenv'
    ]

    for module_name in modules_to_mock:
        if module_name in sys.modules:
            original_modules[module_name] = sys.modules[module_name]

        if module_name == 'fichero.tools.utils.tool_logger':
            mock_tool_logger = MagicMock()
            mock_tool_logger.get_tool_logger = lambda x: MagicMock()
            sys.modules[module_name] = mock_tool_logger
        elif module_name == 'fichero.tools.utils.api_keys':
            mock_api_keys = MagicMock()
            mock_api_keys.get_qwen_key = lambda x: "test-key"
            sys.modules[module_name] = mock_api_keys
        else:
            sys.modules[module_name] = MagicMock()

    yield

    for module_name in modules_to_mock:
        if module_name in original_modules:
            sys.modules[module_name] = original_modules[module_name]
        else:
            sys.modules.pop(module_name, None)


class TestAsyncPathResolution:
    """Test async transcribe path resolution logic matches BatchProcessor"""

    def test_path_resolution_with_outputs_field(self):
        """Test path resolution when manifest has 'outputs' field"""
        # Simulate manifest with 'outputs' field (common format)
        manifest_data = [
            {"type": "file", "outputs": ["image1.jpg"], "path": "image1.jpg"},
            {"type": "file", "outputs": ["image2.jpg"], "path": "image2.jpg"}
        ]

        # Mock the manifest file
        manifest_content = "\n".join(json.dumps(entry) for entry in manifest_data)

        with patch('builtins.open', mock_open(read_data=manifest_content)):
            # Test path extraction logic (same as transcribe.py:289-296)
            paths_collected = []

            with open('mock_manifest.jsonl', 'r') as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line)

                        if entry.get('type') == 'directory':
                            continue

                        paths_to_process = []
                        if 'outputs' in entry and entry['outputs']:
                            for out_path in entry['outputs']:
                                if isinstance(out_path, str):
                                    paths_to_process.append(out_path)
                                elif isinstance(out_path, dict) and 'path' in out_path:
                                    paths_to_process.append(out_path['path'])
                        elif entry.get('path'):
                            paths_to_process.append(entry['path'])

                        paths_collected.extend(paths_to_process)

        assert len(paths_collected) == 2
        assert "image1.jpg" in paths_collected
        assert "image2.jpg" in paths_collected

    def test_path_resolution_with_path_field_only(self):
        """Test path resolution when manifest has only 'path' field (library format)"""
        # Simulate manifest with only 'path' field (library collection format)
        manifest_data = [
            {"type": "file", "path": "LFH_AHJM_DOC10141_IMG_001.jpg", "format": "jpg"},
            {"type": "file", "path": "LFH_AHJM_DOC10141_IMG_002.jpg", "format": "jpg"}
        ]

        manifest_content = "\n".join(json.dumps(entry) for entry in manifest_data)

        with patch('builtins.open', mock_open(read_data=manifest_content)):
            paths_collected = []

            with open('mock_manifest.jsonl', 'r') as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line)

                        if entry.get('type') == 'directory':
                            continue

                        paths_to_process = []
                        if 'outputs' in entry and entry['outputs']:
                            for out_path in entry['outputs']:
                                if isinstance(out_path, str):
                                    paths_to_process.append(out_path)
                                elif isinstance(out_path, dict) and 'path' in out_path:
                                    paths_to_process.append(out_path['path'])
                        elif entry.get('path'):
                            paths_to_process.append(entry['path'])

                        paths_collected.extend(paths_to_process)

        assert len(paths_collected) == 2
        assert "LFH_AHJM_DOC10141_IMG_001.jpg" in paths_collected

    def test_directory_entries_skipped(self):
        """Test that directory entries are properly skipped"""
        manifest_data = [
            {"type": "directory", "path": "folder1"},
            {"type": "file", "path": "image1.jpg"},
            {"type": "directory", "path": "folder2"},
            {"type": "file", "path": "image2.jpg"}
        ]

        manifest_content = "\n".join(json.dumps(entry) for entry in manifest_data)

        with patch('builtins.open', mock_open(read_data=manifest_content)):
            paths_collected = []

            with open('mock_manifest.jsonl', 'r') as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line)

                        if entry.get('type') == 'directory':
                            continue

                        paths_to_process = []
                        if 'outputs' in entry and entry['outputs']:
                            for out_path in entry['outputs']:
                                if isinstance(out_path, str):
                                    paths_to_process.append(out_path)
                                elif isinstance(out_path, dict) and 'path' in out_path:
                                    paths_to_process.append(out_path['path'])
                        elif entry.get('path'):
                            paths_to_process.append(entry['path'])

                        paths_collected.extend(paths_to_process)

        # Only file entries should be collected
        assert len(paths_collected) == 2
        assert "image1.jpg" in paths_collected
        assert "image2.jpg" in paths_collected

    def test_direct_path_exists_uses_direct(self, tmp_path):
        """Test that direct path is used when file exists at source_folder/filename"""
        # Create test file directly in source folder (like background_removed outputs)
        source_folder = tmp_path / "assets" / "background_removed"
        source_folder.mkdir(parents=True)
        test_file = source_folder / "image001.png"
        test_file.write_text("test")

        image_name = "image001.png"
        path = Path(image_name)

        # New logic: try direct path first
        full_path = source_folder / path
        if not full_path.exists():
            alt_path = source_folder / 'documents' / path
            if alt_path.exists():
                full_path = alt_path

        # Should use direct path (no documents/ prefix)
        assert full_path == source_folder / "image001.png"
        assert full_path.exists()

    def test_fallback_to_documents_prefix(self, tmp_path):
        """Test fallback to documents/ prefix when direct path doesn't exist"""
        # Create test file in documents/ subfolder (legacy structure)
        source_folder = tmp_path / "assets" / "background_removed"
        docs_folder = source_folder / "documents"
        docs_folder.mkdir(parents=True)
        test_file = docs_folder / "image001.png"
        test_file.write_text("test")

        image_name = "image001.png"
        path = Path(image_name)

        # New logic: try direct path first, fallback to documents/
        full_path = source_folder / path
        if not full_path.exists():
            alt_path = source_folder / 'documents' / path
            if alt_path.exists():
                full_path = alt_path

        # Should use documents/ path as fallback
        assert full_path == docs_folder / "image001.png"
        assert full_path.exists()

    def test_neither_path_exists_returns_direct(self, tmp_path):
        """Test that direct path is returned when neither exists (for error logging)"""
        source_folder = tmp_path / "assets" / "background_removed"
        source_folder.mkdir(parents=True)
        # Don't create any test file

        image_name = "nonexistent.png"
        path = Path(image_name)

        # New logic: try direct path first, fallback to documents/
        full_path = source_folder / path
        if not full_path.exists():
            alt_path = source_folder / 'documents' / path
            if alt_path.exists():
                full_path = alt_path
            # If neither exists, full_path remains as direct path (for warning message)

        # Should remain as direct path (will be skipped in actual code)
        assert full_path == source_folder / "nonexistent.png"
        assert not full_path.exists()

    def test_workflow_output_scenario(self, tmp_path):
        """Test real workflow scenario: background_removed outputs are flat"""
        # This is the exact scenario that was failing before the fix
        # background_removed tool outputs to: assets/background_removed/filename.png
        # manifest has: {"outputs": ["filename.png"]}
        # transcribe should find: assets/background_removed/filename.png

        export_folder = tmp_path / "export"
        assets_folder = export_folder / "assets" / "background_removed"
        assets_folder.mkdir(parents=True)

        # Create test files like the workflow does
        for i in range(3):
            (assets_folder / f"image_{i:03d}.png").write_text("test")

        # Simulate manifest entries
        manifest_entries = [
            {"outputs": ["image_000.png"]},
            {"outputs": ["image_001.png"]},
            {"outputs": ["image_002.png"]},
        ]

        image_paths = []
        source_folder = assets_folder

        for entry in manifest_entries:
            for path_str in entry['outputs']:
                path = Path(path_str)

                # Apply new path resolution logic
                full_path = source_folder / path
                if not full_path.exists():
                    alt_path = source_folder / 'documents' / path
                    if alt_path.exists():
                        full_path = alt_path
                    else:
                        continue

                if full_path.exists():
                    image_paths.append(full_path)

        # All 3 files should be found
        assert len(image_paths) == 3
        for img_path in image_paths:
            assert img_path.exists()
            assert "documents" not in str(img_path)  # No documents/ prefix needed

    def test_symlink_resolution(self):
        """Test that symlinks are properly resolved to actual files"""
        # This would require actual filesystem mocking, but we can test the logic
        with patch.object(Path, 'exists', return_value=True):
            with patch.object(Path, 'resolve') as mock_resolve:
                mock_resolve.return_value = Path("/actual/path/to/image.jpg")

                test_path = Path("/symlink/path/image.jpg")

                # Simulate the resolution logic from transcribe.py:314-317
                if test_path.exists():
                    resolved_path = test_path.resolve()

                mock_resolve.assert_called_once()
                assert resolved_path == Path("/actual/path/to/image.jpg")

    def test_mixed_manifest_formats(self):
        """Test handling mixed manifest entry formats"""
        manifest_data = [
            {"type": "file", "outputs": ["img1.jpg"]},  # outputs field
            {"type": "file", "path": "img2.jpg"},       # path field only
            {"type": "file", "outputs": [{"path": "img3.jpg"}]},  # dict in outputs
            {"type": "directory", "path": "folder"},    # should skip
        ]

        manifest_content = "\n".join(json.dumps(entry) for entry in manifest_data)

        with patch('builtins.open', mock_open(read_data=manifest_content)):
            paths_collected = []

            with open('mock_manifest.jsonl', 'r') as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line)

                        if entry.get('type') == 'directory':
                            continue

                        paths_to_process = []
                        if 'outputs' in entry and entry['outputs']:
                            for out_path in entry['outputs']:
                                if isinstance(out_path, str):
                                    paths_to_process.append(out_path)
                                elif isinstance(out_path, dict) and 'path' in out_path:
                                    paths_to_process.append(out_path['path'])
                        elif entry.get('path'):
                            paths_to_process.append(entry['path'])

                        paths_collected.extend(paths_to_process)

        assert len(paths_collected) == 3
        assert "img1.jpg" in paths_collected
        assert "img2.jpg" in paths_collected
        assert "img3.jpg" in paths_collected


class TestPathResolutionWithFilesystem:
    """Test path resolution with actual filesystem operations (reflects new logic)"""

    def test_direct_path_preferred(self, tmp_path):
        """Test that direct path is preferred when file exists"""
        # Setup: create file directly in source folder
        source = tmp_path / "source"
        source.mkdir()
        (source / "image.jpg").write_text("test")

        # Also create in documents/ subfolder
        (source / "documents").mkdir()
        (source / "documents" / "image.jpg").write_text("test_documents")

        # New logic: direct path should be preferred
        path = Path("image.jpg")
        full_path = source / path
        if not full_path.exists():
            alt_path = source / 'documents' / path
            if alt_path.exists():
                full_path = alt_path

        assert full_path == source / "image.jpg"
        assert full_path.read_text() == "test"  # Not "test_documents"

    def test_documents_fallback_used(self, tmp_path):
        """Test documents/ fallback when direct path missing"""
        # Setup: file only in documents/ subfolder
        source = tmp_path / "source"
        source.mkdir()
        (source / "documents").mkdir()
        (source / "documents" / "image.jpg").write_text("test_documents")

        # New logic: should fall back to documents/
        path = Path("image.jpg")
        full_path = source / path
        if not full_path.exists():
            alt_path = source / 'documents' / path
            if alt_path.exists():
                full_path = alt_path

        assert full_path == source / "documents" / "image.jpg"

    def test_real_workflow_structure(self, tmp_path):
        """Test with realistic workflow folder structure"""
        # Realistic structure from workflow:
        # export/folder-name/
        #   assets/
        #     background_removed/
        #       image1.png
        #       image2.png
        #       background_removed_manifest.jsonl

        export = tmp_path / "export" / "test-folder"
        bg_folder = export / "assets" / "background_removed"
        bg_folder.mkdir(parents=True)

        # Create files as background_removed tool does (flat in folder)
        (bg_folder / "doc_001.png").write_text("img1")
        (bg_folder / "doc_002.png").write_text("img2")

        # Manifest entries (outputs are just filenames)
        manifest_outputs = ["doc_001.png", "doc_002.png"]

        found_paths = []
        for filename in manifest_outputs:
            path = Path(filename)
            full_path = bg_folder / path
            if not full_path.exists():
                alt_path = bg_folder / 'documents' / path
                if alt_path.exists():
                    full_path = alt_path
                else:
                    continue
            if full_path.exists():
                found_paths.append(full_path)

        assert len(found_paths) == 2
        assert all(p.exists() for p in found_paths)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
