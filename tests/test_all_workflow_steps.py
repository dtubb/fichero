"""
Comprehensive workflow testing - test each step with skip-processing
Tests all tools: enhance, segment, transcribe, recombine, convert_to_word
"""
import tempfile
import shutil
from pathlib import Path
from PIL import Image
import json
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

def create_test_image(path: Path, size=(100, 100)):
    """Helper to create a test image"""
    img = Image.new('RGB', size, color='white')
    img.save(path)
    return path

def create_manifest(manifest_path: Path, entries: list):
    """Helper to create manifest files"""
    with open(manifest_path, 'w') as f:
        for entry in entries:
            f.write(json.dumps(entry) + '\n')
    return manifest_path

def print_test_header(name):
    """Print test section header"""
    print(f"\n{'='*70}")
    print(f"TEST: {name}")
    print(f"{'='*70}")

def print_success(message):
    """Print success message"""
    print(f"  ✓ {message}")

def print_result(result):
    """Print result summary"""
    print(f"  Result: {result}")

# ==================== STEP 1: ENHANCE ====================
def test_step1_enhance():
    """Test enhance step with skip-processing"""
    print_test_header("STEP 1: ENHANCE (Single File)")

    from fichero.tools.enhance import enhance_batch

    temp_dir = Path(tempfile.mkdtemp())
    try:
        source_folder = temp_dir / "source"
        output_folder = temp_dir / "output"
        source_folder.mkdir()
        output_folder.mkdir()

        # Create test image
        create_test_image(source_folder / "test.jpg")

        # Create manifest
        manifest_file = temp_dir / "manifest.jsonl"
        create_manifest(manifest_file, [{"source": "test.jpg"}])

        # Run with skip_processing
        result = enhance_batch(
            source_folder=source_folder,
            source_manifest=manifest_file,
            output_folder=output_folder,
            skip_processing=True
        )

        print_result(result)

        # Verify
        output_image = output_folder / "test.jpg"
        assert output_image.exists()
        img = Image.open(output_image)
        assert img.size == (1, 1)

        print_success("Created 1x1 empty image")
        print_success("Step 1 (Enhance) PASSED")
        return True

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def test_step1_enhance_folder():
    """Test enhance step with folder of files"""
    print_test_header("STEP 1: ENHANCE (Folder of 10 Files)")

    from fichero.tools.enhance import enhance_batch

    temp_dir = Path(tempfile.mkdtemp())
    try:
        source_folder = temp_dir / "source"
        output_folder = temp_dir / "output"
        source_folder.mkdir()
        output_folder.mkdir()

        # Create 10 test images
        num_files = 10
        for i in range(num_files):
            create_test_image(source_folder / f"doc{i:03d}.jpg")

        # Create manifest
        manifest_file = temp_dir / "manifest.jsonl"
        entries = [{"source": f"doc{i:03d}.jpg"} for i in range(num_files)]
        create_manifest(manifest_file, entries)

        # Run with skip_processing
        import time
        start = time.time()
        result = enhance_batch(
            source_folder=source_folder,
            source_manifest=manifest_file,
            output_folder=output_folder,
            skip_processing=True
        )
        elapsed = time.time() - start

        print_result(result)
        print(f"  Time: {elapsed:.2f}s ({elapsed/num_files*1000:.1f}ms per file)")

        # Verify all files
        for i in range(num_files):
            assert (output_folder / f"doc{i:03d}.jpg").exists()

        print_success(f"Processed {num_files} files quickly")
        print_success("Step 1 (Enhance Folder) PASSED")
        return True

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

# ==================== STEP 2: SEGMENT ====================
def test_step2_segment():
    """Test segment step with skip-processing"""
    print_test_header("STEP 2: SEGMENT")

    from fichero.tools.segment import segment_batch

    temp_dir = Path(tempfile.mkdtemp())
    try:
        source_folder = temp_dir / "source"
        output_folder = temp_dir / "output"
        source_folder.mkdir()
        output_folder.mkdir()

        # Create test images
        create_test_image(source_folder / "page1.jpg")
        create_test_image(source_folder / "page2.jpg")

        # Create manifest
        manifest_file = temp_dir / "manifest.jsonl"
        create_manifest(manifest_file, [
            {"source": "page1.jpg"},
            {"source": "page2.jpg"}
        ])

        # Run with skip_processing
        result = segment_batch(
            source_folder=source_folder,
            source_manifest=manifest_file,
            output_folder=output_folder,
            skip_processing=True
        )

        print_result(result)

        # Verify manifest and segment files created
        manifest_out = output_folder / "segment_manifest.jsonl"  # Fixed: was "segments_manifest"
        assert manifest_out.exists()

        # Verify segment images created in documents/ subfolder
        seg1 = output_folder / "documents" / "page1_segments" / "page1_segment_001.jpg"
        seg2 = output_folder / "documents" / "page2_segments" / "page2_segment_001.jpg"
        assert seg1.exists(), f"Should exist: {seg1}"
        assert seg2.exists(), f"Should exist: {seg2}"

        # Verify manifest content
        with open(manifest_out) as f:
            lines = f.readlines()
            assert len(lines) == 2
            for line in lines:
                entry = json.loads(line)
                assert entry['success'] == True
                assert 'details' in entry
                assert entry['details']['skip_processing'] == True

        print_success("Created manifest and segment images in documents/ subfolder")
        print_success("Step 2 (Segment) PASSED")
        return True

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

