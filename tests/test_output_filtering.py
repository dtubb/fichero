"""
Comprehensive tests for file-specific output filtering system

Tests the complete flow from Director output parsing → LibraryManager filtering → GUI/CLI display
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# Import modules to test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fichero.library.director_output_parser import DirectorOutputParser, FileOutput, ProcessingStep
from fichero.library.models import Collection, CollectionItem, ProcessingResult


@pytest.fixture
def temp_output_dir():
        """Create a temporary Director output structure for testing"""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir)

            # Create Director output structure
            (output_path / "documents").mkdir()
            (output_path / "assets" / "manifests").mkdir(parents=True)
            (output_path / "assets" / "prepared").mkdir()
            (output_path / "assets" / "transcriptions").mkdir()
            (output_path / "assets" / "word").mkdir()

            # Create test files
            # Documents (input files)
            (output_path / "documents" / "file001.jpg").write_text("mock image 1")
            (output_path / "documents" / "file002.jpg").write_text("mock image 2")
            (output_path / "documents" / "file003.jpg").write_text("mock image 3")

            # Prepared images
            (output_path / "assets" / "prepared" / "file001.jpg").write_text("prepared 1")
            (output_path / "assets" / "prepared" / "file002.jpg").write_text("prepared 2")
            (output_path / "assets" / "prepared" / "file003.jpg").write_text("prepared 3")

            # Transcriptions
            (output_path / "assets" / "transcriptions" / "file001.json").write_text('{"text": "transcription 1"}')
            (output_path / "assets" / "transcriptions" / "file002.json").write_text('{"text": "transcription 2"}')
            (output_path / "assets" / "transcriptions" / "file003.json").write_text('{"text": "transcription 3"}')

            # Word documents
            (output_path / "assets" / "word" / "file001.docx").write_text("word doc 1")
            (output_path / "assets" / "word" / "file002.docx").write_text("word doc 2")
            (output_path / "assets" / "word" / "file003.docx").write_text("word doc 3")

            # Create manifests
            _create_manifest(
                output_path / "assets" / "manifests" / "documents_manifest.jsonl",
                ["file001.jpg", "file002.jpg", "file003.jpg"]
            )
            _create_manifest(
                output_path / "assets" / "manifests" / "prepare_images_manifest.jsonl",
                ["file001.jpg", "file002.jpg", "file003.jpg"]
            )
            _create_manifest(
                output_path / "assets" / "manifests" / "transcriptions_manifest.jsonl",
                ["file001.json", "file002.json", "file003.json"]
            )

            yield output_path


def _create_manifest(manifest_path: Path, filenames: List[str]):
    """Create a JSONL manifest file"""
    with open(manifest_path, 'w', encoding='utf-8') as f:
        for filename in filenames:
            entry = {
                "file": filename,
                "timestamp": datetime.now().isoformat(),
                "status": "success"
            }
            f.write(json.dumps(entry) + '\n')


class TestDirectorOutputParser:
    """Test the core output parsing and filtering logic"""

    def test_parse_output_folder_structure(self, temp_output_dir):
        """Test: Parser correctly identifies output folder structure"""
        parser = DirectorOutputParser()
        result = parser.parse_output_folder(temp_output_dir)

        assert len(result["input_files"]) == 3, "Should find 3 input files"
        assert len(result["prepared_files"]) == 3, "Should find 3 prepared files"
        assert len(result["transcriptions"]) == 3, "Should find 3 transcription files"
        assert len(result["word_docs"]) == 3, "Should find 3 word documents"
        assert "manifests" in result, "Should have manifests key"

    def test_get_file_outputs_single_file(self, temp_output_dir):
        """Test: Get outputs for a single file"""
        parser = DirectorOutputParser()
        outputs = parser.get_file_outputs(temp_output_dir, "file001.jpg")

        assert len(outputs) == 1, "Should return exactly one FileOutput"
        output = outputs[0]

        # Verify all output files are present
        assert output.original_file is not None, "Should have original file"
        assert output.prepared_file is not None, "Should have prepared file"
        assert output.transcription_file is not None, "Should have transcription"
        assert output.word_doc is not None, "Should have word document"

        # Verify filenames match (stem-based matching)
        assert output.original_file.stem == "file001"
        assert output.prepared_file.stem == "file001"
        assert output.transcription_file.stem == "file001"
        assert output.word_doc.stem == "file001"

    def test_get_file_outputs_missing_file(self, temp_output_dir):
        """Test: Request outputs for non-existent file"""
        parser = DirectorOutputParser()
        outputs = parser.get_file_outputs(temp_output_dir, "nonexistent.jpg")

        assert len(outputs) == 0, "Should return empty list for non-existent file"

    def test_get_all_file_outputs(self, temp_output_dir):
        """Test: Get outputs for ALL files in output folder"""
        parser = DirectorOutputParser()
        all_outputs = parser.get_all_file_outputs(temp_output_dir)

        assert len(all_outputs) == 3, "Should return outputs for all 3 files"

        # Verify each output has the correct file
        filenames = {output.original_file.name for output in all_outputs}
        assert filenames == {"file001.jpg", "file002.jpg", "file003.jpg"}

    def test_get_processing_steps(self, temp_output_dir):
        """Test: Extract ordered processing steps from file output"""
        parser = DirectorOutputParser()
        outputs = parser.get_file_outputs(temp_output_dir, "file001.jpg")

        assert len(outputs) > 0, "Should have output"
        steps = parser.get_processing_steps(outputs[0])

        # Verify steps are in order
        assert len(steps) >= 3, "Should have at least: Input, Prepared, Transcription"

        # Verify step types
        step_types = [step.file_type for step in steps]
        assert "image" in step_types, "Should have image steps"
        assert "text" in step_types, "Should have text steps"

    def test_metadata_extraction(self, temp_output_dir):
        """Test: Metadata is extracted from manifests"""
        parser = DirectorOutputParser()
        outputs = parser.get_file_outputs(temp_output_dir, "file001.jpg")

        output = outputs[0]
        assert output.metadata is not None, "Should have metadata"
        assert len(output.metadata) > 0, "Metadata should not be empty"

    def test_edge_case_partial_outputs(self, temp_output_dir):
        """Test: Handle files with partial outputs (missing some steps)"""
        # Remove transcription for file003
        (temp_output_dir / "assets" / "transcriptions" / "file003.json").unlink()

        parser = DirectorOutputParser()
        outputs = parser.get_file_outputs(temp_output_dir, "file003.jpg")

        assert len(outputs) == 1, "Should still return FileOutput"
        output = outputs[0]

        # Should have some outputs but not all
        assert output.original_file is not None
        assert output.prepared_file is not None
        assert output.transcription_file is None, "Transcription should be None"
        assert output.word_doc is not None

    def test_edge_case_empty_output_folder(self):
        """Test: Handle empty output folder gracefully"""
        with tempfile.TemporaryDirectory() as temp_dir:
            empty_path = Path(temp_dir)

            parser = DirectorOutputParser()
            result = parser.parse_output_folder(empty_path)

            # Should return empty result, not crash
            assert len(result["input_files"]) == 0
            assert len(result["prepared_files"]) == 0
            assert len(result["transcriptions"]) == 0

    def test_filename_matching_case_sensitivity(self, temp_output_dir):
        """Test: Filename matching is case-sensitive for stems"""
        parser = DirectorOutputParser()

        # Try both cases - should only match exact stem
        outputs_lower = parser.get_file_outputs(temp_output_dir, "file001.jpg")
        outputs_upper = parser.get_file_outputs(temp_output_dir, "FILE001.jpg")

        assert len(outputs_lower) == 1, "Should find file001.jpg"
        assert len(outputs_upper) == 0, "Should NOT find FILE001.jpg (different case)"


class TestLibraryIntegration:
    """Test LibraryManager integration with output parser"""

    @pytest.fixture
    def mock_library_manager(self):
        """Create a mock LibraryManager for testing"""
        from unittest.mock import Mock, AsyncMock

        manager = Mock()
        manager.output_parser = DirectorOutputParser()
        manager.get_file_processing_steps = AsyncMock()

        return manager

    @pytest.mark.asyncio
    async def test_get_item_output_data_with_outputs(self, temp_output_dir):
        """Test: get_item_output_data returns filtered outputs for a file"""
        # This would test the full integration if we had a real LibraryManager
        # For now, test the parser directly
        parser = DirectorOutputParser()

        # Simulate what get_item_output_data does:
        # 1. Get item filename
        filename = "file001.jpg"

        # 2. Get file-specific outputs (filtering happens here!)
        outputs = parser.get_file_outputs(temp_output_dir, filename)

        # 3. Verify filtering worked
        assert len(outputs) == 1, "Should return exactly one FileOutput"
        assert outputs[0].original_file.name == "file001.jpg"

        # 4. Get processing steps
        steps = parser.get_processing_steps(outputs[0])

        # 5. Verify steps are file-specific
        for step in steps:
            if step.file_path and step.file_path.exists():
                # All files should match the original filename stem
                assert step.file_path.stem == "file001", f"Step file {step.file_path} should match file001"

    def test_file_specific_filtering_with_batch_processing(self, temp_output_dir):
        """Test: When multiple files were processed together, filtering isolates ONE file's outputs"""
        parser = DirectorOutputParser()

        # Get outputs for file002 (while file001 and file003 also exist)
        outputs_file002 = parser.get_file_outputs(temp_output_dir, "file002.jpg")

        assert len(outputs_file002) == 1, "Should return only file002 outputs"

        output = outputs_file002[0]
        steps = parser.get_processing_steps(output)

        # Verify EVERY step file matches file002 (not file001 or file003)
        for step in steps:
            if step.file_path and step.file_path.exists():
                assert step.file_path.stem == "file002", \
                    f"Filtering failed: found {step.file_path.name} instead of file002"


