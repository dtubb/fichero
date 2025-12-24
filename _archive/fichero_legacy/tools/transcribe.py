"""
Unified transcription tool for Fichero.

This tool provides a single interface for multiple transcription providers:
- DashScope (qwen-vl-max, qwen-vl-ocr)
- OpenAI-compatible APIs
- LMStudio (local processing)

The provider is selected via the --provider parameter, making it easy to
switch between different services without changing workflow configurations.

Usage:
    # DashScope (default)
    transcribe INPUT MANIFEST OUTPUT --provider dashscope --model qwen-vl-max

    # OpenAI-compatible
    transcribe INPUT MANIFEST OUTPUT --provider openai --model qwen-vl-ocr

    # LMStudio
    transcribe INPUT MANIFEST OUTPUT --provider lmstudio --model my-model --api-url http://localhost:1234
"""

import typer
import time
import asyncio
import concurrent.futures
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from dotenv import load_dotenv

# Image size name to pixel mapping
# None means no resize (original size)
IMAGE_SIZE_MAP = {
    'original': None,
    'gigantic': 4096,
    'extra_large': 2048,
    'large': 1536,
    'medium': 1024,
    'small': 768
}

def get_image_size_pixels(size_name: str) -> int | None:
    """Convert image size name to pixel value. Returns None for original (no resize)."""
    return IMAGE_SIZE_MAP.get(size_name, 1024)  # Default to medium (1024)


# Utility to get AI defaults from app settings
def get_ai_defaults() -> Dict[str, Any]:
    """
    Get AI default settings from app configuration.

    Falls back to hardcoded defaults if settings not available.
    """
    defaults = {
        'transcription': {
            'provider': 'dashscope',
            'model': 'qwen-vl-max',
            'image_size': 'large'  # Default image size setting
        },
        'llm': {
            'provider': 'qwen',
            'model': 'qwen-max'
        },
        'describe': {
            'provider': 'dashscope',
            'model': 'qwen-vl-max'
        }
    }

    try:
        from fichero.config.settings import Settings
        settings = Settings()
        ai_defaults = settings.get('ai_defaults', {})

        if ai_defaults:
            # Merge with defaults (settings override defaults)
            if 'transcription' in ai_defaults:
                defaults['transcription'].update(ai_defaults['transcription'])
            if 'llm' in ai_defaults:
                defaults['llm'].update(ai_defaults['llm'])
            if 'describe' in ai_defaults:
                defaults['describe'].update(ai_defaults['describe'])
    except ImportError:
        pass  # Settings not available, use defaults
    except Exception:
        pass  # Any error, use defaults

    return defaults

# Import utilities
try:
    from fichero.tools.utils.batch import BatchProcessor
    from fichero.tools.utils.segment_handler import SegmentHandler
    from fichero.tools.utils.api_keys import get_qwen_key, get_openai_key, get_huggingface_token
    from fichero.tools.utils.tool_logger import get_tool_logger
except ImportError:
    from utils.batch import BatchProcessor
    from utils.segment_handler import SegmentHandler
    from utils.api_keys import get_qwen_key
    from utils.tool_logger import get_tool_logger

# Import providers
try:
    from fichero.tools.transcribe_providers.dashscope_provider import DashScopeProvider
    from fichero.tools.transcribe_providers.openai_provider import OpenAIProvider
    from fichero.tools.transcribe_providers.lmstudio_provider import LMStudioProvider
except ImportError:
    from transcribe_providers.dashscope_provider import DashScopeProvider
    from transcribe_providers.openai_provider import OpenAIProvider
    from transcribe_providers.lmstudio_provider import LMStudioProvider

# Configure logger
tool_logger = get_tool_logger('transcribe')


