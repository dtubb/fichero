#!/usr/bin/env python3
"""
Comprehensive transcription benchmark testing all providers and processing modes.

Tests:
1. DashScope Provider (native SDK)
   - Sync ThreadPoolExecutor (5 workers)
   - Async + Semaphore (15 concurrent)
   - Multi-image batching (20 per request)

2. OpenAI Provider (OpenAI-compatible API)
   - Sync ThreadPoolExecutor (5 workers)
   - Async + Semaphore (15 concurrent)

3. Multiple Models
   - qwen-vl-ocr (fast, streaming)
   - qwen-vl-max (high quality)

Usage:
    python benchmark_comprehensive.py /path/to/images

Output:
    Creates folders beside the benchmark script with results:
    - output_dashscope_sync/
    - output_dashscope_async/
    - output_dashscope_multi/
    - output_openai_sync/
    - output_openai_async/
"""

import sys
import os
import time
import asyncio
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# Optional dotenv support
try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False
    def load_dotenv(*args, **kwargs):
        pass

# Add src to path for imports - use direct path to avoid full package import
providers_path = Path(__file__).parent / "src" / "fichero" / "tools" / "transcribe_providers"
sys.path.insert(0, str(providers_path))
sys.path.insert(0, str(Path(__file__).parent / "src" / "fichero" / "tools"))

from dashscope_provider import DashScopeProvider
from openai_provider import OpenAIProvider


