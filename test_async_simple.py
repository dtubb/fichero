#!/usr/bin/env python3
"""
Simple async test - directly uses providers without full app dependencies.

Usage:
    DASHSCOPE_API_KEY=key python3 test_async_simple.py /path/to/images
"""

import sys
import os
import time
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Add src to path to import from package structure
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

# Import providers from proper package structure
from fichero.tools.transcribe_providers.dashscope_provider import DashScopeProvider
from fichero.tools.transcribe_providers.async_batch_processor import run_async_batch


def main():
    if len(sys.argv) < 2:
        print("Usage: DASHSCOPE_API_KEY=key python3 test_async_simple.py /path/to/images")
        return 1

    image_folder = Path(sys.argv[1])

    if not image_folder.exists():
        print(f"❌ Error: Folder does not exist: {image_folder}")
        return 1

    # Load API key
    load_dotenv()
    api_key = os.environ.get('DASHSCOPE_API_KEY')

    if not api_key:
        print("❌ Error: DASHSCOPE_API_KEY not set")
        return 1

    print("=" * 80)
    print("🧪 Testing Async Transcription")
    print("=" * 80)
    print(f"📂 Folder: {image_folder}")
    print(f"🔑 API key: {api_key[:10]}...")
    print()

    # Find images
    extensions = ['.jpg', '.jpeg', '.png', '.tiff', '.tif']
    images = []
    for ext in extensions:
        images.extend(image_folder.glob(f"*{ext}"))
        images.extend(image_folder.glob(f"*{ext.upper()}"))

    images = sorted(images)[:5]  # Test with first 5

    print(f"📝 Found {len(images)} images")
    for img in images:
        print(f"   - {img.name}")
    print()

    # Create provider
    provider = DashScopeProvider(
        api_key=api_key,
        model="qwen-vl-ocr"
    )

    # Test async processing
    print("=" * 80)
    print("🚀 Running Async Processing (15 concurrent)")
    print("=" * 80)
    print()

    output_folder = image_folder / "test_async_output"
    output_folder.mkdir(exist_ok=True)

    start_time = time.time()

    try:
        results = run_async_batch(
            provider=provider,
            image_paths=images,
            output_folder=output_folder,
            max_concurrent=15,
            skip_existing=False
        )

        elapsed = time.time() - start_time

        # Stats
        processed = sum(1 for r in results if r.get('success'))
        failed = sum(1 for r in results if not r.get('success'))

        print()
        print("=" * 80)
        print("✅ Complete!")
        print("=" * 80)
        print(f"📊 Stats:")
        print(f"   Processed: {processed}")
        print(f"   Failed: {failed}")
        print(f"⏱️  Time: {elapsed:.2f}s ({elapsed/len(images):.2f}s per image)")
        print()

        # Show sample results
        print("📄 Sample Results:")
        for i, result in enumerate(results[:3], 1):
            if result.get('success'):
                text = result.get('text', '')[:100]
                print(f"   {i}. {result.get('source', 'unknown')}: {text}...")
        print()

        # Cleanup
        provider.cleanup()

        return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
