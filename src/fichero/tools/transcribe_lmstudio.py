import os
import typer
from rich import print
from rich.progress import track
from typing_extensions import Annotated
from pathlib import Path 
from PIL import Image
from dotenv import load_dotenv 
from io import BytesIO
import base64
import requests
import asyncio
from datetime import datetime
import gc
import warnings

# Import utilities with fallback for standalone execution
try:
    # Try absolute imports first (when run from app context)
    from fichero.tools.utils.batch import BatchProcessor
    from fichero.tools.utils.processor import process_file
    from fichero.tools.utils.segment_handler import SegmentHandler
    from fichero.tools.utils.tool_logger import get_tool_logger
except ImportError:
    # Fall back to relative imports (when run standalone)
    from utils.batch import BatchProcessor
    from utils.processor import process_file
    from utils.segment_handler import SegmentHandler
    from utils.tool_logger import get_tool_logger

# Configure tool_logger
tool_logger = get_tool_logger('transcribe_lmstudio')

# Don't create semaphore at module level - create it dynamically
def get_api_semaphore():
    """Get API semaphore for current event loop"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No event loop running, create a new one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return asyncio.Semaphore(1)  # Limit to 1 concurrent API call for LMStudio running locally.

DEFAULT_PROMPT = "Extract all text line by line. Do not number lines. RETURN ONLY PLAIN TEXT. RETURN NOTHING IF NOT TEXT. SAY NOTHING ELSE. DO NOT PROCESS REVERSED TEXT, MIRRORED TEXT, GIBBERISH, OR TEXT IN LANGUAGE YOU DO NOT RECOGNIZE. RETURN EMPTY IF NOT TEXT."

# Base 64 encoding format
def encode_image(image: Image.Image) -> str:
    # Resize image if needed - more aggressive resizing for local processing
    max_size = 1024  # Reduced from 1500 to 1024 for faster local processing
    width, height = image.size
    aspect_ratio = max(width, height) / float(min(width, height))
    
    # Skip extremely wide/tall images
    if aspect_ratio > 200:
        return ""
        
    if width > max_size or height > max_size:
        if width > height:
            new_width = max_size
            new_height = int((max_size / width) * height)
        else:
            new_height = max_size
            new_width = int((max_size / height) * width)
        image = image.resize((new_width, new_height), Image.LANCZOS)
    
    # Encode resized image with more compression
    buffered = BytesIO()
    image.save(buffered, format="JPEG", quality=80)  # Reduced quality for better compression
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

class LMStudioTranscriber:
    def __init__(self, api_url: str, model_name: str, prompt: str = DEFAULT_PROMPT):
        self.api_url = api_url
        self.model_name = model_name
        self.prompt = prompt
        # Create a session for connection pooling and proper cleanup
        self.session = requests.Session()

    async def process_image(self, image: Image.Image) -> str:
        """Process an image using LMStudio's API"""
        try:
            # Encode image using consistent method
            base64_image = encode_image(image)
            if not base64_image:
                tool_logger.error("Failed to encode image - possibly too wide/tall")
                return ""

            # Prepare the request payload
            payload = {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": self.prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ]
                    }
                ],
                "max_tokens": 2048,
                "temperature": 0.7
            }

            # Make the API request
            async with get_api_semaphore():
                # Retry logic for API calls
                max_retries = 3
                retry_delay = 1.0  # Start with 1 second delay
                
                for attempt in range(max_retries):
                    try:
                        response = self.session.post(
                            f"{self.api_url}/chat/completions",
                            json=payload,
                            headers={"Content-Type": "application/json"}
                        )
                        response.raise_for_status()
                        
                        # If we get here, the API call succeeded
                        break
                        
                    except Exception as api_error:
                        if attempt < max_retries - 1:
                            tool_logger.warning(f"LMStudio API call failed (attempt {attempt + 1}/{max_retries}): {api_error}")
                            tool_logger.info(f"Retrying in {retry_delay:.1f} seconds...")
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                        else:
                            # Final attempt failed
                            tool_logger.error(f"LMStudio API call failed after {max_retries} attempts: {api_error}")
                            raise api_error

            # Extract the transcription from the response
            result = response.json()
            if "choices" not in result:
                tool_logger.error(f"LMStudio API response missing 'choices': {result}")
                return ""
            transcription = result["choices"][0]["message"]["content"].strip()

            return transcription

        except Exception as e:
            tool_logger.error(f"Error in LMStudio processing: {e}")
            return ""

    def cleanup(self):
        """Clean up resources"""
        try:
            if hasattr(self, 'session'):
                self.session.close()
        except Exception as e:
            tool_logger.warning(f"Error cleaning up LMStudio transcriber: {e}")