class BenchmarkRunner:
    """Manages benchmark execution and result collection"""

    def __init__(self, api_key: str, image_folder: Path, output_base: Path):
        self.api_key = api_key
        self.image_folder = image_folder
        self.output_base = output_base
        self.results = []

    def get_images(self) -> List[Path]:
        """Get all images from folder"""
        extensions = ['.jpg', '.jpeg', '.png', '.tiff', '.tif']
        images = []
        for ext in extensions:
            images.extend(self.image_folder.glob(f"*{ext}"))
            images.extend(self.image_folder.glob(f"*{ext.upper()}"))
        return sorted(images)

    def save_result(self, result: Dict[str, Any], output_path: Path, filename: str):
        """Save transcription result to file"""
        output_path.mkdir(parents=True, exist_ok=True)
        txt_file = output_path / filename

        text = result.get("text", "")
        if result.get("error"):
            text = f"[ERROR] {result['error']}"

        txt_file.write_text(text, encoding='utf-8')
        return txt_file

    def test_dashscope_sync(self, images: List[Path], model: str = "qwen-vl-ocr", max_workers: int = 5) -> Dict[str, Any]:
        """Test DashScope with sync ThreadPoolExecutor"""
        test_name = f"DashScope {model} - Sync ThreadPool ({max_workers} workers)"
        output_folder = self.output_base / f"output_dashscope_{model.replace('-', '_')}_sync"

        print("=" * 80)
        print(f"🧪 {test_name}")
        print("=" * 80)
        print(f"📂 Output: {output_folder}")
        print()

        # Create provider
        provider = DashScopeProvider(
            api_key=self.api_key,
            model=model
        )

        start_time = time.time()
        results = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(provider.process_image, img): img
                for img in images
            }

            for future in as_completed(futures):
                img = futures[future]
                try:
                    result = future.result()
                    results.append(result)

                    # Save to file
                    filename = img.with_suffix('.txt').name
                    self.save_result(result, output_folder, filename)

                    status = "✅" if result.get('success') else "❌"
                    print(f"{status} {img.name}")
                except Exception as e:
                    print(f"❌ {img.name}: {e}")
                    results.append({"success": False, "error": str(e), "source": img.name})

        elapsed = time.time() - start_time

        # Cleanup
        provider.cleanup()

        # Stats
        processed = sum(1 for r in results if r.get('success'))
        failed = sum(1 for r in results if not r.get('success'))

        print()
        print(f"✅ Complete!")
        print(f"   Processed: {processed}")
        print(f"   Failed: {failed}")
        print(f"   Total time: {elapsed:.2f}s")
        print(f"   Avg per image: {elapsed/len(images):.2f}s")
        print()

        return {
            "test_name": test_name,
            "provider": "DashScope",
            "model": model,
            "mode": f"Sync ThreadPool ({max_workers} workers)",
            "elapsed": elapsed,
            "processed": processed,
            "failed": failed,
            "avg_per_image": elapsed/len(images),
            "output_folder": str(output_folder)
        }

    async def test_dashscope_async(self, images: List[Path], model: str = "qwen-vl-ocr", max_concurrent: int = 15) -> Dict[str, Any]:
        """Test DashScope with async + semaphore"""
        test_name = f"DashScope {model} - Async ({max_concurrent} concurrent)"
        output_folder = self.output_base / f"output_dashscope_{model.replace('-', '_')}_async"

        print("=" * 80)
        print(f"🧪 {test_name}")
        print("=" * 80)
        print(f"📂 Output: {output_folder}")
        print()

        # Create provider
        provider = DashScopeProvider(
            api_key=self.api_key,
            model=model
        )

        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_logging(img: Path):
            async with semaphore:
                result = await provider.process_image_async(img)

                # Save to file
                filename = img.with_suffix('.txt').name
                self.save_result(result, output_folder, filename)

                status = "✅" if result.get('success') else "❌"
                print(f"{status} {img.name}")
                return result

        start_time = time.time()

        tasks = [process_with_logging(img) for img in images]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        elapsed = time.time() - start_time

        # Cleanup
        await provider.cleanup_async()

        # Stats
        processed = sum(1 for r in results if isinstance(r, dict) and r.get('success'))
        failed = sum(1 for r in results if not (isinstance(r, dict) and r.get('success')))

        print()
        print(f"✅ Complete!")
        print(f"   Processed: {processed}")
        print(f"   Failed: {failed}")
        print(f"   Total time: {elapsed:.2f}s")
        print(f"   Avg per image: {elapsed/len(images):.2f}s")
        print()

        return {
            "test_name": test_name,
            "provider": "DashScope",
            "model": model,
            "mode": f"Async ({max_concurrent} concurrent)",
            "elapsed": elapsed,
            "processed": processed,
            "failed": failed,
            "avg_per_image": elapsed/len(images),
            "output_folder": str(output_folder)
        }

    async def test_dashscope_multi_image(self, images: List[Path], model: str = "qwen-vl-max", batch_size: int = 20) -> Dict[str, Any]:
        """Test DashScope with multi-image batching"""
        test_name = f"DashScope {model} - Multi-image ({batch_size} per batch)"
        output_folder = self.output_base / f"output_dashscope_{model.replace('-', '_')}_multi"

        print("=" * 80)
        print(f"🧪 {test_name}")
        print("=" * 80)
        print(f"📂 Output: {output_folder}")
        print()

        # Create provider
        provider = DashScopeProvider(
            api_key=self.api_key,
            model=model
        )

        if not provider.supports_multi_image:
            print(f"⚠️  Multi-image not supported for {model}, skipping...")
            return None

        # Check batch size limits
        min_batch, max_batch = provider.min_images_per_batch, provider.max_images_per_batch
        if batch_size < min_batch or batch_size > max_batch:
            print(f"⚠️  Batch size {batch_size} out of range [{min_batch}, {max_batch}], adjusting...")
            batch_size = max(min_batch, min(batch_size, max_batch))
            print(f"   Using batch size: {batch_size}")

        start_time = time.time()
        results = []

        # Process in batches
        for i in range(0, len(images), batch_size):
            batch = images[i:i + batch_size]

            if len(batch) < min_batch:
                print(f"⚠️  Remaining batch ({len(batch)}) too small, processing individually...")
                for img in batch:
                    result = provider.process_image(img)
                    results.append(result)
                    filename = img.with_suffix('.txt').name
                    self.save_result(result, output_folder, filename)
                    status = "✅" if result.get('success') else "❌"
                    print(f"{status} {img.name}")
                continue

            print(f"Processing batch {i//batch_size + 1}: {len(batch)} images")

            try:
                batch_results = provider.process_multi_image(batch)

                for result, img in zip(batch_results, batch):
                    results.append(result)
                    filename = img.with_suffix('.txt').name
                    self.save_result(result, output_folder, filename)
                    status = "✅" if result.get('success') else "❌"
                    print(f"{status} {img.name}")

            except Exception as e:
                print(f"❌ Batch failed: {e}")
                for img in batch:
                    results.append({"success": False, "error": str(e), "source": img.name})

        elapsed = time.time() - start_time

        # Cleanup
        provider.cleanup()

        # Stats
        processed = sum(1 for r in results if r.get('success'))
        failed = sum(1 for r in results if not r.get('success'))

        print()
        print(f"✅ Complete!")
        print(f"   Processed: {processed}")
        print(f"   Failed: {failed}")
        print(f"   Total time: {elapsed:.2f}s")
        print(f"   Avg per image: {elapsed/len(images):.2f}s")
        print()

        return {
            "test_name": test_name,
            "provider": "DashScope",
            "model": model,
            "mode": f"Multi-image ({batch_size} per batch)",
            "elapsed": elapsed,
            "processed": processed,
            "failed": failed,
            "avg_per_image": elapsed/len(images),
            "output_folder": str(output_folder)
        }

    def test_openai_sync(self, images: List[Path], model: str = "qwen-vl-ocr", max_workers: int = 5) -> Dict[str, Any]:
        """Test OpenAI Provider with sync ThreadPoolExecutor"""
        test_name = f"OpenAI {model} - Sync ThreadPool ({max_workers} workers)"
        output_folder = self.output_base / f"output_openai_{model.replace('-', '_')}_sync"

        print("=" * 80)
        print(f"🧪 {test_name}")
        print("=" * 80)
        print(f"📂 Output: {output_folder}")
        print()

        # Create provider
        provider = OpenAIProvider(
            api_key=self.api_key,
            model=model
        )

        start_time = time.time()
        results = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(provider.process_image, img): img
                for img in images
            }

            for future in as_completed(futures):
                img = futures[future]
                try:
                    result = future.result()
                    results.append(result)

                    # Save to file
                    filename = img.with_suffix('.txt').name
                    self.save_result(result, output_folder, filename)

                    status = "✅" if result.get('success') else "❌"
                    print(f"{status} {img.name}")
                except Exception as e:
                    print(f"❌ {img.name}: {e}")
                    results.append({"success": False, "error": str(e), "source": img.name})

        elapsed = time.time() - start_time

        # Cleanup
        provider.cleanup()

        # Stats
        processed = sum(1 for r in results if r.get('success'))
        failed = sum(1 for r in results if not r.get('success'))

        print()
        print(f"✅ Complete!")
        print(f"   Processed: {processed}")
        print(f"   Failed: {failed}")
        print(f"   Total time: {elapsed:.2f}s")
        print(f"   Avg per image: {elapsed/len(images):.2f}s")
        print()

        return {
            "test_name": test_name,
            "provider": "OpenAI",
            "model": model,
            "mode": f"Sync ThreadPool ({max_workers} workers)",
            "elapsed": elapsed,
            "processed": processed,
            "failed": failed,
            "avg_per_image": elapsed/len(images),
            "output_folder": str(output_folder)
        }

    async def test_openai_async(self, images: List[Path], model: str = "qwen-vl-ocr", max_concurrent: int = 15) -> Dict[str, Any]:
        """Test OpenAI Provider with async + semaphore"""
        test_name = f"OpenAI {model} - Async ({max_concurrent} concurrent)"
        output_folder = self.output_base / f"output_openai_{model.replace('-', '_')}_async"

        print("=" * 80)
        print(f"🧪 {test_name}")
        print("=" * 80)
        print(f"📂 Output: {output_folder}")
        print()

        # Create provider
        provider = OpenAIProvider(
            api_key=self.api_key,
            model=model
        )

        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_logging(img: Path):
            async with semaphore:
                result = await provider.process_image_async(img)

                # Save to file
                filename = img.with_suffix('.txt').name
                self.save_result(result, output_folder, filename)

                status = "✅" if result.get('success') else "❌"
                print(f"{status} {img.name}")
                return result

        start_time = time.time()

        tasks = [process_with_logging(img) for img in images]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        elapsed = time.time() - start_time

        # Cleanup
        await provider.cleanup_async()

        # Stats
        processed = sum(1 for r in results if isinstance(r, dict) and r.get('success'))
        failed = sum(1 for r in results if not (isinstance(r, dict) and r.get('success')))

        print()
        print(f"✅ Complete!")
        print(f"   Processed: {processed}")
        print(f"   Failed: {failed}")
        print(f"   Total time: {elapsed:.2f}s")
        print(f"   Avg per image: {elapsed/len(images):.2f}s")
        print()

        return {
            "test_name": test_name,
            "provider": "OpenAI",
            "model": model,
            "mode": f"Async ({max_concurrent} concurrent)",
            "elapsed": elapsed,
            "processed": processed,
            "failed": failed,
            "avg_per_image": elapsed/len(images),
            "output_folder": str(output_folder)
        }


