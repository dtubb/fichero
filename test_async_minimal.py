#!/usr/bin/env python3
"""
Minimal async test - directly imports only what's needed without app dependencies.

Usage:
    DASHSCOPE_API_KEY=key python3 test_async_minimal.py /path/to/images
"""

import sys
import os
import time
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

# Optional dotenv support
try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False
    def load_dotenv(*args, **kwargs):
        pass

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Import just what we need
from openai import AsyncOpenAI
from PIL import Image
import base64
from io import BytesIO


class MinimalDashScopeProvider:
    """Minimal DashScope provider for testing - no app dependencies"""

    def __init__(self, api_key: str, model: str = "qwen-vl-ocr", use_intl: bool = False):
        self.api_key = api_key
        self.model_name = model

        # Use China endpoint by default (most common)
        base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1" if not use_intl else "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

        self.async_client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
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

    async def process_image_async(self, image_path: Path, semaphore: Optional[asyncio.Semaphore] = None) -> Dict[str, Any]:
        """Process image with async API"""

        async def _process():
            # Try progressively smaller sizes on timeout
            for max_size in [1024, 768, 512, 256]:
                try:
                    base64_image = self.encode_image(image_path, max_size)

                    completion = await asyncio.wait_for(
                        self.async_client.chat.completions.create(
                            model=self.model_name,
                            messages=[{
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                                    },
                                    {
                                        "type": "text",
                                        "text": "Please transcribe all text in this image."
                                    }
                                ]
                            }]
                        ),
                        timeout=180
                    )

                    return {
                        "text": completion.choices[0].message.content,
                        "success": True,
                        "source": image_path.name,
                        "details": {"size": max_size}
                    }

                except asyncio.TimeoutError:
                    if max_size == 256:
                        raise
                    logger.warning(f"Timeout at {max_size}px, trying {max_size//2}px")
                    continue

        if semaphore:
            async with semaphore:
                return await _process()
        else:
            return await _process()

    async def cleanup_async(self):
        """Clean up async client"""
        await self.async_client.close()


async def process_batch_async(
    provider: MinimalDashScopeProvider,
    image_paths: List[Path],
    max_concurrent: int = 15
) -> List[Dict[str, Any]]:
    """Process batch of images with async concurrency"""

    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_one(img_path: Path, idx: int, total: int) -> Dict[str, Any]:
        logger.info(f"[{idx+1}/{total}] Processing {img_path.name}...")
        try:
            result = await provider.process_image_async(img_path, semaphore)
            logger.info(f"[{idx+1}/{total}] ✅ {img_path.name}")
            return result
        except Exception as e:
            logger.error(f"[{idx+1}/{total}] ❌ {img_path.name}: {e}")
            return {
                "text": "",
                "success": False,
                "source": img_path.name,
                "error": str(e)
            }

    tasks = [
        process_one(img, idx, len(image_paths))
        for idx, img in enumerate(image_paths)
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results


def main():
    if len(sys.argv) < 2:
        print("Usage: DASHSCOPE_API_KEY=key python3 test_async_minimal.py /path/to/images")
        return 1

    image_folder = Path(sys.argv[1])

    if not image_folder.exists():
        print(f"❌ Error: Folder does not exist: {image_folder}")
        return 1

    # Load API key - try multiple sources
    load_dotenv()
    api_key = os.environ.get('DASHSCOPE_API_KEY')

    # Try loading from parent .env
    if not api_key:
        parent_env = Path(__file__).parent.parent / ".env"
        if parent_env.exists():
            load_dotenv(parent_env)
            api_key = os.environ.get('DASHSCOPE_API_KEY')

    # Try loading from home directory
    if not api_key:
        home_env = Path.home() / ".env"
        if home_env.exists():
            load_dotenv(home_env)
            api_key = os.environ.get('DASHSCOPE_API_KEY')

    if not api_key:
        print("❌ Error: DASHSCOPE_API_KEY not set")
        print()
        print("Please set it with:")
        print("  DASHSCOPE_API_KEY=your-key python3 test_async_minimal.py /path/to/images")
        return 1

    print("=" * 80)
    print("🧪 Testing Async Transcription (Minimal)")
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
    provider = MinimalDashScopeProvider(
        api_key=api_key,
        model="qwen-vl-ocr"
    )

    # Create output folder
    output_folder = image_folder.parent / f"{image_folder.name}_async_output"
    output_folder.mkdir(exist_ok=True)

    print(f"📁 Output folder: {output_folder}")
    print()

    # Test async processing
    print("=" * 80)
    print("🚀 Running Async Processing (15 concurrent)")
    print("=" * 80)
    print()

    start_time = time.time()

    try:
        # Run async batch
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            results = loop.run_until_complete(
                process_batch_async(provider, images, max_concurrent=15)
            )
            loop.run_until_complete(provider.cleanup_async())
        finally:
            loop.close()

        elapsed = time.time() - start_time

        # Save transcriptions to output folder
        for i, result in enumerate(results):
            if result.get('success') and i < len(images):
                img_path = images[i]
                output_txt = output_folder / img_path.with_suffix('.txt').name
                output_txt.write_text(result['text'], encoding='utf-8')
                print(f"💾 Saved: {output_txt.name}")

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

        return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
