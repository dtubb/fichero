#!/usr/bin/env python3
"""
Standalone test script for transcribe tool.
Doesn't require full Fichero app initialization.

Usage:
    DASHSCOPE_API_KEY=your-key python3 test_transcribe_standalone.py INPUT_FOLDER OUTPUT_FOLDER
"""

import sys
import os
from pathlib import Path
import json
from datetime import datetime
import time

# Just check for dependencies
try:
    from openai import OpenAI
    from PIL import Image
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Install with: pip install openai pillow python-dotenv")
    sys.exit(1)


def create_simple_manifest(image_folder: Path) -> Path:
    """Create a simple manifest file"""
    manifest_path = image_folder / "test_manifest.jsonl"

    print(f"📝 Creating manifest...")

    # Find images
    extensions = ['.jpg', '.jpeg', '.png', '.tiff', '.tif']
    images = []
    for ext in extensions:
        images.extend(image_folder.glob(f"*{ext}"))
        images.extend(image_folder.glob(f"*{ext.upper()}"))

    # Write manifest
    with open(manifest_path, 'w') as f:
        for img in sorted(images):
            f.write(json.dumps({
                "source": img.name,
                "outputs": [img.name],
                "type": "file"
            }) + '\n')

    print(f"   Found {len(images)} images")
    return manifest_path


def process_image_simple(image_path: Path, output_path: Path, client: OpenAI, model: str) -> dict:
    """Process a single image with DashScope"""
    import base64

    # Skip if exists
    output_txt = output_path.with_suffix('.txt')
    if output_txt.exists():
        print(f"   ⏭️  Skipped: {image_path.name}")
        return {"skipped": True, "source": image_path.name}

    try:
        # Read and encode image
        with open(image_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')

        print(f"   🔄 Processing: {image_path.name}")

        # Call API
        response = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}},
                    {"type": "text", "text": "Extract all text from this image. Return plain text only."}
                ]
            }],
            timeout=180
        )

        # Save result
        text = response.choices[0].message.content
        output_txt.parent.mkdir(parents=True, exist_ok=True)
        output_txt.write_text(text, encoding='utf-8')

        print(f"   ✅ Done: {image_path.name} ({len(text)} chars)")
        return {"success": True, "source": image_path.name, "text_length": len(text)}

    except Exception as e:
        print(f"   ❌ Error: {image_path.name} - {e}")
        return {"error": str(e), "source": image_path.name}


def main():
    if len(sys.argv) < 3:
        print("Usage: DASHSCOPE_API_KEY=key python3 test_transcribe_standalone.py INPUT_FOLDER OUTPUT_FOLDER")
        print("\nExample:")
        print("  DASHSCOPE_API_KEY=sk-xxx python3 test_transcribe_standalone.py \\")
        print("    '/Users/dtubb/Documents/fichero/Small Test/1931 Antonio' \\")
        print("    '/Users/dtubb/Documents/fichero/Small Test/1931 Antonio Transcriptions'")
        return 1

    input_folder = Path(sys.argv[1])
    output_folder = Path(sys.argv[2])

    # Check API key
    load_dotenv()
    api_key = os.environ.get('DASHSCOPE_API_KEY')
    if not api_key:
        print("❌ DASHSCOPE_API_KEY not set")
        return 1

    print("=" * 70)
    print("🧪 Testing DashScope Qwen OCR")
    print("=" * 70)
    print(f"📂 Input:  {input_folder}")
    print(f"📂 Output: {output_folder}")
    print(f"🔑 API:    {api_key[:10]}...")
    print("=" * 70)

    # Create manifest
    try:
        manifest = create_simple_manifest(input_folder)
    except Exception as e:
        print(f"❌ Error creating manifest: {e}")
        return 1

    # Read manifest
    images = []
    with open(manifest, 'r') as f:
        for line in f:
            if line.strip():
                entry = json.loads(line)
                images.append(entry['source'])

    # Create OpenAI client
    client = OpenAI(
        api_key=api_key,
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        timeout=180.0
    )

    # Process images
    print(f"\n🚀 Processing {len(images)} images...")
    print("=" * 70)

    start_time = time.time()
    results = []

    for img_name in images:
        img_path = input_folder / img_name
        out_path = output_folder / img_name

        result = process_image_simple(img_path, out_path, client, "qwen-vl-ocr")
        results.append(result)

    elapsed = time.time() - start_time

    # Stats
    processed = sum(1 for r in results if r.get('success'))
    skipped = sum(1 for r in results if r.get('skipped'))
    failed = sum(1 for r in results if r.get('error'))

    print("=" * 70)
    print("✅ Complete!")
    print("=" * 70)
    print(f"📊 Stats:")
    print(f"   Total:     {len(images)}")
    print(f"   Processed: {processed}")
    print(f"   Skipped:   {skipped}")
    print(f"   Failed:    {failed}")
    print(f"⏱️  Time:      {elapsed:.1f}s ({elapsed/len(images):.1f}s per image)")
    print(f"📁 Output:    {output_folder}")
    print("=" * 70)

    # Cleanup
    manifest.unlink()

    return 0


if __name__ == "__main__":
    sys.exit(main())