def main():
    if len(sys.argv) < 2:
        print("Usage: python benchmark_comprehensive.py /path/to/images")
        print()
        print("This will run comprehensive benchmarks testing:")
        print("  - DashScope Provider (sync, async, multi-image)")
        print("  - OpenAI Provider (sync, async)")
        print("  - Multiple models (qwen-vl-ocr, qwen-vl-max)")
        print()
        print("Output folders will be created beside the script:")
        print("  - output_dashscope_qwen_vl_ocr_sync/")
        print("  - output_dashscope_qwen_vl_ocr_async/")
        print("  - output_dashscope_qwen_vl_max_async/")
        print("  - output_dashscope_qwen_vl_max_multi/")
        print("  - output_openai_qwen_vl_ocr_sync/")
        print("  - output_openai_qwen_vl_ocr_async/")
        print()
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
        print()
        print("Please set it with:")
        print("  export DASHSCOPE_API_KEY=your-key")
        return 1

    # Output base folder beside script
    script_dir = Path(__file__).parent
    output_base = script_dir

    print("=" * 80)
    print("🏁 Comprehensive Transcription Benchmark")
    print("=" * 80)
    print(f"📂 Input folder: {image_folder}")
    print(f"📂 Output base: {output_base}")
    print(f"🔑 API key: {api_key[:10]}...")
    print()

    # Create benchmark runner
    runner = BenchmarkRunner(api_key, image_folder, output_base)

    # Get all images
    images = runner.get_images()
    print(f"📝 Found {len(images)} images to process")
    for img in images[:10]:
        print(f"   - {img.name}")
    if len(images) > 10:
        print(f"   ... and {len(images) - 10} more")
    print()

    if len(images) == 0:
        print("❌ No images found!")
        return 1

    # Run all tests
    all_results = []

    # Test 1: DashScope qwen-vl-ocr Sync
    print("\n")
    result = runner.test_dashscope_sync(images, model="qwen-vl-ocr", max_workers=5)
    all_results.append(result)
    time.sleep(2)

    # Test 2: DashScope qwen-vl-ocr Async
    print("\n")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            runner.test_dashscope_async(images, model="qwen-vl-ocr", max_concurrent=15)
        )
        all_results.append(result)
    finally:
        loop.close()
    time.sleep(2)

    # Test 3: DashScope qwen-vl-max Async
    print("\n")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            runner.test_dashscope_async(images, model="qwen-vl-max", max_concurrent=15)
        )
        all_results.append(result)
    finally:
        loop.close()
    time.sleep(2)

    # Test 4: DashScope qwen-vl-max Multi-image
    print("\n")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            runner.test_dashscope_multi_image(images, model="qwen-vl-max", batch_size=20)
        )
        if result:
            all_results.append(result)
    finally:
        loop.close()
    time.sleep(2)

    # Test 5: OpenAI qwen-vl-ocr Sync
    print("\n")
    result = runner.test_openai_sync(images, model="qwen-vl-ocr", max_workers=5)
    all_results.append(result)
    time.sleep(2)

    # Test 6: OpenAI qwen-vl-ocr Async
    print("\n")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            runner.test_openai_async(images, model="qwen-vl-ocr", max_concurrent=15)
        )
        all_results.append(result)
    finally:
        loop.close()

    # Final comparison
    print("\n")
    print("=" * 80)
    print("📊 Performance Comparison")
    print("=" * 80)
    print()

    # Sort by elapsed time (fastest first)
    all_results.sort(key=lambda x: x['elapsed'])

    fastest = all_results[0]

    print(f"{'Test':<60} {'Time':<12} {'Speed':<10}")
    print("-" * 80)

    for result in all_results:
        speedup = fastest['elapsed'] / result['elapsed']
        if speedup > 1:
            speedup_str = f"{speedup:.2f}x"
        else:
            speedup_str = "baseline"

        test_label = f"{result['provider']} {result['model']} - {result['mode']}"
        print(f"{test_label:<60} {result['elapsed']:>8.2f}s   {speedup_str:>8}")

    print()
    print(f"🏆 Winner: {fastest['test_name']}")
    print(f"⚡ Time: {fastest['elapsed']:.2f}s ({fastest['avg_per_image']:.2f}s per image)")
    print()

    # Save detailed results
    results_file = output_base / "benchmark_results.json"
    with open(results_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "image_count": len(images),
            "results": all_results
        }, f, indent=2)

    print(f"📄 Detailed results saved to: {results_file}")
    print()

    print("=" * 80)
    print("🏁 Benchmark Complete")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