class ProviderFactory:
    """Factory for creating transcription providers"""

    PROVIDERS = {
        "dashscope": DashScopeProvider,
        "openai": OpenAIProvider,
        "lmstudio": LMStudioProvider
    }

    @classmethod
    def create(cls, provider: str, **config) -> Any:
        """
        Create a transcription provider.

        Args:
            provider: Provider name ("dashscope", "openai", "lmstudio")
            **config: Provider-specific configuration

        Returns:
            Provider instance

        Raises:
            ValueError: If provider not found
        """
        provider_cls = cls.PROVIDERS.get(provider.lower())
        if not provider_cls:
            available = ", ".join(cls.PROVIDERS.keys())
            raise ValueError(f"Unknown provider '{provider}'. Available: {available}")

        return provider_cls(**config)


def process_image_with_provider(
    file_path: Path,
    out_path: Path,
    provider: Any
) -> Dict:
    """
    Process a single image file with a provider.

    Args:
        file_path: Path to input image
        out_path: Path for output transcription
        provider: Provider instance

    Returns:
        Manifest-compatible result dictionary
    """
    try:
        # Ensure output directory exists
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to .txt extension
        out_path = out_path.with_suffix('.txt')

        # Skip if already exists
        if out_path.exists():
            rel_path = SegmentHandler.get_relative_path(file_path)
            tool_logger.info(f"Skipping existing file: {rel_path}")
            return {
                "outputs": [str(rel_path.with_suffix('.txt'))],
                "source": str(rel_path),
                "skipped": True,
                "success": True
            }

        # Touch output file
        out_path.touch()

        # Process with provider
        result = provider.process_image(file_path)

        # Save transcription
        text = result.get("text", "")
        if result.get("error"):
            text = f"[ERROR] {result['error']}"

        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(text)

        # Create manifest entry
        rel_path = SegmentHandler.get_relative_path(file_path)
        manifest_entry = {
            "outputs": [str(rel_path.with_suffix('.txt'))],
            "source": str(rel_path),
            "success": result.get("success", False),
            "details": result.get("details", {})
        }

        if result.get("error"):
            manifest_entry["error"] = result["error"]

        if result.get("skipped"):
            manifest_entry["skipped"] = True

        # Add parent image info for segments
        if 'segments' in str(rel_path):
            parent_path = rel_path.parents[1]
            manifest_entry["parent_image"] = str(parent_path)
            if "segment_info" not in manifest_entry["details"]:
                manifest_entry["details"]["segment_info"] = {
                    "segment_index": int(rel_path.stem.split('_')[-1]),
                    "parent_path": str(parent_path)
                }
        else:
            manifest_entry["parent_image"] = str(rel_path)

        return manifest_entry

    except Exception as e:
        tool_logger.error(f"Error processing {file_path}: {e}")
        rel_path = SegmentHandler.get_relative_path(file_path)
        return {
            "error": str(e),
            "outputs": [str(rel_path.with_suffix('.txt'))],
            "source": str(rel_path),
            "success": False
        }


