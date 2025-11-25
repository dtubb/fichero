#!/usr/bin/env python3
"""
Standalone comprehensive transcription benchmark.

Tests all providers and processing modes without complex package dependencies.
"""

import sys
import os
import time
import asyncio
import json
import base64
from pathlib import Path
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from PIL import Image
from io import BytesIO

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        pass

from openai import OpenAI, AsyncOpenAI


class DashScopeTestProvider:
    """Standalone DashScope provider for testing"""

    def __init__(self, api_key: str, model: str = "qwen-vl-ocr"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

        self.client = OpenAI(api_key=api_key, base_url=self.base_url, timeout=180)
        self.async_client = AsyncOpenAI(api_key=api_key, base_url=self.base_url, timeout=180)

    def encode_image(self, image_path: Path, max_size: int = 1024) -> str:
        """Encode image to base64"""
        img = Image.open(image_path)
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            new_size = tuple(int(dim * ratio) for dim in img.size)
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        buffered = BytesIO()
        img.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def process_image(self, image_path: Path) -> Dict[str, Any]:
        """Process image synchronously"""
        try:
            base64_image = self.encode_image(image_path)
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            },
                            "min_pixels": 28 * 28 * 4,
                            "max_pixels": 28 * 28 * 8192
                        },
                        {"type": "text", "text": "Extract all text from this image. Return plain text only."}
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

    async def process_image_async(self, image_path: Path) -> Dict[str, Any]:
        """Process image asynchronously"""
        try:
            base64_image = self.encode_image(image_path)
            completion = await self.async_client.chat.completions.create(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            },
                            "min_pixels": 28 * 28 * 4,
                            "max_pixels": 28 * 28 * 8192
                        },
                        {"type": "text", "text": "Extract all text from this image. Return plain text only."}
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

    def cleanup(self):
        """Cleanup sync client"""
        try:
            self.client.close()
        except:
            pass

    async def cleanup_async(self):
        """Cleanup async client"""
        try:
            await self.async_client.close()
        except:
            pass


class BenchmarkRunner:
    """Manages benchmark execution"""

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

    def test_sync(self, images: List[Path], model: str, max_workers: int = 5) -> Dict[str, Any]:
        """Test with sync ThreadPoolExecutor"""
        test_name = f"Sync ThreadPool ({max_workers} workers) - {model}"
        output_folder = self.output_base / f"output_{model.replace('-', '_')}_sync"

        print("=" * 80)
        print(f"🧪 {test_name}")
        print("=" * 80)
        print(f"📂 Output: {output_folder}")
        print()

        provider = DashScopeTestProvider(self.api_key, model)
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
            "model": model,
            "mode": f"Sync ThreadPool ({max_workers})",
            "elapsed": elapsed,
            "processed": processed,
            "failed": failed,
            "avg_per_image": elapsed/len(images),
            "output_folder": str(output_folder)
        }

    async def test_async(self, images: List[Path], model: str, max_concurrent: int = 15) -> Dict[str, Any]:
        """Test with async + semaphore"""
        test_name = f"Async Semaphore ({max_concurrent} concurrent) - {model}"
        output_folder = self.output_base / f"output_{model.replace('-', '_')}_async"

        print("=" * 80)
        print(f"🧪 {test_name}")
        print("=" * 80)
        print(f"📂 Output: {output_folder}")
        print()

        provider = DashScopeTestProvider(self.api_key, model)
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
        print("Usage: python benchmark_standalone.py /path/to/images")
        print()
        print("Tests:")
        print("  1. qwen-vl-ocr - Sync ThreadPool (5 workers)")
        print("  2. qwen-vl-ocr - Async (15 concurrent)")
        print("  3. qwen-vl-max - Sync ThreadPool (5 workers)")
        print("  4. qwen-vl-max - Async (15 concurrent)")
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
        print("Environment variables available:")
        for k in os.environ.keys():
            if 'API' in k or 'KEY' in k or 'DASH' in k:
                print(f"  {k} = {os.environ[k][:10]}..." if len(os.environ[k]) > 10 else f"  {k} = {os.environ[k]}")
        return 1

    output_base = Path(__file__).parent

    print("=" * 80)
    print("🏁 Comprehensive Transcription Benchmark")
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

    # Test 1: qwen-vl-ocr Sync
    print("\n")
    result = runner.test_sync(images, "qwen-vl-ocr", max_workers=5)
    all_results.append(result)
    time.sleep(2)

    # Test 2: qwen-vl-ocr Async
    print("\n")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(runner.test_async(images, "qwen-vl-ocr", max_concurrent=15))
        all_results.append(result)
    finally:
        loop.close()
    time.sleep(2)

    # Test 3: qwen-vl-max Sync
    print("\n")
    result = runner.test_sync(images, "qwen-vl-max", max_workers=5)
    all_results.append(result)
    time.sleep(2)

    # Test 4: qwen-vl-max Async
    print("\n")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(runner.test_async(images, "qwen-vl-max", max_concurrent=15))
        all_results.append(result)
    finally:
        loop.close()

    # Final comparison
    print("\n")
    print("=" * 80)
    print("📊 Performance Comparison")
    print("=" * 80)
    print()

    all_results.sort(key=lambda x: x['elapsed'])
    fastest = all_results[0]

    print(f"{'Test':<50} {'Time':<12} {'Speed':<10}")
    print("-" * 80)

    for result in all_results:
        speedup = fastest['elapsed'] / result['elapsed']
        speedup_str = f"{speedup:.2f}x" if speedup > 1 else "baseline"
        test_label = f"{result['model']} - {result['mode']}"
        print(f"{test_label:<50} {result['elapsed']:>8.2f}s   {speedup_str:>8}")

    print()
    print(f"🏆 Winner: {fastest['test_name']}")
    print(f"⚡ Time: {fastest['elapsed']:.2f}s ({fastest['avg_per_image']:.2f}s per image)")
    print()

    # Save results
    results_file = output_base / "benchmark_results.json"
    with open(results_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "image_count": len(images),
            "results": all_results
        }, f, indent=2)

    print(f"📄 Results saved: {results_file}")
    print()
    print("=" * 80)
    print("🏁 Benchmark Complete")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