async def process_image(file_path: Path, out_path: Path, api_url: str, model_name: str) -> dict:
    """Process a single image file, returning manifest-compatible output"""
    transcriber = None
    try:
        # Ensure output directory exists
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert output path to .txt extension
        out_path = out_path.with_suffix('.txt')
        
        # Skip if already exists and return proper manifest entry
        if out_path.exists():
            rel_path = SegmentHandler.get_relative_path(file_path)
            tool_logger.info(f"Skipping existing file: {rel_path}")
            return {
                "outputs": [str(rel_path.with_suffix('.txt'))],
                "source": str(rel_path),
                "skipped": True,
                "success": True
            }
        
        out_path.touch()
        
        try:
            # Add timestamp to show concurrent execution
            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            tool_logger.info(f"[{timestamp}] Starting to process: {file_path.name}")
            
            # Initialize transcriber
            transcriber = LMStudioTranscriber(
                api_url=api_url,
                model_name=model_name,
                prompt=DEFAULT_PROMPT
            )
            
            # Load and process image
            try:
                # Convert to RGB and resize if needed
                image = Image.open(file_path).convert("RGB")
                # Log original size
                orig_width, orig_height = image.size
                tool_logger.info(f"Original image size: {orig_width}x{orig_height}")
            except Exception as e:
                tool_logger.error(f"Failed to open image {file_path}: {e}")
                return {
                    "error": f"Failed to open image: {e}",
                    "outputs": [str(SegmentHandler.get_relative_path(out_path))],
                    "source": str(SegmentHandler.get_relative_path(file_path))
                }
            
            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            tool_logger.info(f"[{timestamp}] Sending to LMStudio API: {file_path.name}")
            
            transcription = await transcriber.process_image(image)
            
            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            tool_logger.info(f"[{timestamp}] Received response from LMStudio API for: {file_path.name}")
            
            # Save transcription
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(transcription)
            
            # Create manifest entry with .txt extension
            rel_path = SegmentHandler.get_relative_path(file_path)
            result = {
                "outputs": [str(rel_path.with_suffix('.txt'))],
                "source": str(rel_path),
                "details": {
                    "has_content": bool(transcription.strip()),
                    "text_length": len(transcription.strip()),
                    "processed_at": datetime.now().isoformat(),
                    "model": model_name,
                    "num_lines": len(transcription.strip().split('\n')),
                    "parent_info": {
                        "path": str(rel_path),
                        "relative_path": str(rel_path),
                        "original_size": f"{orig_width}x{orig_height}"
                    }
                }
            }
            
            # Add parent image info
            if 'segments' in str(rel_path):
                parent_path = rel_path.parents[1]
                result["parent_image"] = str(parent_path)
                result["details"]["segment_info"] = {
                    "segment_index": int(rel_path.stem.split('_')[-1]),
                    "parent_path": str(parent_path)
                }
            else:
                result["parent_image"] = str(rel_path)
                
            return result
            
        except Exception as e:
            tool_logger.error(f"Error processing image {file_path}: {str(e)}")
            # Return error but keep empty file
            return {
                "error": str(e),
                "outputs": [str(SegmentHandler.get_relative_path(out_path))],
                "source": str(SegmentHandler.get_relative_path(file_path))
            }

    except Exception as e:
        tool_logger.error(f"Error processing {file_path}: {e}")
        return {"error": str(e)}
    finally:
        # Clean up transcriber resources
        if transcriber:
            transcriber.cleanup()

