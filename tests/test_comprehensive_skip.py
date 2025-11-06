"""
Comprehensive skip-processing tests for various file and folder scenarios
Tests single files, multiple files, folders, and different tools
"""
import tempfile
import shutil
from pathlib import Path
from PIL import Image
import json
import sys

# Add src to path
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

def test_scenario(name: str, test_func):
    """Run a test scenario and report results"""
    print(f"\n{'='*70}")
    print(f"TEST: {name}")
    print(f"{'='*70}")
    try:
        test_func()
        print(f"✅ PASSED: {name}")
        return True
    except AssertionError as e:
        print(f"❌ FAILED: {name}")
        print(f"   Error: {e}")
        return False
    except Exception as e:
        print(f"❌ ERROR: {name}")
        print(f"   Exception: {e}")
        return False

# ==================== TEST 1: Single File - Enhance ====================
def test_single_file_enhance():
    """Test enhance with single file and skip-processing"""
    from fichero.tools.enhance import enhance_batch

    temp_dir = Path(tempfile.mkdtemp())
    try:
        source_folder = temp_dir / "source"
        output_folder = temp_dir / "output"
        source_folder.mkdir()
        output_folder.mkdir()

        # Create single test image
        test_image = source_folder / "single.jpg"
        create_test_image(test_image)

        # Create manifest
        manifest_file = temp_dir / "manifest.jsonl"
        create_manifest(manifest_file, [{"source": "single.jpg"}])

        print(f"  Input: 1 image file")
        print(f"  Source: {source_folder}")

        # Run with skip_processing=True
        result = enhance_batch(
            source_folder=source_folder,
            source_manifest=manifest_file,
            output_folder=output_folder,
            skip_processing=True
        )

        print(f"  Result: {result}")

        # Verify
        output_image = output_folder / "single.jpg"
        assert output_image.exists(), "Output image should exist"

        img = Image.open(output_image)
        assert img.size == (1, 1), f"Should be 1x1 image, got {img.size}"
        assert result['success'] == 1, f"Should have 1 success, got {result}"

        print(f"  ✓ Created 1x1 empty image")
        print(f"  ✓ Manifest created")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

# ==================== TEST 2: Multiple Files - Enhance ====================
def test_multiple_files_enhance():
    """Test enhance with multiple files and skip-processing"""
    from fichero.tools.enhance import enhance_batch

    temp_dir = Path(tempfile.mkdtemp())
    try:
        source_folder = temp_dir / "source"
        output_folder = temp_dir / "output"
        source_folder.mkdir()
        output_folder.mkdir()

        # Create 5 test images
        num_files = 5
        for i in range(num_files):
            create_test_image(source_folder / f"file{i}.jpg")

        # Create manifest
        manifest_file = temp_dir / "manifest.jsonl"
        entries = [{"source": f"file{i}.jpg"} for i in range(num_files)]
        create_manifest(manifest_file, entries)

        print(f"  Input: {num_files} image files")

        # Run with skip_processing=True
        result = enhance_batch(
            source_folder=source_folder,
            source_manifest=manifest_file,
            output_folder=output_folder,
            skip_processing=True
        )

        print(f"  Result: {result}")

        # Verify all outputs
        for i in range(num_files):
            output_image = output_folder / f"file{i}.jpg"
            assert output_image.exists(), f"Output image {i} should exist"
            img = Image.open(output_image)
            assert img.size == (1, 1), f"Image {i} should be 1x1"

        assert result['success'] == num_files, f"Should have {num_files} successes"

        print(f"  ✓ Created {num_files} 1x1 empty images")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

# ==================== TEST 3: Folder with Subfolders ====================
def test_folder_structure():
    """Test with nested folder structure"""
    from fichero.tools.enhance import enhance_batch

    temp_dir = Path(tempfile.mkdtemp())
    try:
        source_folder = temp_dir / "source"
        output_folder = temp_dir / "output"
        source_folder.mkdir()
        output_folder.mkdir()

        # Create nested structure
        (source_folder / "subfolder1").mkdir()
        (source_folder / "subfolder2").mkdir()

        create_test_image(source_folder / "root.jpg")
        create_test_image(source_folder / "subfolder1" / "sub1.jpg")
        create_test_image(source_folder / "subfolder2" / "sub2.jpg")

        # Create manifest for all files
        manifest_file = temp_dir / "manifest.jsonl"
        entries = [
            {"source": "root.jpg"},
            {"source": "subfolder1/sub1.jpg"},
            {"source": "subfolder2/sub2.jpg"}
        ]
        create_manifest(manifest_file, entries)

        print(f"  Input: 3 images in nested folders")

        # Run with skip_processing=True
        result = enhance_batch(
            source_folder=source_folder,
            source_manifest=manifest_file,
            output_folder=output_folder,
            skip_processing=True
        )

        print(f"  Result: {result}")

        # Verify
        assert (output_folder / "root.jpg").exists()
        assert (output_folder / "subfolder1" / "sub1.jpg").exists()
        assert (output_folder / "subfolder2" / "sub2.jpg").exists()
        assert result['success'] == 3

        print(f"  ✓ Processed nested folder structure correctly")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

