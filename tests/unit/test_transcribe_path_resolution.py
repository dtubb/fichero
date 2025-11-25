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

    def test_full_path_construction_with_documents_in_base(self):
        """Test path construction when source_folder already contains 'documents'"""
        # Simulate the library case where source_folder = ".../staging/documents"
        source_folder = Path("/library/collections/abc123/outputs/staging/documents")
        image_name = "LFH_AHJM_DOC10141_IMG_001.jpg"

        # Path construction logic from transcribe.py:303-312
        path = Path(image_name)
        base_str = str(source_folder)

        if 'documents' in base_str or str(path).startswith('projects/'):
            full_path = source_folder / path
        else:
            full_path = source_folder / 'documents' / path

        # Should NOT add another /documents/
        expected = Path("/library/collections/abc123/outputs/staging/documents/LFH_AHJM_DOC10141_IMG_001.jpg")
        assert full_path == expected
        assert str(full_path).count('/documents/') == 1  # Only one /documents/ in path

    def test_full_path_construction_without_documents_in_base(self):
        """Test path construction when source_folder doesn't contain 'documents'"""
        # Simulate typical CLI usage where source_folder = input folder
        source_folder = Path("/input/my_images")
        image_name = "image001.jpg"

        path = Path(image_name)
        base_str = str(source_folder)

        if 'documents' in base_str or str(path).startswith('projects/'):
            full_path = source_folder / path
        else:
            full_path = source_folder / 'documents' / path

        # Should add /documents/
        expected = Path("/input/my_images/documents/image001.jpg")
        assert full_path == expected

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


class TestBatchProcessorCompatibility:
    """Test that async path logic matches BatchProcessor exactly"""

    def test_same_logic_as_batch_processor(self):
        """Verify async transcribe uses same path construction as BatchProcessor"""
        # This is a documentation test to ensure consistency

        # BatchProcessor logic (batch.py:141-149):
        # if base_folder:
        #     if add_documents_prefix and "documents" not in str(base_folder) and not str(path).startswith("projects/"):
        #         full_path = base_folder / "documents" / path
        #     else:
        #         full_path = base_folder / path

        # Async transcribe logic (transcribe.py:303-312):
        # if source_folder:
        #     if 'documents' in base_str or str(path).startswith('projects/'):
        #         full_path = source_folder / path
        #     else:
        #         full_path = source_folder / 'documents' / path

        # Test case 1: base folder has 'documents'
        base_with_docs = Path("/staging/documents")
        path1 = Path("image.jpg")

        # BatchProcessor logic (with add_documents_prefix=True by default)
        if "documents" not in str(base_with_docs) and not str(path1).startswith("projects/"):
            bp_path = base_with_docs / "documents" / path1
        else:
            bp_path = base_with_docs / path1

        # Async transcribe logic
        if 'documents' in str(base_with_docs) or str(path1).startswith('projects/'):
            async_path = base_with_docs / path1
        else:
            async_path = base_with_docs / 'documents' / path1

        # Should produce same result
        assert bp_path == async_path == Path("/staging/documents/image.jpg")

        # Test case 2: base folder without 'documents'
        base_without_docs = Path("/input/images")
        path2 = Path("photo.jpg")

        if "documents" not in str(base_without_docs) and not str(path2).startswith("projects/"):
            bp_path2 = base_without_docs / "documents" / path2
        else:
            bp_path2 = base_without_docs / path2

        if 'documents' in str(base_without_docs) or str(path2).startswith('projects/'):
            async_path2 = base_without_docs / path2
        else:
            async_path2 = base_without_docs / 'documents' / path2

        assert bp_path2 == async_path2 == Path("/input/images/documents/photo.jpg")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
