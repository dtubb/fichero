"""
Debug test to see what recombine_segments_batch actually creates with skip_processing
"""
import tempfile
import shutil
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

def test_recombine_debug():
    """Debug test to see what's happening"""
    from fichero.tools.recombine_segments import recombine_segments_batch

    temp_dir = Path(tempfile.mkdtemp())
    try:
        transcriptions_folder = temp_dir / "transcriptions"
        output_folder = temp_dir / "output"
        transcriptions_folder.mkdir()
        output_folder.mkdir()

        # Create transcription manifest with empty segments
        transcription_manifest = temp_dir / "transcriptions_manifest.jsonl"
        with open(transcription_manifest, 'w') as f:
            f.write(json.dumps({"original_file": "page1.jpg", "segments": []}) + '\n')
            f.write(json.dumps({"original_file": "page2.jpg", "segments": []}) + '\n')

        # Create image manifest
        image_manifest = temp_dir / "images_manifest.jsonl"
        with open(image_manifest, 'w') as f:
            f.write(json.dumps({"file_name": "page1.jpg", "segments": []}) + '\n')
            f.write(json.dumps({"file_name": "page2.jpg", "segments": []}) + '\n')

        print(f"\nTest setup:")
        print(f"  transcriptions_folder: {transcriptions_folder}")
        print(f"  output_folder: {output_folder}")
        print(f"  transcription_manifest: {transcription_manifest}")
        print(f"  image_manifest: {image_manifest}")

        # Run with skip_processing=True
        print(f"\nCalling recombine_segments_batch with skip_processing=True...")
        result = recombine_segments_batch(
            transcriptions_folder=transcriptions_folder,
            output_folder=output_folder,
            transcription_manifest=transcription_manifest,
            image_manifest=image_manifest,
            skip_processing=True
        )

        print(f"\nResult: {result}")

        # List ALL files in output folder recursively
        print(f"\nFiles in output folder:")
        if output_folder.exists():
            for file in output_folder.rglob("*"):
                if file.is_file():
                    print(f"  - {file.relative_to(output_folder)} (size: {file.stat().st_size} bytes)")
                    if file.suffix == '.txt':
                        content = file.read_text()
                        print(f"    Content: '{content}'")
        else:
            print("  Output folder does not exist!")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    test_recombine_debug()