def transcribe_batch(
    source_folder: Path,
    source_manifest: Path,
    output_folder: Path,
    api_url: str,
    model_name: str,
    testing: bool = False,
    **kwargs
) -> dict:
    """Batch transcription using LMStudio"""
    tool_logger.info(f"[green]Transcribing images in {source_folder}")
    tool_logger.info(f"[cyan]Using model {model_name}")
    
    # Create a custom batch processor that handles async properly
    class AsyncBatchProcessor(BatchProcessor):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.pending_tasks = []
            self.batch_times = []  # Track time for each batch
            
        async def process_batch_async(self, batch: list):
            """Process a batch of files asynchronously"""
            tasks = []
            for doc in batch:
                path = Path(doc["path"])
                
                # Use base folder directly with documents/ prefix like other scripts
                if self.base_folder:
                    if "documents" not in str(self.base_folder):
                        full_path = self.base_folder / "documents" / path
                    else:
                        full_path = self.base_folder / path
                else:
                    full_path = path
                
                # Create output path
                parts = path.parts
                if 'documents' in parts:
                    rel_path = Path(*parts[parts.index('documents') + 1:])
                else:
                    rel_path = path
                out_path = self.output_folder / "documents" / rel_path
                
                # Add to tasks
                tasks.append(process_image(full_path, out_path, api_url, model_name))
            
            # Process all tasks concurrently
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                return results
            return []

        def _process_batch(self, batch: list, stats: dict, progress, task):
            """Override to use async processing"""
            import time
            batch_start = time.time()
            
            # Get the current event loop
            loop = asyncio.get_event_loop()
            
            # Run the async batch processing in the current event loop
            results = loop.run_until_complete(self.process_batch_async(batch))
            
            batch_time = time.time() - batch_start
            self.batch_times.append(batch_time)
            
            # Show time savings
            sequential_estimate = len(batch) * 8  # Assume ~8 seconds per image sequentially
            tool_logger.info(f"Batch of {len(batch)} images processed in {batch_time:.1f}s")
            tool_logger.info(f"Sequential processing would take ~{sequential_estimate}s")
            tool_logger.info(f"Time saved: {sequential_estimate - batch_time:.1f}s ({(sequential_estimate - batch_time) / sequential_estimate * 100:.0f}%)")
            
            # Process results
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    tool_logger.error(f"Error: {result}")
                    stats["failed"] += 1
                elif isinstance(result, dict):
                    self.output_proc.save_entry(result)
                    if result.get("error"):
                        stats["failed"] += 1
                    elif result.get("skipped"):
                        stats["skipped"] += 1
                    else:
                        stats["processed"] += 1
                
                progress.update(task, advance=1, **stats)
                
        def process(self):
            """Override to add timing summary"""
            result = super().process()
            
            # Show overall time savings summary
            if self.batch_times:
                total_time = sum(self.batch_times)
                total_images = result.get('processed', 0) + result.get('failed', 0) + result.get('skipped', 0)
                sequential_estimate = total_images * 8
                
                tool_logger.info("🚀 Async Processing Summary:")
                tool_logger.info(f"Total images: {total_images}")
                tool_logger.info(f"Processed: {result.get('processed', 0)}")
                tool_logger.info(f"Skipped: {result.get('skipped', 0)}")
                tool_logger.info(f"Failed: {result.get('failed', 0)}")
                tool_logger.info(f"Total time: {total_time:.1f}s")
                tool_logger.info(f"Sequential estimate: {sequential_estimate}s")
                tool_logger.info(f"Time saved: {sequential_estimate - total_time:.1f}s ({(sequential_estimate - total_time) / sequential_estimate * 100:.0f}%)")
                tool_logger.info(f"Average time per image: {total_time / total_images:.1f}s")
                
            return result

    # Use the async batch processor
    processor = AsyncBatchProcessor(
        input_manifest=source_manifest,
        output_folder=output_folder,
        process_name="transcription",
        processor_fn=None,  # Not used in async version
        base_folder=source_folder,
        batch_size=1  # Process 1 image at a time for LMStudio
    )
    
    return processor.process()

def transcribe(
    source_folder: Path = typer.Argument(..., help="Input source folder"),
    source_manifest: Path = typer.Argument(..., help="Input source manifest"),
    output_folder: Path = typer.Argument(..., help="Output folder for transcriptions"),
    api_url: str = typer.Option(
        "http://localhost:1234",
        "--api-url",
        help="LMStudio API URL (without /v1)"
    ),
    model_name: str = typer.Option(
        ...,  # No default, must be provided
        "--model", "-m",
        help="Model name in LMStudio (e.g. qwen2.5-vl-7b-instruct)"
    ),
    testing: bool = typer.Option(False, help="Run on a small subset of data"),
):
    """Batch transcription CLI using LMStudio for processing"""
    # Ensure API URL has /v1 for chat completions
    if not api_url.endswith('/v1'):
        api_url = f"{api_url}/v1"
    
    tool_logger.info(f"Using LMStudio API: {api_url}")
    tool_logger.info(f"Using model: {model_name}")

    transcribe_batch(
        source_folder,
        source_manifest,
        output_folder,
        api_url,
        model_name,
        testing
    )

def cleanup_resources():
    """Clean up all resources to prevent ResourceWarnings"""
    try:
        import asyncio
        import gc
        import warnings
        
        # Suppress ResourceWarnings during cleanup
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            
            # Get the current event loop if it exists
            try:
                loop = asyncio.get_running_loop()
                # Cancel all pending tasks
                pending_tasks = asyncio.all_tasks(loop)
                if pending_tasks:
                    for task in pending_tasks:
                        if not task.done():
                            task.cancel()
                    
                    # Wait briefly for tasks to cancel
                    try:
                        loop.run_until_complete(asyncio.wait(pending_tasks, timeout=1.0))
                    except Exception:
                        pass
                
                # Close the loop if it's not the main loop
                if not loop.is_closed():
                    loop.close()
                    
            except RuntimeError:
                # No running event loop
                pass
            
            # Force garbage collection to clean up any remaining resources
            gc.collect()
            
    except Exception:
        # Ignore cleanup errors
        pass

if __name__ == "__main__":
    try:
        typer.run(transcribe)
    finally:
        cleanup_resources() 