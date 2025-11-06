"""
Comprehensive integration tests for skip_processing functionality
"""
import pytest
import tempfile
import shutil
from pathlib import Path
from PIL import Image
import json

# Test fixtures
@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing"""
    temp = tempfile.mkdtemp()
    yield Path(temp)
    shutil.rmtree(temp, ignore_errors=True)

@pytest.fixture
def sample_image():
    """Create a sample test image"""
    def _create_image(path: Path, size=(100, 100)):
        img = Image.new('RGB', size, color='white')
        img.save(path)
        return path
    return _create_image

@pytest.fixture
def create_manifest():
    """Helper to create manifest files"""
    def _create_manifest(manifest_path: Path, entries: list):
        with open(manifest_path, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + '\n')
        return manifest_path
    return _create_manifest

# Test 1: Test enhance tool with skip_processing
def test_enhance_skip_processing(temp_dir, sample_image, create_manifest):
    """Test that enhance creates empty images in skip mode"""
    from fichero.tools.enhance import enhance_batch

    # Create test input
    source_folder = temp_dir / "source"
    output_folder = temp_dir / "output"
    source_folder.mkdir()
    output_folder.mkdir()

    # Create test image
    test_image = source_folder / "test.jpg"
    sample_image(test_image)

    # Create manifest
    manifest_file = temp_dir / "manifest.jsonl"
    create_manifest(manifest_file, [
        {"file_name": "test.jpg", "file_path": str(test_image)}
    ])

    # Run with skip_processing=True
    result = enhance_batch(
        source_folder=source_folder,
        source_manifest=manifest_file,
        output_folder=output_folder,
        skip_processing=True
    )

    # Verify empty image was created
    output_image = output_folder / "test.jpg"
    assert output_image.exists(), "Output image should exist"

    # Check it's a 1x1 white image
    img = Image.open(output_image)
    assert img.size == (1, 1), "Should be 1x1 image in skip mode"
    assert result['success'] is True
    print("✓ Test enhance_skip_processing PASSED")

# Test 2: Test transcribe tool with skip_processing
def test_transcribe_skip_processing(temp_dir, sample_image, create_manifest):
    """Test that transcribe creates empty text files in skip mode"""
    from fichero.tools.transcribe_qwen_max import transcribe_batch

    # Create test input
    source_folder = temp_dir / "source"
    output_folder = temp_dir / "output"
    source_folder.mkdir()
    output_folder.mkdir()

    # Create test image
    test_image = source_folder / "test.jpg"
    sample_image(test_image)

    # Create manifest
    manifest_file = temp_dir / "manifest.jsonl"
    create_manifest(manifest_file, [
        {"file_name": "test.jpg", "file_path": str(test_image)}
    ])

    # Run with skip_processing=True
    result = transcribe_batch(
        source_folder=source_folder,
        source_manifest=manifest_file,
        output_folder=output_folder,
        skip_processing=True
    )

    # Verify empty text file was created
    output_text = output_folder / "test.txt"
    assert output_text.exists(), "Output text file should exist"

    # Check it's empty
    content = output_text.read_text()
    assert content == "", "Text file should be empty in skip mode"
    assert result['success'] is True
    print("✓ Test transcribe_skip_processing PASSED")

# Test 3: Test segment tool with skip_processing
def test_segment_skip_processing(temp_dir, sample_image, create_manifest):
    """Test that segment creates empty segment files in skip mode"""
    from fichero.tools.segment import segment_batch

    # Create test input
    source_folder = temp_dir / "source"
    output_folder = temp_dir / "output"
    source_folder.mkdir()
    output_folder.mkdir()

    # Create test image
    test_image = source_folder / "test.jpg"
    sample_image(test_image)

    # Create manifest
    manifest_file = temp_dir / "manifest.jsonl"
    create_manifest(manifest_file, [
        {"file_name": "test.jpg", "file_path": str(test_image)}
    ])

    # Run with skip_processing=True
    result = segment_batch(
        source_folder=source_folder,
        source_manifest=manifest_file,
        output_folder=output_folder,
        skip_processing=True
    )

    # Verify manifest was created with empty segment
    output_manifest = output_folder / "segments_manifest.jsonl"
    assert output_manifest.exists(), "Manifest should exist"

    # Check manifest content
    with open(output_manifest) as f:
        lines = f.readlines()
        assert len(lines) == 1, "Should have one entry in skip mode"
        entry = json.loads(lines[0])
        assert entry['segments'] == [], "Should have empty segments"

    assert result['success'] is True
    print("✓ Test segment_skip_processing PASSED")

# Test 4: Test recombine tool with skip_processing
def test_recombine_skip_processing(temp_dir, create_manifest):
    """Test that recombine creates empty recombined files in skip mode"""
    from fichero.tools.recombine_segments import recombine_segments_batch

    # Create test input
    transcriptions_folder = temp_dir / "transcriptions"
    output_folder = temp_dir / "output"
    transcriptions_folder.mkdir()
    output_folder.mkdir()

    # Create transcription manifest
    transcription_manifest = temp_dir / "transcriptions_manifest.jsonl"
    create_manifest(transcription_manifest, [
        {"original_file": "test.jpg", "segments": []}
    ])

    # Create image manifest
    image_manifest = temp_dir / "images_manifest.jsonl"
    create_manifest(image_manifest, [
        {"file_name": "test.jpg", "segments": []}
    ])

    # Run with skip_processing=True
    result = recombine_segments_batch(
        transcriptions_folder=transcriptions_folder,
        output_folder=output_folder,
        transcription_manifest=transcription_manifest,
        image_manifest=image_manifest,
        skip_processing=True
    )

    # Verify empty recombined file was created
    output_text = output_folder / "test_recombined.txt"
    assert output_text.exists(), "Recombined text file should exist"

    # Check it's empty
    content = output_text.read_text()
    assert content == "", "Recombined file should be empty in skip mode"
    assert result['success'] is True
    print("✓ Test recombine_skip_processing PASSED")

# Test 5: Test convert_to_word tool with skip_processing
def test_convert_to_word_skip_processing(temp_dir, sample_image, create_manifest):
    """Test that convert_to_word creates empty Word docs in skip mode"""
    from fichero.tools.convert_to_word import convert_to_word_batch

    # Create test input
    images_folder = temp_dir / "images"
    output_folder = temp_dir / "output"
    images_folder.mkdir()
    output_folder.mkdir()

    # Create test image
    test_image = images_folder / "test.jpg"
    sample_image(test_image)

    # Create transcription manifest
    transcription_manifest = temp_dir / "transcription_manifest.jsonl"
    create_manifest(transcription_manifest, [
        {
            "original_file": "test.jpg",
            "image_file": str(test_image),
            "text_file": str(temp_dir / "test_recombined.txt")
        }
    ])

    # Create dummy text file
    (temp_dir / "test_recombined.txt").write_text("Test content")

    # Run with skip_processing=True
    result = convert_to_word_batch(
        images_folder=images_folder,
        transcription_manifest=transcription_manifest,
        output_folder=output_folder,
        skip_processing=True
    )

    # Verify empty Word doc was created
    output_doc = output_folder / "test.docx"
    assert output_doc.exists(), "Word document should exist"
    assert result['success'] is True
    print("✓ Test convert_to_word_skip_processing PASSED")

if __name__ == "__main__":
    print("Running skip_processing integration tests...")
    print("=" * 60)
    pytest.main([__file__, "-v", "-s"])
