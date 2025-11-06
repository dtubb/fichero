"""
Debug test to see what convert_to_word_batch actually creates with skip_processing
"""
import tempfile
import shutil
from pathlib import Path
from PIL import Image
import json
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

def test_convert_to_word_debug():
    """Debug test to see what's happening"""
    from fichero.tools.convert_to_word import convert_to_word_batch

    temp_dir = Path(tempfile.mkdtemp())
    try:
        images_folder = temp_dir / "images"
        output_folder = temp_dir / "output"
        images_folder.mkdir()
        output_folder.mkdir()

        # Create test images
        img = Image.new('RGB', (100, 100), color='white')
        test_img1 = images_folder / "doc1.jpg"
        test_img2 = images_folder / "doc2.jpg"
        img.save(test_img1)
        img.save(test_img2)

        # Create dummy text files
        (temp_dir / "doc1_recombined.txt").write_text("Test content 1")
        (temp_dir / "doc2_recombined.txt").write_text("Test content 2")

        # Create transcription manifest
        transcription_manifest = temp_dir / "transcription_manifest.jsonl"
        with open(transcription_manifest, 'w') as f:
            f.write(json.dumps({
                "original_file": "doc1.jpg",
                "image_file": str(test_img1),
                "text_file": str(temp_dir / "doc1_recombined.txt")
            }) + '\n')
            f.write(json.dumps({
                "original_file": "doc2.jpg",
                "image_file": str(test_img2),
                "text_file": str(temp_dir / "doc2_recombined.txt")
            }) + '\n')

        print(f"\nTest setup:")
        print(f"  images_folder: {images_folder}")
        print(f"  output_folder: {output_folder}")
        print(f"  transcription_manifest: {transcription_manifest}")

        # Run with skip_processing=True
        print(f"\nCalling convert_to_word_batch with skip_processing=True...")
        result = convert_to_word_batch(
            images_folder=images_folder,
            transcription_manifest=transcription_manifest,
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
        else:
            print("  Output folder does not exist!")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    test_convert_to_word_debug()