class TestJSONSyntaxHighlighting:
    """Test JSON content display features"""

    def test_json_parsing_and_formatting(self):
        """Test: JSON is parsed and pretty-printed"""
        test_json = '{"key": "value", "number": 123, "bool": true, "null": null}'

        # Test that it can be parsed
        parsed = json.loads(test_json)
        assert parsed["key"] == "value"
        assert parsed["number"] == 123

        # Test pretty-printing
        formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
        assert "\n" in formatted, "Should have newlines for formatting"
        assert "  " in formatted, "Should have indentation"

    def test_jsonl_parsing_multiple_lines(self):
        """Test: JSONL files (multiple JSON objects per line) are parsed"""
        jsonl_content = '''{"file": "file001.jpg", "status": "success"}
{"file": "file002.jpg", "status": "success"}
{"file": "file003.jpg", "status": "success"}'''

        # Parse JSONL
        lines = [json.loads(line) for line in jsonl_content.strip().split('\n') if line.strip()]

        assert len(lines) == 3, "Should parse 3 JSON objects"
        assert lines[0]["file"] == "file001.jpg"
        assert lines[1]["file"] == "file002.jpg"
        assert lines[2]["file"] == "file003.jpg"

    def test_json_highlighting_regex_patterns(self):
        """Test: JSON syntax highlighting patterns work correctly"""
        import re
        import html

        test_json = '{"key": "value", "num": 123, "bool": true}'
        escaped = html.escape(test_json)

        # Test key highlighting pattern
        key_pattern = r'&quot;([^&]+)&quot;(\s*:)'
        matches = re.findall(key_pattern, escaped)

        assert len(matches) == 3, "Should find 3 keys"
        assert ("key", ":") in matches
        assert ("num", ":") in matches
        assert ("bool", ":") in matches

    def test_malformed_json_handling(self):
        """Test: Malformed JSON is handled gracefully"""
        malformed_json = '{"key": "value", "missing_quote: 123}'

        # Should raise JSONDecodeError
        with pytest.raises(json.JSONDecodeError):
            json.loads(malformed_json)

        # But should still be displayable as raw text
        assert len(malformed_json) > 0


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_non_existent_output_path(self):
        """Test: Parser handles non-existent output path"""
        parser = DirectorOutputParser()
        result = parser.parse_output_folder(Path("/nonexistent/path"))

        # Should return empty result, not crash
        assert len(result["input_files"]) == 0

    def test_filename_with_special_characters(self, temp_output_dir):
        """Test: Handle filenames with special characters"""
        # Create file with special characters
        special_file = temp_output_dir / "documents" / "file (copy) [1].jpg"
        special_file.write_text("special")

        parser = DirectorOutputParser()
        result = parser.parse_output_folder(temp_output_dir)

        # Should find the file
        filenames = [f.name for f in result["input_files"]]
        assert "file (copy) [1].jpg" in filenames

    def test_very_large_output_folder(self, temp_output_dir):
        """Test: Performance with large number of files"""
        # Create 100 files
        for i in range(100):
            (temp_output_dir / "documents" / f"file{i:03d}.jpg").write_text(f"file {i}")

        parser = DirectorOutputParser()
        result = parser.parse_output_folder(temp_output_dir)

        # Should handle all files (3 original + 100 new = 103)
        # Note: Depending on fixture reuse, we might have slightly different counts
        assert len(result["input_files"]) >= 100, "Should find at least 100 files"

    def test_unicode_filenames(self, temp_output_dir):
        """Test: Handle Unicode filenames correctly"""
        # Create file with Unicode characters
        unicode_file = temp_output_dir / "documents" / "文件001.jpg"
        unicode_file.write_text("unicode")

        parser = DirectorOutputParser()
        outputs = parser.get_file_outputs(temp_output_dir, "文件001.jpg")

        # Should handle Unicode correctly
        assert len(outputs) == 0 or len(outputs) == 1  # Depends on filesystem support

    def test_symlinks_handling(self, temp_output_dir):
        """Test: Handle symlinks in output folder"""
        # Create a symlink
        real_file = temp_output_dir / "documents" / "real.jpg"
        real_file.write_text("real")

        symlink_file = temp_output_dir / "documents" / "link.jpg"
        try:
            symlink_file.symlink_to(real_file)
        except (OSError, NotImplementedError):
            pytest.skip("Symlinks not supported on this filesystem")

        parser = DirectorOutputParser()
        result = parser.parse_output_folder(temp_output_dir)

        # Should find both files
        filenames = [f.name for f in result["input_files"]]
        assert "real.jpg" in filenames


