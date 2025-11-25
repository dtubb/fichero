#!/usr/bin/env python3
"""
Quick test script for the unified transcribe tool with DashScope Qwen OCR.

Usage:
    python test_transcribe_quick.py /path/to/images/folder

This will:
1. Create a manifest of images in the folder
2. Run transcription using DashScope Qwen OCR
3. Show results and statistics
"""

import sys
import os
from pathlib import Path
import json
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero.tools.build_documents_manifest import build_documents_manifest_batch
from fichero.tools.transcribe import transcribe_batch


def create_test_manifest(image_folder: Path) -> Path:
    """Create a simple manifest file for the images"""
    manifest_path = image_folder / "test_manifest.jsonl"

    print(f"📝 Creating manifest for images in: {image_folder}")

    # Find all image files
    image_extensions = ['.jpg', '.jpeg', '.png', '.tiff', '.tif']
    images = []
    for ext in image_extensions:
        images.extend(image_folder.glob(f"*{ext}"))
        images.extend(image_folder.glob(f"*{ext.upper()}"))

    # Write manifest
    with open(manifest_path, 'w') as f:
        for img in sorted(images):
            entry = {
                "source": img.name,
                "outputs": [img.name],
                "type": "file"
            }
            f.write(json.dumps(entry) + '\n')

    print(f"✅ Created manifest with {len(images)} images")
    return manifest_path


def test_transcribe_dashscope_ocr(image_folder: str):
    """Test transcribe tool with DashScope Qwen OCR provider"""

    print("=" * 70)
    print("🧪 Testing Unified Transcribe Tool - DashScope Qwen OCR")
    print("=" * 70)

    # Convert to Path
    image_folder = Path(image_folder).resolve()

    if not image_folder.exists():
        print(f"❌ Error: Folder does not exist: {image_folder}")
        return 1

    if not image_folder.is_dir():
        print(f"❌ Error: Not a directory: {image_folder}")
        return 1

    # Check for API key
    api_key = os.environ.get('DASHSCOPE_API_KEY')
    if not api_key:
        print("❌ Error: DASHSCOPE_API_KEY environment variable not set")
        print("   Set it with: export DASHSCOPE_API_KEY=your-key-here")
        return 1

    print(f"\n📂 Image folder: {image_folder}")
    print(f"🔑 API key: {api_key[:8]}..." if api_key else "None")

    # Create manifest
    try:
        manifest_path = create_test_manifest(image_folder)
    except Exception as e:
        print(f"❌ Error creating manifest: {e}")
        return 1

    # Create output folder
    output_folder = image_folder / "transcriptions_test"
    output_folder.mkdir(exist_ok=True)

    print(f"\n💾 Output folder: {output_folder}")
    print("\n" + "=" * 70)
    print("🚀 Starting Transcription")
    print("=" * 70)
    print(f"Provider: dashscope")
    print(f"Model: qwen-vl-ocr")
    print(f"Workers: 5 (parallel)")
    print("=" * 70 + "\n")

    # Run transcription
    start_time = datetime.now()

    try:
        stats = transcribe_batch(
            source_folder=image_folder,
            source_manifest=manifest_path,
            output_folder=output_folder,
            provider="dashscope",
            model="qwen-vl-ocr",
            api_key_cli=api_key,
            max_workers=5,
            testing=False
        )

        end_time = datetime.now()
        elapsed = (end_time - start_time).total_seconds()

        # Show results
        print("\n" + "=" * 70)
        print("✅ Transcription Complete!")
        print("=" * 70)
        print(f"\n📊 Statistics:")
        print(f"   Total images:  {stats.get('total', 0)}")
        print(f"   ✅ Processed:  {stats.get('processed', 0)}")
        print(f"   ⏭️  Skipped:    {stats.get('skipped', 0)}")
        print(f"   ❌ Failed:     {stats.get('failed', 0)}")
        print(f"\n⏱️  Time:")
        print(f"   Total time: {elapsed:.2f}s")
        if stats.get('processed', 0) > 0:
            avg_time = elapsed / stats['processed']
            print(f"   Avg per image: {avg_time:.2f}s")

        # Show output files
        print(f"\n📁 Output Files:")
        output_manifest = output_folder / "transcriptions_manifest.jsonl"
        if output_manifest.exists():
            print(f"   Manifest: {output_manifest}")

            # Count transcription files
            txt_files = list(output_folder.glob("documents/**/*.txt"))
            print(f"   Transcriptions: {len(txt_files)} .txt files")

            # Show first few transcriptions
            print(f"\n📄 Sample Transcriptions:")
            for i, txt_file in enumerate(txt_files[:3], 1):
                with open(txt_file, 'r') as f:
                    content = f.read().strip()
                    preview = content[:100] + "..." if len(content) > 100 else content
                    print(f"\n   {i}. {txt_file.name}")
                    print(f"      {preview}")

        print("\n" + "=" * 70)
        print("🎉 Test Complete!")
        print("=" * 70)

        # Cleanup manifest
        if manifest_path.exists():
            manifest_path.unlink()
            print(f"\n🧹 Cleaned up test manifest")

        return 0

    except Exception as e:
        print(f"\n❌ Error during transcription: {e}")
        import traceback
        traceback.print_exc()
        return 1


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: python test_transcribe_quick.py /path/to/images/folder")
        print("\nThis will test the unified transcribe tool with:")
        print("  - Provider: dashscope")
        print("  - Model: qwen-vl-ocr")
        print("  - Parallel workers: 5")
        print("\nMake sure DASHSCOPE_API_KEY is set in your environment.")
        return 1

    image_folder = sys.argv[1]
    return test_transcribe_dashscope_ocr(image_folder)


if __name__ == "__main__":
    sys.exit(main())
