#!/usr/bin/env python3
"""
Ultimate comprehensive benchmark testing ALL transcription providers and approaches.

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
    python benchmark_all_providers.py /path/to/images

Output:
    Creates benchmarks/output_* folders with results
"""

import sys
import os
import time
import asyncio
import json
from pathlib import Path
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# Add parent/src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        pass

# Import production providers
from fichero.tools.transcribe_providers.dashscope_provider import DashScopeProvider
from fichero.tools.transcribe_providers.openai_provider import OpenAIProvider


class BenchmarkRunner:
    """Manages comprehensive benchmark execution"""

    def __init__(self, api_key: str, image_folder: Path, output_base: Path):
        self.api_key = api_key
        self.image_folder = image_folder
        self.output_base = output_base

    def get_images(self) -> List[Path]:
        """Get all images from folder"""
        extensions = ['.jpg', '.jpeg', '.png', '.tiff', '.tif']
        images = []
        for ext in extensions:
            images.extend(self.image_folder.glob(f"*{ext}"))
            images.extend(self.image_folder.glob(f"*{ext.upper()}"))
        return sorted(images)

    def save_result(self, result: Dict[str, Any], output_path: Path, filename: str):
        """Save transcription result"""
        output_path.mkdir(parents=True, exist_ok=True)
        txt_file = output_path / filename
        text = result.get("text", "")
        if result.get("error"):
            text = f"[ERROR] {result['error']}"
        txt_file.write_text(text, encoding='utf-8')

    def test_provider_sync(self, provider_cls, provider_name: str, images: List[Path],
                          model: str, max_workers: int = 5, **provider_config) -> Dict[str, Any]:
        """Test any provider with sync ThreadPoolExecutor"""
        test_name = f"{provider_name} {model} - Sync ThreadPool ({max_workers} workers)"
        output_folder = self.output_base / f"output_{provider_name.lower()}_{model.replace('-', '_')}_sync"

        print("=" * 80)
        print(f"🧪 {test_name}")
        print("=" * 80)
        print(f"📂 Output: {output_folder}")
        print()

        # Create provider instance
        provider = provider_cls(
            api_key=self.api_key,
            model=model,
            **provider_config
        )

        start_time = time.time()
        results = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(provider.process_image, img): img for img in images}
            for future in as_completed(futures):
                img = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    self.save_result(result, output_folder, img.with_suffix('.txt').name)
                    status = "✅" if result.get('success') else "❌"
                    error_msg = f" - {result.get('error', '')}" if result.get('error') else ""
                    print(f"{status} {img.name}{error_msg}")
                except Exception as e:
                    print(f"❌ {img.name}: {e}")
                    results.append({"success": False, "error": str(e), "source": img.name})

        elapsed = time.time() - start_time
        provider.cleanup()

        processed = sum(1 for r in results if r.get('success'))
        failed = len(results) - processed

        print()
        print(f"✅ Complete!")
        print(f"   Processed: {processed}, Failed: {failed}")
        print(f"   Total: {elapsed:.2f}s ({elapsed/len(images):.2f}s per image)")
        print()

        return {
            "test_name": test_name,
            "provider": provider_name,
            "model": model,
            "mode": f"Sync ThreadPool ({max_workers})",
            "elapsed": elapsed,
            "processed": processed,
            "failed": failed,
            "avg_per_image": elapsed/len(images),
            "output_folder": str(output_folder)
        }

    async def test_provider_async(self, provider_cls, provider_name: str, images: List[Path],
                                  model: str, max_concurrent: int = 15, **provider_config) -> Dict[str, Any]:
        """Test any provider with async + semaphore"""
        test_name = f"{provider_name} {model} - Async ({max_concurrent} concurrent)"
        output_folder = self.output_base / f"output_{provider_name.lower()}_{model.replace('-', '_')}_async"

        print("=" * 80)
        print(f"🧪 {test_name}")
        print("=" * 80)
        print(f"📂 Output: {output_folder}")
        print()

        # Create provider instance
        provider = provider_cls(
            api_key=self.api_key,
            model=model,
            **provider_config
        )

        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_logging(img: Path):
            async with semaphore:
                result = await provider.process_image_async(img)
                self.save_result(result, output_folder, img.with_suffix('.txt').name)
                status = "✅" if result.get('success') else "❌"
                error_msg = f" - {result.get('error', '')}" if result.get('error') else ""
                print(f"{status} {img.name}{error_msg}")
                return result

        start_time = time.time()
        tasks = [process_with_logging(img) for img in images]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start_time

        await provider.cleanup_async()

        processed = sum(1 for r in results if isinstance(r, dict) and r.get('success'))
        failed = len(results) - processed

        print()
        print(f"✅ Complete!")
        print(f"   Processed: {processed}, Failed: {failed}")
        print(f"   Total: {elapsed:.2f}s ({elapsed/len(images):.2f}s per image)")
        print()

        return {
            "test_name": test_name,
            "provider": provider_name,
            "model": model,
            "mode": f"Async ({max_concurrent})",
            "elapsed": elapsed,
            "processed": processed,
            "failed": failed,
            "avg_per_image": elapsed/len(images),
            "output_folder": str(output_folder)
        }