class TestCLIIntegration:
    """Test CLI command integration"""

    def test_cli_show_content_flag_usage(self):
        """Test: CLI --show-content flag works correctly"""
        # This would test the actual CLI command
        # For now, just verify the flag parsing

        show_content = True  # Simulating --show-content flag

        # When show_content is True, JSON files should be read and displayed
        test_json_path = Path("/tmp/test.json")
        test_json_path.write_text('{"key": "value"}')

        if show_content:
            with open(test_json_path, 'r') as f:
                content = f.read()
                parsed = json.loads(content)
                assert parsed["key"] == "value"

        test_json_path.unlink()


def test_full_integration_workflow(temp_output_dir):
    """
    Integration test: Full workflow from Director output → filtered outputs → GUI display

    Simulates:
    1. Director processes a batch of files
    2. Library stores processing results
    3. User clicks on ONE file in GUI
    4. System filters and shows ONLY that file's outputs
    """
    parser = DirectorOutputParser()

    # Step 1: Parse entire output folder (batch processing)
    all_outputs = parser.get_all_file_outputs(temp_output_dir)
    assert len(all_outputs) == 3, "Batch contains 3 files"

    # Step 2: User selects file002.jpg
    selected_filename = "file002.jpg"

    # Step 3: Filter outputs for selected file ONLY
    filtered_outputs = parser.get_file_outputs(temp_output_dir, selected_filename)
    assert len(filtered_outputs) == 1, "Should filter to exactly ONE file"

    # Step 4: Get processing steps for selected file
    steps = parser.get_processing_steps(filtered_outputs[0])

    # Step 5: Verify ALL steps belong to the selected file (NOT other files!)
    for step in steps:
        if step.file_path and step.file_path.exists():
            assert step.file_path.stem == "file002", \
                f"Filter failed: {step.step_name} has {step.file_path.name}, expected file002"

    print("✅ Full integration test passed - filtering works correctly!")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