# ==================== TEST 4: Transcribe Tool ====================
def test_transcribe_skip():
    """Test transcribe with skip-processing"""
    from fichero.tools.transcribe_qwen_max import transcribe_batch

    temp_dir = Path(tempfile.mkdtemp())
    try:
        source_folder = temp_dir / "source"
        output_folder = temp_dir / "output"
        source_folder.mkdir()
        output_folder.mkdir()

        # Create test images
        create_test_image(source_folder / "doc1.jpg")
        create_test_image(source_folder / "doc2.jpg")

        # Create manifest (transcribe uses 'source' field)
        manifest_file = temp_dir / "manifest.jsonl"
        entries = [
            {"source": "doc1.jpg"},
            {"source": "doc2.jpg"}
        ]
        create_manifest(manifest_file, entries)

        print(f"  Input: 2 images to transcribe")

        # Run with skip_processing=True
        result = transcribe_batch(
            source_folder=source_folder,
            source_manifest=manifest_file,
            output_folder=output_folder,
            skip_processing=True
        )

        print(f"  Result: {result}")

        # Verify empty text files created in documents/ subfolder
        text1 = output_folder / "documents" / "doc1.txt"
        text2 = output_folder / "documents" / "doc2.txt"

        assert text1.exists(), f"Text file 1 should exist: {text1}"
        assert text2.exists(), f"Text file 2 should exist: {text2}"
        assert text1.read_text() == "", "Text file 1 should be empty"
        assert text2.read_text() == "", "Text file 2 should be empty"
        assert result['processed'] == 2

        print(f"  ✓ Created 2 empty text files in documents/ subfolder")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

# ==================== TEST 5: Large Batch ====================
def test_large_batch():
    """Test with a larger number of files"""
    from fichero.tools.enhance import enhance_batch

    temp_dir = Path(tempfile.mkdtemp())
    try:
        source_folder = temp_dir / "source"
        output_folder = temp_dir / "output"
        source_folder.mkdir()
        output_folder.mkdir()

        # Create 20 test images
        num_files = 20
        for i in range(num_files):
            create_test_image(source_folder / f"batch{i:03d}.jpg")

        # Create manifest
        manifest_file = temp_dir / "manifest.jsonl"
        entries = [{"source": f"batch{i:03d}.jpg"} for i in range(num_files)]
        create_manifest(manifest_file, entries)

        print(f"  Input: {num_files} image files")

        import time
        start = time.time()

        # Run with skip_processing=True
        result = enhance_batch(
            source_folder=source_folder,
            source_manifest=manifest_file,
            output_folder=output_folder,
            skip_processing=True
        )

        elapsed = time.time() - start

        print(f"  Result: {result}")
        print(f"  Time: {elapsed:.2f}s ({elapsed/num_files*1000:.1f}ms per file)")

        # Verify
        assert result['success'] == num_files
        for i in range(num_files):
            assert (output_folder / f"batch{i:03d}.jpg").exists()

        print(f"  ✓ Processed {num_files} files quickly")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

# ==================== RUN ALL TESTS ====================
if __name__ == "__main__":
    print("\n" + "="*70)
    print("COMPREHENSIVE SKIP-PROCESSING TESTS")
    print("Testing various file and folder scenarios")
    print("="*70)

    tests = [
        ("Single File - Enhance", test_single_file_enhance),
        ("Multiple Files (5) - Enhance", test_multiple_files_enhance),
        ("Nested Folder Structure", test_folder_structure),
        ("Transcribe Tool - 2 Files", test_transcribe_skip),
        ("Large Batch (20 Files)", test_large_batch),
    ]

    results = []
    for name, test_func in tests:
        passed = test_scenario(name, test_func)
        results.append((name, passed))

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed_count}/{total_count} tests passed")

    if passed_count == total_count:
        print("\n🎉 ALL TESTS PASSED! Skip-processing works correctly.")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total_count - passed_count} test(s) failed.")
        sys.exit(1)