def transcribe_batch(
    source_folder: Path,
    source_manifest: Path,
    output_folder: Path,
    provider: str = "dashscope",
    model: str = "qwen-vl-max",
    api_key_cli: Optional[str] = None,
    api_url: Optional[str] = None,
    prompt: Optional[str] = None,
    max_workers: int = 5,
    use_async: bool = True,
    max_concurrent: int = 15,
    multi_image: bool = False,
    multi_image_size: int = 20,
    testing: bool = False,
    use_langgraph: bool = False,
    **kwargs
) -> Dict:
    """
    Batch transcription using pluggable providers.

    Args:
        source_folder: Source folder containing images
        source_manifest: Manifest file
        output_folder: Output folder for transcriptions
        provider: Provider to use ("dashscope", "openai", "lmstudio")
        model: Model name
        api_key_cli: API key (for cloud providers)
        api_url: API URL (for custom endpoints)
        prompt: Custom prompt for transcription
        max_workers: Number of parallel workers (for thread-based processing)
        use_async: Use async processing (3-5x faster, requires provider support)
        max_concurrent: Maximum concurrent async requests (default 15)
        multi_image: Use multi-image batching (experimental, 4-512 images per request)
        multi_image_size: Images per multi-image batch
        testing: Run on small subset
        use_langgraph: Use LangGraph workflow orchestration (visual, modular)
        **kwargs: Additional provider-specific arguments

    Returns:
        Processing statistics dictionary
    """
    tool_logger.info(f"[green]Transcribing images in {source_folder}")
    tool_logger.info(f"[cyan]Provider: {provider}, Model: {model}")

    load_dotenv()

    # Get API key for cloud providers
    api_key = None
    provider_lower = provider.lower()
    if provider_lower == "dashscope":
        api_key = get_qwen_key(api_key_cli)
        if not api_key:
            raise ValueError("API key required for DashScope (set DASHSCOPE_API_KEY)")
    elif provider_lower == "openai":
        api_key = get_openai_key(api_key_cli)
        if not api_key:
            raise ValueError("API key required for OpenAI (set OPENAI_API_KEY)")
    elif provider_lower == "huggingface":
        api_key = get_huggingface_token(api_key_cli)
        if not api_key:
            raise ValueError("API key required for HuggingFace (set HUGGINGFACE_TOKEN)")

    # Get image size from settings
    ai_defaults = get_ai_defaults()
    image_size_name = ai_defaults.get('transcription', {}).get('image_size', 'large')
    max_size_pixels = get_image_size_pixels(image_size_name)
    size_info = f"{max_size_pixels}px" if max_size_pixels else "original"
    tool_logger.info(f"[cyan]Image size: {image_size_name} ({size_info})")

    # Create provider configuration
    provider_config = {
        "model": model,
        "max_size": max_size_pixels,  # Pass image size to provider
        **kwargs
    }

    # Add provider-specific config
    if api_key:
        provider_config["api_key"] = api_key
    if api_url:
        provider_config["api_url"] = api_url if provider == "lmstudio" else None
        provider_config["base_url"] = api_url if provider != "lmstudio" else None
    if prompt:
        provider_config["prompt"] = prompt

    # Create provider instance
    try:
        provider_instance = ProviderFactory.create(provider, **provider_config)
    except Exception as e:
        tool_logger.error(f"Failed to create provider '{provider}': {e}")
        raise

    # Validate provider configuration
    if not provider_instance.validate_config():
        raise ValueError(f"Provider configuration validation failed")

    tool_logger.info(f"✅ Provider initialized: {provider_instance.name}")

    # =========================================================================
    # LangGraph Workflow Path
    # =========================================================================
    if use_langgraph:
        tool_logger.info(f"🔗 Using LangGraph workflow orchestration")

        try:
            from fichero.tools.transcribe_providers.langgraph_workflow import (
                run_transcribe_workflow_async,
                run_transcribe_workflow_sync,
                LANGGRAPH_AVAILABLE
            )
        except ImportError:
            try:
                from transcribe_providers.langgraph_workflow import (
                    run_transcribe_workflow_async,
                    run_transcribe_workflow_sync,
                    LANGGRAPH_AVAILABLE
                )
            except ImportError:
                tool_logger.warning("LangGraph workflow not available, falling back to standard processing")
                use_langgraph = False
                LANGGRAPH_AVAILABLE = False

        if use_langgraph and LANGGRAPH_AVAILABLE:
            tool_logger.info(f"📊 LangGraph workflow: load_images → process_images → save_results")

            try:
                if use_async:
                    tool_logger.info(f"🚀 Running async LangGraph workflow ({max_concurrent} concurrent)")

                    # Run async workflow
                    result = asyncio.run(run_transcribe_workflow_async(
                        source_folder=source_folder,
                        source_manifest=source_manifest,
                        output_folder=output_folder,
                        provider=provider_instance,
                        max_concurrent=max_concurrent,
                        skip_existing=True
                    ))
                else:
                    tool_logger.info(f"📝 Running sync LangGraph workflow ({max_workers} workers)")

                    # Run sync workflow
                    result = run_transcribe_workflow_sync(
                        source_folder=source_folder,
                        source_manifest=source_manifest,
                        output_folder=output_folder,
                        provider=provider_instance,
                        max_concurrent=max_workers,
                        skip_existing=True
                    )

                # Check for errors
                if result.get('error'):
                    tool_logger.error(f"❌ Workflow error: {result['error']}")

                # Log results
                stats = result.get('stats', {})
                elapsed = result.get('elapsed_time', 0.0)
                tool_logger.info(f"✅ LangGraph workflow complete!")
                tool_logger.info(f"📊 Processed: {stats.get('processed', 0)}, Failed: {stats.get('failed', 0)}, Skipped: {stats.get('skipped', 0)}")
                tool_logger.info(f"⏱️  Total time: {elapsed:.2f}s")

                # Return in expected format
                return {
                    'total': stats.get('total', 0),
                    'processed': stats.get('processed', 0),
                    'failed': stats.get('failed', 0),
                    'skipped': stats.get('skipped', 0),
                    'elapsed_time': elapsed,
                    'model_info': provider_instance.get_model_info(),
                    'workflow': 'langgraph'
                }

            except Exception as e:
                tool_logger.error(f"❌ LangGraph workflow failed: {e}")
                tool_logger.warning("Falling back to standard processing")
                use_langgraph = False

            finally:
                # Cleanup provider
                provider_instance.cleanup()

    # =========================================================================
    # Standard Processing Paths (async, multi-image, parallel, sequential)
    # =========================================================================

    # Check if async processing is requested and supported
    if use_async and hasattr(provider_instance, 'supports_async') and provider_instance.supports_async:
        tool_logger.info(f"🚀 Using async processing with {max_concurrent} concurrent requests")
        tool_logger.info(f"⚡ Expected speedup: 3-5x faster than ThreadPoolExecutor")

        try:
            # Import async batch processor
            from fichero.tools.transcribe_providers.async_batch_processor import run_async_batch
        except ImportError:
            try:
                from transcribe_providers.async_batch_processor import run_async_batch
            except ImportError:
                tool_logger.warning("Async batch processor not available, falling back to sync processing")
                use_async = False

        if use_async:
            # Load images from manifest using same logic as BatchProcessor
            import json
            image_paths = []

            with open(source_manifest, 'r') as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line)

                        # Skip directory entries
                        if entry.get('type') == 'directory':
                            continue

                        # Get paths using same logic as BatchProcessor (batch.py:62-72)
                        paths_to_process = []
                        if 'outputs' in entry and entry['outputs']:
                            for out_path in entry['outputs']:
                                if isinstance(out_path, str):
                                    paths_to_process.append(out_path)
                                elif isinstance(out_path, dict) and 'path' in out_path:
                                    paths_to_process.append(out_path['path'])
                        elif entry.get('path'):
                            paths_to_process.append(entry['path'])

                        # Build full paths using BatchProcessor logic (batch.py:141-149)
                        for path_str in paths_to_process:
                            path = Path(path_str)

                            # Resolve path relative to source_folder
                            if source_folder:
                                # Try direct path first (tools output to source_folder directly)
                                full_path = source_folder / path
                                if not full_path.exists():
                                    # Fallback: try with documents/ prefix for legacy compatibility
                                    alt_path = source_folder / 'documents' / path
                                    if alt_path.exists():
                                        full_path = alt_path
                                    else:
                                        # Log missing file for debugging
                                        tool_logger.warning(f"⚠️ File not found: {full_path} (also tried: {alt_path})")
                                        continue
                            else:
                                full_path = path

                            # Resolve symlinks to actual files for PIL/DashScope
                            if full_path.exists():
                                full_path = full_path.resolve()
                                image_paths.append(full_path)
                            else:
                                tool_logger.warning(f"⚠️ File not found after resolution: {full_path}")

            tool_logger.info(f"📂 Loaded {len(image_paths)} images from manifest")

            if testing:
                image_paths = image_paths[:5]
                tool_logger.info(f"🧪 Testing mode: limiting to {len(image_paths)} images")

            # Process with async batch processor
            start_time = time.time()

            results = run_async_batch(
                provider=provider_instance,
                image_paths=image_paths,
                output_folder=output_folder,
                max_concurrent=max_concurrent,
                skip_existing=True
            )

            elapsed = time.time() - start_time

            # Save results
            output_docs = output_folder / "documents"
            output_docs.mkdir(parents=True, exist_ok=True)

            manifest_entries = []
            processed = 0
            failed = 0
            skipped = 0

            for result in results:
                if result.get('skipped'):
                    skipped += 1
                    continue

                if result.get('success'):
                    # Get image path
                    img_name = result.get('source', '')
                    if not img_name:
                        continue

                    # Find original path
                    img_path = None
                    for path in image_paths:
                        if path.name == img_name:
                            img_path = path
                            break

                    if not img_path:
                        failed += 1
                        continue

                    # Save transcription
                    output_txt = output_docs / img_path.with_suffix('.txt').name
                    output_txt.write_text(result['text'], encoding='utf-8')
                    processed += 1

                    # Add to manifest
                    rel_path = SegmentHandler.get_relative_path(img_path)
                    manifest_entries.append({
                        "source": str(rel_path),
                        "outputs": [output_txt.name],
                        "type": "transcription",
                        "success": True,
                        "details": result.get('details', {})
                    })
                else:
                    failed += 1

            # Write manifest
            output_manifest = output_folder / "transcriptions_manifest.jsonl"
            with open(output_manifest, 'w') as f:
                for entry in manifest_entries:
                    f.write(json.dumps(entry) + '\n')

            # Note: Provider cleanup is handled by run_async_batch before loop closes
            tool_logger.info(f"✅ Async processing complete!")
            tool_logger.info(f"📊 Processed: {processed}, Failed: {failed}, Skipped: {skipped}")
            if len(image_paths) > 0:
                tool_logger.info(f"⏱️  Total time: {elapsed:.2f}s ({elapsed/len(image_paths):.2f}s per image)")
            else:
                tool_logger.info(f"⏱️  Total time: {elapsed:.2f}s")

            return {
                'total': len(image_paths),
                'processed': processed,
                'failed': failed,
                'skipped': skipped,
                'elapsed_time': elapsed,
                'model_info': provider_instance.get_model_info()
            }

    # Check multi-image support
    if multi_image:
        if not provider_instance.supports_multi_image:
            tool_logger.warning(f"⚠️ Multi-image batching requested but {provider_instance.name} doesn't support it")
            tool_logger.warning(f"Falling back to parallel processing mode")
            multi_image = False
        else:
            # Validate multi-image size
            if multi_image_size < provider_instance.min_images_per_batch:
                tool_logger.warning(
                    f"⚠️ Multi-image size {multi_image_size} is below minimum {provider_instance.min_images_per_batch}"
                )
                multi_image_size = provider_instance.min_images_per_batch
                tool_logger.info(f"Adjusted to minimum: {multi_image_size}")

            if multi_image_size > provider_instance.max_images_per_batch:
                tool_logger.warning(
                    f"⚠️ Multi-image size {multi_image_size} exceeds maximum {provider_instance.max_images_per_batch}"
                )
                multi_image_size = provider_instance.max_images_per_batch
                tool_logger.info(f"Adjusted to maximum: {multi_image_size}")

            tool_logger.info(f"🎯 Using multi-image batching: {multi_image_size} images per API request")

    # Create batch processor based on mode
    if multi_image and provider_instance.supports_multi_image:
        tool_logger.info(f"📦 Using multi-image batching mode")

        class MultiImageBatchProcessor(BatchProcessor):
            def __init__(self, *args, provider=None, multi_image_size=20, **kwargs):
                super().__init__(*args, **kwargs)
                self.provider = provider
                self.multi_image_size = multi_image_size

            def _process_batch(self, batch: list, stats: dict):
                """Process batch using multi-image API calls"""
                batch_start = time.time()

                # Build file paths
                image_paths = []
                output_paths = []
                docs_for_paths = []

                for doc in batch:
                    path = Path(doc["path"])

                    # Build full path - try direct path first, fallback to documents/
                    if self.base_folder:
                        full_path = self.base_folder / path
                        if not full_path.exists():
                            alt_path = self.base_folder / "documents" / path
                            if alt_path.exists():
                                full_path = alt_path
                    else:
                        full_path = path

                    # Create output path
                    parts = path.parts
                    if 'documents' in parts:
                        rel_path = Path(*parts[parts.index('documents') + 1:])
                    else:
                        rel_path = path
                    out_path = self.output_folder / "documents" / rel_path

                    image_paths.append(full_path)
                    output_paths.append(out_path)
                    docs_for_paths.append(doc)

                # Process in multi-image chunks
                for i in range(0, len(image_paths), self.multi_image_size):
                    chunk_paths = image_paths[i:i + self.multi_image_size]
                    chunk_outputs = output_paths[i:i + self.multi_image_size]
                    chunk_docs = docs_for_paths[i:i + self.multi_image_size]

                    # Skip if too few images for multi-image
                    if len(chunk_paths) < self.provider.min_images_per_batch:
                        tool_logger.info(f"Processing remaining {len(chunk_paths)} images individually")
                        for img_path, out_path in zip(chunk_paths, chunk_outputs):
                            result = process_image_with_provider(img_path, out_path, self.provider)
                            self.output_proc.save_entry(result)
                            if result.get("error"):
                                stats["failed"] += 1
                            elif result.get("skipped"):
                                stats["skipped"] += 1
                            else:
                                stats["processed"] += 1
                        continue

                    tool_logger.info(f"Processing multi-image chunk: {len(chunk_paths)} images")

                    try:
                        # Process multiple images in one API call
                        results = self.provider.process_multi_image(chunk_paths)

                        # Save results
                        for result, out_path, img_path in zip(results, chunk_outputs, chunk_paths):
                            # Ensure output directory exists
                            out_path.parent.mkdir(parents=True, exist_ok=True)
                            out_path = out_path.with_suffix('.txt')

                            # Skip if already exists
                            if out_path.exists():
                                rel_path = SegmentHandler.get_relative_path(img_path)
                                tool_logger.info(f"Skipping existing file: {rel_path}")
                                result["skipped"] = True
                                stats["skipped"] += 1
                            else:
                                # Save transcription
                                out_path.touch()
                                text = result.get("text", "")
                                if result.get("error"):
                                    text = f"[ERROR] {result['error']}"

                                with open(out_path, 'w', encoding='utf-8') as f:
                                    f.write(text)

                                # Update stats
                                if result.get("error"):
                                    stats["failed"] += 1
                                elif result.get("skipped"):
                                    stats["skipped"] += 1
                                else:
                                    stats["processed"] += 1

                            # Create manifest entry
                            rel_path = SegmentHandler.get_relative_path(img_path)
                            manifest_entry = {
                                "outputs": [str(rel_path.with_suffix('.txt'))],
                                "source": str(rel_path),
                                "success": result.get("success", False),
                                "details": result.get("details", {})
                            }

                            if result.get("error"):
                                manifest_entry["error"] = result["error"]
                            if result.get("skipped"):
                                manifest_entry["skipped"] = True

                            # Add parent image info
                            if 'segments' in str(rel_path):
                                parent_path = rel_path.parents[1]
                                manifest_entry["parent_image"] = str(parent_path)
                            else:
                                manifest_entry["parent_image"] = str(rel_path)

                            self.output_proc.save_entry(manifest_entry)

                    except Exception as e:
                        tool_logger.error(f"Multi-image chunk failed: {e}")
                        # Fall back to individual processing
                        for img_path, out_path in zip(chunk_paths, chunk_outputs):
                            result = process_image_with_provider(img_path, out_path, self.provider)
                            self.output_proc.save_entry(result)
                            if result.get("error"):
                                stats["failed"] += 1
                            elif result.get("skipped"):
                                stats["skipped"] += 1
                            else:
                                stats["processed"] += 1

                batch_time = time.time() - batch_start
                tool_logger.info(f"Batch of {len(batch)} images processed in {batch_time:.1f}s")

        processor = MultiImageBatchProcessor(
            input_manifest=source_manifest,
            output_folder=output_folder,
            process_name=output_folder.name if output_folder.name else "transcription",
            processor_fn=None,
            base_folder=source_folder,
            batch_size=multi_image_size * 5,  # Process larger batches
            provider=provider_instance,
            multi_image_size=multi_image_size
        )

    elif provider_instance.supports_parallel:
        tool_logger.info(f"🚀 Using parallel processing with {max_workers} workers")

        class ParallelBatchProcessor(BatchProcessor):
            def __init__(self, *args, provider=None, **kwargs):
                super().__init__(*args, **kwargs)
                self.provider = provider

            def process_batch_parallel(self, batch: list):
                """Process batch in parallel"""
                file_tasks = []
                for doc in batch:
                    path = Path(doc["path"])

                    # Build full path - try direct path first, fallback to documents/
                    if self.base_folder:
                        full_path = self.base_folder / path
                        if not full_path.exists():
                            alt_path = self.base_folder / "documents" / path
                            if alt_path.exists():
                                full_path = alt_path
                    else:
                        full_path = path

                    # Create output path
                    parts = path.parts
                    if 'documents' in parts:
                        rel_path = Path(*parts[parts.index('documents') + 1:])
                    else:
                        rel_path = path
                    out_path = self.output_folder / "documents" / rel_path

                    file_tasks.append((full_path, out_path))

                if not file_tasks:
                    tool_logger.warning("⚠️ No tasks created for batch")
                    return []

                # Process using ThreadPoolExecutor
                results = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_path = {
                        executor.submit(process_image_with_provider, full_path, out_path, self.provider): full_path
                        for full_path, out_path in file_tasks
                    }

                    for future in concurrent.futures.as_completed(future_to_path):
                        file_path = future_to_path[future]
                        try:
                            result = future.result()
                            results.append(result)
                            tool_logger.info(f"✅ Completed: {file_path.name}")
                        except Exception as e:
                            tool_logger.error(f"❌ Failed {file_path.name}: {e}")
                            results.append({
                                "error": str(e),
                                "outputs": [],
                                "source": str(file_path),
                                "success": False
                            })

                return results

            def _process_batch(self, batch: list, stats: dict):
                """Process batch (override)"""
                batch_start = time.time()

                results = self.process_batch_parallel(batch)

                batch_time = time.time() - batch_start

                tool_logger.info(f"Batch of {len(batch)} images processed in {batch_time:.1f}s")

                # Update stats
                for result in results:
                    if isinstance(result, dict):
                        self.output_proc.save_entry(result)
                        if result.get("error"):
                            stats["failed"] += 1
                        elif result.get("skipped"):
                            stats["skipped"] += 1
                        else:
                            stats["processed"] += 1

        processor = ParallelBatchProcessor(
            input_manifest=source_manifest,
            output_folder=output_folder,
            process_name=output_folder.name if output_folder.name else "transcription",
            processor_fn=None,
            base_folder=source_folder,
            batch_size=max_workers,
            provider=provider_instance
        )

    else:
        tool_logger.info(f"📝 Using sequential processing")

        class SequentialBatchProcessor(BatchProcessor):
            def __init__(self, *args, provider=None, **kwargs):
                super().__init__(*args, **kwargs)
                self.provider = provider

            def _process_batch(self, batch: list, stats: dict):
                """Process batch sequentially"""
                batch_start = time.time()

                for doc in batch:
                    path = Path(doc["path"])

                    # Build full path - try direct path first, fallback to documents/
                    if self.base_folder:
                        full_path = self.base_folder / path
                        if not full_path.exists():
                            alt_path = self.base_folder / "documents" / path
                            if alt_path.exists():
                                full_path = alt_path
                    else:
                        full_path = path

                    # Create output path
                    parts = path.parts
                    if 'documents' in parts:
                        rel_path = Path(*parts[parts.index('documents') + 1:])
                    else:
                        rel_path = path
                    out_path = self.output_folder / "documents" / rel_path

                    # Process
                    result = process_image_with_provider(full_path, out_path, self.provider)

                    # Save and update stats
                    self.output_proc.save_entry(result)
                    if result.get("error"):
                        stats["failed"] += 1
                    elif result.get("skipped"):
                        stats["skipped"] += 1
                    else:
                        stats["processed"] += 1

                batch_time = time.time() - batch_start
                tool_logger.info(f"Batch of {len(batch)} images processed in {batch_time:.1f}s")

        processor = SequentialBatchProcessor(
            input_manifest=source_manifest,
            output_folder=output_folder,
            process_name=output_folder.name if output_folder.name else "transcription",
            processor_fn=None,
            base_folder=source_folder,
            batch_size=10,
            provider=provider_instance
        )

    # Process
    try:
        result = processor.process()
        # Add model info to result for workflow tracking
        result['model_info'] = provider_instance.get_model_info()
    finally:
        # Clean up provider
        provider_instance.cleanup()

    return result


