"""
Debug test to see what enhance_batch actually does with skip_processing
"""
import tempfile
import shutil
from pathlib import Path
from PIL import Image
import json

def test_enhance_debug():
    """Debug test to see what's happening"""
    from fichero.tools.enhance import enhance_batch

    temp_dir = Path(tempfile.mkdtemp())
    try:
        # Create test input
        source_folder = temp_dir / "source"
        output_folder = temp_dir / "output"
        source_folder.mkdir()
        output_folder.mkdir()

        # Create test image
        test_image = source_folder / "test.jpg"
        img = Image.new('RGB', (100, 100), color='white')
        img.save(test_image)

        # Create manifest (use "source" field as expected by enhance_batch)
        manifest_file = temp_dir / "manifest.jsonl"
        with open(manifest_file, 'w') as f:
            f.write(json.dumps({"source": "test.jpg"}) + '\n')

        print(f"\nTest setup:")
        print(f"  source_folder: {source_folder}")
        print(f"  output_folder: {output_folder}")
        print(f"  manifest_file: {manifest_file}")
        print(f"  test_image exists: {test_image.exists()}")
        print(f"  manifest exists: {manifest_file.exists()}")

        # Run with skip_processing=True
        print(f"\nCalling enhance_batch with skip_processing=True...")
        result = enhance_batch(
            source_folder=source_folder,
            source_manifest=manifest_file,
            output_folder=output_folder,
            skip_processing=True
        )

        print(f"\nResult: {result}")

        # List all files created
        print(f"\nFiles in output folder:")
        if output_folder.exists():
            for file in output_folder.iterdir():
                print(f"  - {file.name} (size: {file.stat().st_size} bytes)")
                if file.suffix in ['.jpg', '.png']:
                    try:
                        img = Image.open(file)
                        print(f"    Image size: {img.size}")
                    except Exception as e:
                        print(f"    Could not open as image: {e}")
        else:
            print("  Output folder does not exist!")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    test_enhance_debug()
