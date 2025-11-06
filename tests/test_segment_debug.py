"""
Debug test to see what segment_batch actually creates with skip_processing
"""
import tempfile
import shutil
from pathlib import Path
from PIL import Image
import json
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

def test_segment_debug():
    """Debug test to see what's happening"""
    from fichero.tools.segment import segment_batch

    temp_dir = Path(tempfile.mkdtemp())
    try:
        source_folder = temp_dir / "source"
        output_folder = temp_dir / "output"
        source_folder.mkdir()
        output_folder.mkdir()

        # Create test images
        img = Image.new('RGB', (100, 100), color='white')
        img.save(source_folder / "page1.jpg")
        img.save(source_folder / "page2.jpg")

        # Create manifest
        manifest_file = temp_dir / "manifest.jsonl"
        with open(manifest_file, 'w') as f:
            f.write(json.dumps({"source": "page1.jpg"}) + '\n')
            f.write(json.dumps({"source": "page2.jpg"}) + '\n')

        print(f"\nTest setup:")
        print(f"  source_folder: {source_folder}")
        print(f"  output_folder: {output_folder}")
        print(f"  manifest_file: {manifest_file}")

        # Run with skip_processing=True
        print(f"\nCalling segment_batch with skip_processing=True...")
        result = segment_batch(
            source_folder=source_folder,
            source_manifest=manifest_file,
            output_folder=output_folder,
            skip_processing=True
        )

        print(f"\nResult: {result}")

        # List ALL files in output folder recursively
        print(f"\nFiles in output folder:")
        if output_folder.exists():
            for file in output_folder.rglob("*"):
                if file.is_file():
                    print(f"  - {file.relative_to(output_folder)} (size: {file.stat().st_size} bytes)")
                    if file.suffix == '.jsonl':
                        print(f"    Content:")
                        with open(file) as f:
                            for line in f:
                                print(f"      {line.strip()}")
        else:
            print("  Output folder does not exist!")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    test_segment_debug()