def main():
    if len(sys.argv) < 2:
        print("Usage: python benchmark_all_providers.py /path/to/images")
        print()
        print("Tests ALL provider approaches:")
        print("  1. DashScope qwen-vl-ocr - Sync ThreadPool (5 workers)")
        print("  2. DashScope qwen-vl-ocr - Async (15 concurrent)")
        print("  3. DashScope qwen-vl-max - Sync ThreadPool (5 workers)")
        print("  4. DashScope qwen-vl-max - Async (15 concurrent)")
        print("  5. OpenAI qwen-vl-ocr - Sync ThreadPool (5 workers)")
        print("  6. OpenAI qwen-vl-ocr - Async (15 concurrent)")
        print()
        return 1

    image_folder = Path(sys.argv[1])
    if not image_folder.exists():
        print(f"❌ Error: Folder does not exist: {image_folder}")
        return 1

    load_dotenv()
    api_key = os.environ.get('DASHSCOPE_API_KEY')
    if not api_key:
        print("❌ Error: DASHSCOPE_API_KEY not set")
        print()
        print("Please set it with:")
        print("  export DASHSCOPE_API_KEY=your-key")
        return 1

    # Output to benchmarks folder
    output_base = Path(__file__).parent

    print("=" * 80)
    print("🏁 Ultimate Provider Benchmark - ALL APPROACHES")
    print("=" * 80)
    print(f"📂 Input: {image_folder}")
    print(f"📂 Output: {output_base}")
    print(f"🔑 API key: {api_key[:10]}...{api_key[-4:]} (length: {len(api_key)})")
    print()

    runner = BenchmarkRunner(api_key, image_folder, output_base)
    images = runner.get_images()

    print(f"📝 Found {len(images)} images")
    for img in images[:10]:
        print(f"   - {img.name}")
    if len(images) > 10:
        print(f"   ... and {len(images) - 10} more")
    print()

    if len(images) == 0:
        print("❌ No images found!")
        return 1

    all_results = []

    # Test 1: DashScope qwen-vl-ocr Sync
    print("\n")
    result = runner.test_provider_sync(
        DashScopeProvider, "DashScope", images, "qwen-vl-ocr", max_workers=5
    )
    all_results.append(result)
    time.sleep(2)

    # Test 2: DashScope qwen-vl-ocr Async
    print("\n")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            runner.test_provider_async(DashScopeProvider, "DashScope", images, "qwen-vl-ocr", max_concurrent=15)
        )
        all_results.append(result)
    finally:
        loop.close()
    time.sleep(2)

    # Test 3: DashScope qwen-vl-max Sync
    print("\n")
    result = runner.test_provider_sync(
        DashScopeProvider, "DashScope", images, "qwen-vl-max", max_workers=5
    )
    all_results.append(result)
    time.sleep(2)

    # Test 4: DashScope qwen-vl-max Async
    print("\n")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            runner.test_provider_async(DashScopeProvider, "DashScope", images, "qwen-vl-max", max_concurrent=15)
        )
        all_results.append(result)
    finally:
        loop.close()
    time.sleep(2)

    # Test 5: OpenAI qwen-vl-ocr Sync
    print("\n")
    result = runner.test_provider_sync(
        OpenAIProvider, "OpenAI", images, "qwen-vl-ocr", max_workers=5
    )
    all_results.append(result)
    time.sleep(2)

    # Test 6: OpenAI qwen-vl-ocr Async
    print("\n")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            runner.test_provider_async(OpenAIProvider, "OpenAI", images, "qwen-vl-ocr", max_concurrent=15)
        )
        all_results.append(result)
    finally:
        loop.close()

    # Final comparison
    print("\n")
    print("=" * 80)
    print("📊 Ultimate Performance Comparison - ALL PROVIDERS")
    print("=" * 80)
    print()

    # Sort by elapsed time (fastest first)
    all_results.sort(key=lambda x: x['elapsed'])
    fastest = all_results[0]

    print(f"{'Provider + Model + Mode':<65} {'Time':<12} {'Speed':<10}")
    print("-" * 90)

    for result in all_results:
        speedup = fastest['elapsed'] / result['elapsed']
        speedup_str = f"{speedup:.2f}x" if speedup > 1 else "baseline"
        test_label = f"{result['provider']} {result['model']} - {result['mode']}"
        print(f"{test_label:<65} {result['elapsed']:>8.2f}s   {speedup_str:>8}")

    print()
    print(f"🏆 Winner: {fastest['test_name']}")
    print(f"⚡ Time: {fastest['elapsed']:.2f}s ({fastest['avg_per_image']:.2f}s per image)")
    print()

    # Save detailed results
    results_file = output_base / "benchmark_all_providers_results.json"
    with open(results_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "image_count": len(images),
            "results": all_results
        }, f, indent=2)

    print(f"📄 Results saved: {results_file}")
    print()
    print("=" * 80)
    print("🏁 Ultimate Benchmark Complete")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
