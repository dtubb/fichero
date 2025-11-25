#!/usr/bin/env python3
"""
Comprehensive benchmark comparing all transcription approaches:
1. Sync (ThreadPoolExecutor with 5 workers)
2. Async (AsyncOpenAI with 15 concurrent + semaphore)
3. Batch processing (if different from sync)

Usage:
    python benchmark_all_approaches.py /path/to/images

This will test all approaches on the same images and show performance comparison.
"""

import sys
import os
import time
import asyncio
from pathlib import Path
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

# Optional dotenv support
try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False
    def load_dotenv(*args, **kwargs):
        pass

from openai import OpenAI, AsyncOpenAI
from PIL import Image
import base64
from io import BytesIO


class BenchmarkProvider:
    """Unified provider for benchmarking all approaches"""

    def __init__(self, api_key: str, model: str = "qwen-vl-ocr"):
        self.api_key = api_key
        self.model_name = model
        self.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

        # Sync client for ThreadPoolExecutor
        self.client = OpenAI(
            api_key=api_key,
            base_url=self.base_url,
            timeout=180
        )

        # Async client for async/await
        self.async_client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.base_url,
            timeout=180
        )

    def encode_image(self, image_path: Path, max_size: int = 1024) -> str:
        """Encode image to base64"""
        img = Image.open(image_path)

        # Resize if needed
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            new_size = tuple(int(dim * ratio) for dim in img.size)
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        # Convert to base64
        buffered = BytesIO()
        img.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def process_image_sync(self, image_path: Path) -> Dict[str, Any]:
        """Process image with sync OpenAI client (for ThreadPoolExecutor)"""
        try:
            base64_image = self.encode_image(image_path)

            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                        {"type": "text", "text": "Please transcribe all text in this image."}
                    ]
                }]
            )

            return {
                "text": completion.choices[0].message.content,
                "success": True,
                "source": image_path.name
            }
        except Exception as e:
            return {
                "text": "",
                "success": False,
                "source": image_path.name,
                "error": str(e)
            }

    async def process_image_async(self, image_path: Path, semaphore: asyncio.Semaphore) -> Dict[str, Any]:
        """Process image with async OpenAI client + semaphore"""
        async with semaphore:
            try:
                base64_image = self.encode_image(image_path)

                completion = await asyncio.wait_for(
                    self.async_client.chat.completions.create(
                        model=self.model_name,
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                                {"type": "text", "text": "Please transcribe all text in this image."}
                            ]
                        }]
                    ),
                    timeout=180
                )

                return {
                    "text": completion.choices[0].message.content,
                    "success": True,
                    "source": image_path.name
                }
            except Exception as e:
                return {
                    "text": "",
                    "success": False,
                    "source": image_path.name,
                    "error": str(e)
                }

    def cleanup(self):
        """Clean up sync client"""
        try:
            self.client.close()
        except:
            pass

    async def cleanup_async(self):
        """Clean up async client"""
        try:
            await self.async_client.close()
        except:
            pass


def benchmark_threadpool(provider: BenchmarkProvider, images: List[Path], max_workers: int = 5) -> Dict[str, Any]:
    """Benchmark ThreadPoolExecutor approach"""
    print("=" * 80)
    print(f"🧪 Test 1: ThreadPoolExecutor ({max_workers} workers)")
    print("=" * 80)
    print()

    start_time = time.time()

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(provider.process_image_sync, img) for img in images]

        for future in as_completed(futures):
            try:
                result = future.result()
                results.append(result)
                status = "✅" if result.get('success') else "❌"
                print(f"{status} {result.get('source', 'unknown')}")
            except Exception as e:
                print(f"❌ Error: {e}")
                results.append({"success": False, "error": str(e)})

    elapsed = time.time() - start_time

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
        "approach": f"ThreadPoolExecutor ({max_workers} workers)",
        "elapsed": elapsed,
        "processed": processed,
        "failed": failed,
        "avg_per_image": elapsed/len(images)
    }


async def benchmark_async(provider: BenchmarkProvider, images: List[Path], max_concurrent: int = 15) -> Dict[str, Any]:
    """Benchmark async/await + semaphore approach"""
    print("=" * 80)
    print(f"🧪 Test 2: Async/Await + Semaphore ({max_concurrent} concurrent)")
    print("=" * 80)
    print()

    start_time = time.time()

    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_with_logging(img: Path, idx: int, total: int):
        result = await provider.process_image_async(img, semaphore)
        status = "✅" if result.get('success') else "❌"
        print(f"{status} {result.get('source', 'unknown')}")
        return result

    tasks = [
        process_with_logging(img, idx, len(images))
        for idx, img in enumerate(images)
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    elapsed = time.time() - start_time

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
        "approach": f"Async + Semaphore ({max_concurrent} concurrent)",
        "elapsed": elapsed,
        "processed": processed,
        "failed": failed,
        "avg_per_image": elapsed/len(images)
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python benchmark_all_approaches.py /path/to/images")
        print()
        print("This will benchmark all transcription approaches:")
        print("  1. ThreadPoolExecutor (5 workers)")
        print("  2. Async/Await + Semaphore (15 concurrent)")
        print()
        print("Example:")
        print("  python benchmark_all_approaches.py '/Users/dtubb/Documents/fichero/Small Test/LFH_AHJM_DOC10141 small'")
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

    print("=" * 80)
    print("🏁 Transcription Approach Benchmark")
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
    provider = BenchmarkProvider(api_key=api_key, model="qwen-vl-ocr")

    # Store results
    benchmark_results = []

    # Test 1: ThreadPoolExecutor
    result1 = benchmark_threadpool(provider, images, max_workers=5)
    benchmark_results.append(result1)

    # Small delay between tests
    time.sleep(2)

    # Test 2: Async/Await + Semaphore
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result2 = loop.run_until_complete(benchmark_async(provider, images, max_concurrent=15))
        benchmark_results.append(result2)
        loop.run_until_complete(provider.cleanup_async())
    finally:
        loop.close()

    # Cleanup
    provider.cleanup()

    # Final comparison
    print("=" * 80)
    print("📊 Performance Comparison")
    print("=" * 80)
    print()

    # Sort by elapsed time (fastest first)
    benchmark_results.sort(key=lambda x: x['elapsed'])

    fastest = benchmark_results[0]
    print(f"{'Approach':<45} {'Time':<12} {'Speedup':<10}")
    print("-" * 80)

    for result in benchmark_results:
        speedup = fastest['elapsed'] / result['elapsed']
        speedup_str = f"{speedup:.2f}x" if speedup > 1 else "baseline"
        print(f"{result['approach']:<45} {result['elapsed']:>8.2f}s   {speedup_str:>8}")

    print()
    print(f"🏆 Winner: {fastest['approach']}")
    print(f"⚡ Fastest time: {fastest['elapsed']:.2f}s ({fastest['avg_per_image']:.2f}s per image)")
    print()

    # Show speedup
    slowest = benchmark_results[-1]
    overall_speedup = slowest['elapsed'] / fastest['elapsed']
    print(f"📈 Overall speedup: {overall_speedup:.2f}x faster")
    print()

    if overall_speedup >= 3.0:
        print("✅ Async processing achieved 3x+ speedup (excellent)")
    elif overall_speedup >= 2.0:
        print("✅ Async processing achieved 2x+ speedup (good)")
    elif overall_speedup >= 1.5:
        print("⚠️  Async processing achieved 1.5x+ speedup (moderate)")
    else:
        print("⚠️  Speedup less than expected")

    print()
    print("=" * 80)
    print("🏁 Benchmark Complete")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
