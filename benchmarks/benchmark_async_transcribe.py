#!/usr/bin/env python3
"""
Benchmark script to compare sync vs async transcription performance.

Usage:
    DASHSCOPE_API_KEY=your-key python benchmark_async_transcribe.py /path/to/images

This will run both sync (ThreadPoolExecutor) and async (AsyncOpenAI + Semaphore)
processing on the same images and compare performance.
"""

import sys
import os
import time
from pathlib import Path
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero.tools.transcribe import transcribe_batch


def benchmark_transcription(image_folder: Path, api_key: str):
    """
    Benchmark sync vs async transcription.

    Args:
        image_folder: Folder with test images
        api_key: DashScope API key
    """
    print("=" * 80)
    print("🏁 Transcription Performance Benchmark")
    print("=" * 80)
    print(f"📂 Image folder: {image_folder}")
    print(f"🔑 API key: {api_key[:10]}...")
    print()

    # Create manifest
    manifest_path = image_folder / "benchmark_manifest.jsonl"

    import json
    extensions = ['.jpg', '.jpeg', '.png', '.tiff', '.tif']
    images = []
    for ext in extensions:
        images.extend(image_folder.glob(f"*{ext}"))
        images.extend(image_folder.glob(f"*{ext.upper()}"))

    with open(manifest_path, 'w') as f:
        for img in sorted(images):
            f.write(json.dumps({
                "source": img.name,
                "outputs": [img.name],
                "type": "file"
            }) + '\n')

    print(f"📝 Created manifest with {len(images)} images")
    print()

    # Test 1: Sync processing (ThreadPoolExecutor, 5 workers)
    print("=" * 80)
    print("🧪 Test 1: Sync Processing (ThreadPoolExecutor, 5 workers)")
    print("=" * 80)

    output_sync = image_folder / "output_sync"
    output_sync.mkdir(exist_ok=True)

    start_time = time.time()

    try:
        stats_sync = transcribe_batch(
            source_folder=image_folder,
            source_manifest=manifest_path,
            output_folder=output_sync,
            provider="dashscope",
            model="qwen-vl-ocr",
            api_key_cli=api_key,
            use_async=False,  # Disable async
            max_workers=5,
            testing=False
        )
    except Exception as e:
        print(f"❌ Sync test failed: {e}")
        import traceback
        traceback.print_exc()
        stats_sync = None

    elapsed_sync = time.time() - start_time

    if stats_sync:
        print()
        print(f"✅ Sync test complete!")
        print(f"   Processed: {stats_sync.get('processed', 0)}")
        print(f"   Failed: {stats_sync.get('failed', 0)}")
        print(f"   Skipped: {stats_sync.get('skipped', 0)}")
        print(f"   Total time: {elapsed_sync:.2f}s")
        print(f"   Avg per image: {elapsed_sync/len(images):.2f}s")
    print()

    # Test 2: Async processing (AsyncOpenAI + Semaphore, 15 concurrent)
    print("=" * 80)
    print("🧪 Test 2: Async Processing (AsyncOpenAI + Semaphore, 15 concurrent)")
    print("=" * 80)

    output_async = image_folder / "output_async"
    output_async.mkdir(exist_ok=True)

    start_time = time.time()

    try:
        stats_async = transcribe_batch(
            source_folder=image_folder,
            source_manifest=manifest_path,
            output_folder=output_async,
            provider="dashscope",
            model="qwen-vl-ocr",
            api_key_cli=api_key,
            use_async=True,  # Enable async
            max_concurrent=15,
            testing=False
        )
    except Exception as e:
        print(f"❌ Async test failed: {e}")
        import traceback
        traceback.print_exc()
        stats_async = None

    elapsed_async = time.time() - start_time

    if stats_async:
        print()
        print(f"✅ Async test complete!")
        print(f"   Processed: {stats_async.get('processed', 0)}")
        print(f"   Failed: {stats_async.get('failed', 0)}")
        print(f"   Skipped: {stats_async.get('skipped', 0)}")
        print(f"   Total time: {elapsed_async:.2f}s")
        print(f"   Avg per image: {elapsed_async/len(images):.2f}s")
    print()

    # Comparison
    print("=" * 80)
    print("📊 Performance Comparison")
    print("=" * 80)

    if stats_sync and stats_async:
        speedup = elapsed_sync / elapsed_async
        print(f"Sync (ThreadPoolExecutor, 5 workers):  {elapsed_sync:.2f}s")
        print(f"Async (AsyncOpenAI, 15 concurrent):    {elapsed_async:.2f}s")
        print()
        print(f"⚡ Speedup: {speedup:.2f}x faster")
        print()

        if speedup >= 3.0:
            print("✅ Async processing achieved 3x+ speedup (excellent)")
        elif speedup >= 2.0:
            print("✅ Async processing achieved 2x+ speedup (good)")
        elif speedup >= 1.5:
            print("⚠️  Async processing achieved 1.5x+ speedup (moderate)")
        else:
            print("⚠️  Async processing speedup less than expected")

    elif stats_sync:
        print(f"Sync only:  {elapsed_sync:.2f}s")
        print(f"(Async test failed)")

    elif stats_async:
        print(f"Async only: {elapsed_async:.2f}s")
        print(f"(Sync test failed)")

    else:
        print("❌ Both tests failed")

    print()
    print("=" * 80)
    print("🏁 Benchmark Complete")
    print("=" * 80)

    # Cleanup manifest
    if manifest_path.exists():
        manifest_path.unlink()
        print(f"🧹 Cleaned up benchmark manifest")

    return {
        'sync_time': elapsed_sync if stats_sync else None,
        'async_time': elapsed_async if stats_async else None,
        'speedup': elapsed_sync / elapsed_async if (stats_sync and stats_async) else None
    }


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: DASHSCOPE_API_KEY=key python benchmark_async_transcribe.py /path/to/images")
        print()
        print("This will benchmark sync (ThreadPoolExecutor) vs async (AsyncOpenAI + Semaphore)")
        print("processing on the same set of images.")
        print()
        print("Example:")
        print("  DASHSCOPE_API_KEY=sk-xxx python benchmark_async_transcribe.py \\")
        print("    '/Users/dtubb/Documents/fichero/Small Test/1931 Antonio'")
        return 1

    image_folder = Path(sys.argv[1])

    if not image_folder.exists():
        print(f"❌ Error: Folder does not exist: {image_folder}")
        return 1

    if not image_folder.is_dir():
        print(f"❌ Error: Not a directory: {image_folder}")
        return 1

    # Load API key
    load_dotenv()
    api_key = os.environ.get('DASHSCOPE_API_KEY')

    if not api_key:
        print("❌ Error: DASHSCOPE_API_KEY environment variable not set")
        print("   Set it with: export DASHSCOPE_API_KEY=your-key-here")
        return 1

    # Run benchmark
    benchmark_transcription(image_folder, api_key)

    return 0


if __name__ == "__main__":
    sys.exit(main())