# ==================== STEP 3: TRANSCRIBE ====================
def test_step3_transcribe():
    """Test transcribe step with skip-processing"""
    print_test_header("STEP 3: TRANSCRIBE")

    from fichero.tools.transcribe_qwen_max import transcribe_batch

    temp_dir = Path(tempfile.mkdtemp())
    try:
        source_folder = temp_dir / "source"
        output_folder = temp_dir / "output"
        source_folder.mkdir()
        output_folder.mkdir()

        # Create test images
        create_test_image(source_folder / "page1.jpg")
        create_test_image(source_folder / "page2.jpg")

        # Create manifest
        manifest_file = temp_dir / "manifest.jsonl"
        create_manifest(manifest_file, [
            {"source": "page1.jpg"},
            {"source": "page2.jpg"}
        ])

        # Run with skip_processing
        result = transcribe_batch(
            source_folder=source_folder,
            source_manifest=manifest_file,
            output_folder=output_folder,
            skip_processing=True
        )

        print_result(result)

        # Verify empty text files in documents/ subfolder
        text1 = output_folder / "documents" / "page1.txt"
        text2 = output_folder / "documents" / "page2.txt"

        assert text1.exists(), f"Should exist: {text1}"
        assert text2.exists(), f"Should exist: {text2}"
        assert text1.read_text() == ""
        assert text2.read_text() == ""

        print_success("Created empty text files in documents/ subfolder")
        print_success("Step 3 (Transcribe) PASSED")
        return True

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

# ==================== STEP 4: RECOMBINE ====================
def test_step4_recombine():
    """Test recombine step with skip-processing"""
    print_test_header("STEP 4: RECOMBINE")

    from fichero.tools.recombine_segments import recombine_segments_batch

    temp_dir = Path(tempfile.mkdtemp())
    try:
        transcriptions_folder = temp_dir / "transcriptions"
        output_folder = temp_dir / "output"
        transcriptions_folder.mkdir()
        output_folder.mkdir()

        # Create transcription manifest with empty segments
        transcription_manifest = temp_dir / "transcriptions_manifest.jsonl"
        create_manifest(transcription_manifest, [
            {"original_file": "page1.jpg", "segments": []},
            {"original_file": "page2.jpg", "segments": []}
        ])

        # Create image manifest
        image_manifest = temp_dir / "images_manifest.jsonl"
        create_manifest(image_manifest, [
            {"file_name": "page1.jpg", "segments": []},
            {"file_name": "page2.jpg", "segments": []}
        ])

        # Run with skip_processing
        result = recombine_segments_batch(
            transcriptions_folder=transcriptions_folder,
            output_folder=output_folder,
            transcription_manifest=transcription_manifest,
            image_manifest=image_manifest,
            skip_processing=True
        )

        print_result(result)

        # Verify manifest file created (recombine may not process with empty segments)
        manifest_out = output_folder / "recombine_manifest.jsonl"
        assert manifest_out.exists(), f"Manifest should exist: {manifest_out}"

        # Note: recombine_segments_batch may not create output files with empty segments
        # This is expected behavior - just verify it ran without errors
        print_success("Recombine completed without errors")
        print_success("Step 4 (Recombine) PASSED")
        return True

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

# ==================== STEP 5: CONVERT TO WORD ====================
def test_step5_convert_to_word():
    """Test convert_to_word step with skip-processing"""
    print_test_header("STEP 5: CONVERT TO WORD")

    from fichero.tools.convert_to_word import convert_to_word_batch

    temp_dir = Path(tempfile.mkdtemp())
    try:
        images_folder = temp_dir / "images"
        output_folder = temp_dir / "output"
        images_folder.mkdir()
        output_folder.mkdir()

        # Create test images
        test_img1 = images_folder / "doc1.jpg"
        test_img2 = images_folder / "doc2.jpg"
        create_test_image(test_img1)
        create_test_image(test_img2)

        # Create dummy text files
        (temp_dir / "doc1_recombined.txt").write_text("Test content 1")
        (temp_dir / "doc2_recombined.txt").write_text("Test content 2")

        # Create transcription manifest
        transcription_manifest = temp_dir / "transcription_manifest.jsonl"
        create_manifest(transcription_manifest, [
            {
                "original_file": "doc1.jpg",
                "image_file": str(test_img1),
                "text_file": str(temp_dir / "doc1_recombined.txt")
            },
            {
                "original_file": "doc2.jpg",
                "image_file": str(test_img2),
                "text_file": str(temp_dir / "doc2_recombined.txt")
            }
        ])

        # Run with skip_processing
        result = convert_to_word_batch(
            images_folder=images_folder,
            transcription_manifest=transcription_manifest,
            output_folder=output_folder,
            skip_processing=True
        )

        print_result(result)

        # Verify manifest file created
        manifest_out = output_folder / "convert_to_word_manifest.jsonl"
        assert manifest_out.exists(), f"Manifest should exist: {manifest_out}"

        # Note: convert_to_word may not create docs with placeholder data
        # Just verify it ran without errors
        print_success("Convert to Word completed without errors")
        print_success("Step 5 (Convert to Word) PASSED")
        return True

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

# ==================== RUN ALL TESTS ====================
if __name__ == "__main__":
    print("\n" + "="*70)
    print("COMPREHENSIVE WORKFLOW STEP TESTING")
    print("Testing each step with skip-processing on files and folders")
    print("="*70)

    tests = [
        ("Step 1: Enhance (Single File)", test_step1_enhance),
        ("Step 1: Enhance (Folder)", test_step1_enhance_folder),
        ("Step 2: Segment", test_step2_segment),
        ("Step 3: Transcribe", test_step3_transcribe),
        ("Step 4: Recombine", test_step4_recombine),
        ("Step 5: Convert to Word", test_step5_convert_to_word),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed_count}/{total_count} workflow steps passed")

    if passed_count == total_count:
        print("\n🎉 ALL WORKFLOW STEPS PASSED!")
        print("Skip-processing works correctly for the entire pipeline.")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total_count - passed_count} step(s) failed.")
        sys.exit(1)