def transcribe(
    source_folder: Path = typer.Argument(..., help="Input source images folder"),
    source_manifest: Path = typer.Argument(..., help="Input source manifest"),
    output_folder: Path = typer.Argument(..., help="Output folder for transcriptions"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Provider: dashscope, openai, lmstudio (default from settings)"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model name (default from settings)"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="API key (for cloud providers)"),
    api_url: Optional[str] = typer.Option(None, "--api-url", help="API URL (for custom endpoints)"),
    prompt: Optional[str] = typer.Option(None, "--prompt", help="Custom transcription prompt"),
    use_async: bool = typer.Option(True, "--async/--no-async", help="Use async processing (3-5x faster)"),
    max_concurrent: int = typer.Option(15, "--max-concurrent", help="Max concurrent async requests"),
    max_workers: int = typer.Option(5, "--max-workers", "-w", help="Number of parallel workers (sync mode)"),
    multi_image: bool = typer.Option(False, "--multi-image", help="Use multi-image batching (Qwen-VL only, 4-512 images per request)"),
    multi_image_size: int = typer.Option(20, "--multi-image-size", help="Images per multi-image batch (4-512)"),
    testing: bool = typer.Option(False, "--testing", help="Run on small subset"),
    use_langgraph: bool = typer.Option(False, "--langgraph", help="Use LangGraph workflow orchestration"),
):
    """
    Unified transcription CLI with pluggable providers.

    Provider and model default to settings from Preferences > AI Configuration.
    Override with --provider and --model flags.

    Examples:
        # Use defaults from settings
        transcribe INPUT MANIFEST OUTPUT

        # DashScope with Qwen VL Max (async, 15 concurrent)
        transcribe INPUT MANIFEST OUTPUT --provider dashscope --model qwen-vl-max

        # DashScope with Qwen VL OCR (async, custom concurrency)
        transcribe INPUT MANIFEST OUTPUT --provider dashscope --model qwen-vl-ocr --max-concurrent 20

        # Disable async (use ThreadPoolExecutor)
        transcribe INPUT MANIFEST OUTPUT --provider dashscope --no-async --max-workers 5

        # Multi-image batching (4-512 images per API call)
        transcribe INPUT MANIFEST OUTPUT --provider dashscope --multi-image --multi-image-size 20

        # OpenAI-compatible API
        transcribe INPUT MANIFEST OUTPUT --provider openai --model qwen-vl-ocr

        # LMStudio (local)
        transcribe INPUT MANIFEST OUTPUT --provider lmstudio --model my-model

        # LangGraph workflow (visual, modular orchestration)
        transcribe INPUT MANIFEST OUTPUT --langgraph
    """
    # Get defaults from settings if not specified
    ai_defaults = get_ai_defaults()
    transcription_defaults = ai_defaults.get('transcription', {})

    actual_provider = provider or transcription_defaults.get('provider', 'dashscope')
    actual_model = model or transcription_defaults.get('model', 'qwen-vl-max')

    tool_logger.info(f"Using provider: {actual_provider}, model: {actual_model}")

    transcribe_batch(
        source_folder,
        source_manifest,
        output_folder,
        provider=actual_provider,
        model=actual_model,
        api_key_cli=api_key,
        api_url=api_url,
        prompt=prompt,
        use_async=use_async,
        max_concurrent=max_concurrent,
        max_workers=max_workers,
        multi_image=multi_image,
        multi_image_size=multi_image_size,
        testing=testing,
        use_langgraph=use_langgraph
    )


def main():
    """Main CLI entry point"""
    typer.run(transcribe)


if __name__ == "__main__":
    main()
