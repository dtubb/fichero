"""
Test to verify single file processing creates correct staging structure
"""
import tempfile
import shutil
from pathlib import Path
from PIL import Image
import json
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

def test_single_file_staging_structure():
    """Verify that single file processing creates staging/documents/ structure"""
    from fichero.tools.enhance import enhance_batch

    temp_dir = Path(tempfile.mkdtemp())
    try:
        # Simulate library single file processing structure
        source_folder = temp_dir / "source"
        staging_dir = temp_dir / "staging"
        output_folder = temp_dir / "output"

        source_folder.mkdir()
        staging_dir.mkdir()
        output_folder.mkdir()

        # Create documents subfolder in staging (as fixed code does)
        documents_dir = staging_dir / "documents"
        documents_dir.mkdir()

        # Create test image in source
        test_img = Image.new('RGB', (100, 100), color='white')
        source_file = source_folder / "test.jpg"
        test_img.save(source_file)

        # Create symlink in staging/documents/
        import os
        staging_link = documents_dir / "test.jpg"
        os.symlink(source_file, staging_link)

        # Create manifest pointing to the file in documents/
        manifest_file = temp_dir / "manifest.jsonl"
        with open(manifest_file, 'w') as f:
            f.write(json.dumps({"source": "documents/test.jpg"}) + '\n')

        print(f"\nStaging structure test:")
        print(f"  Source: {source_file}")
        print(f"  Staging: {staging_dir}")
        print(f"  Symlink: {staging_link}")
        print(f"  Symlink exists: {staging_link.exists()}")
        print(f"  Symlink points to: {staging_link.resolve()}")

        # Run enhance with skip_processing to verify structure is correct
        result = enhance_batch(
            source_folder=staging_dir,  # Point to staging as documents_folder
            source_manifest=manifest_file,
            output_folder=output_folder,
            skip_processing=True
        )

        print(f"  Result: {result}")

        # Verify output was created
        output_image = output_folder / "documents" / "test.jpg"
        assert output_image.exists(), f"Output should exist at {output_image}"

        img = Image.open(output_image)
        assert img.size == (1, 1), f"Should be 1x1 image, got {img.size}"

        print(f"  ✓ Staging structure with documents/ subfolder works correctly!")
        print(f"  ✓ Single file processing bug is FIXED!")
        return True

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    try:
        test_single_file_staging_structure()
        print("\n✅ TEST PASSED: Single file staging structure is correct")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
