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
from openai import AsyncOpenAI
import asyncio
from datetime import datetime
import logging
# Import utilities with fallback for standalone execution
try:
    # Try absolute imports first (when run from app context)
    from fichero.tools.utils.batch import BatchProcessor
    from fichero.tools.utils.processor import process_file
    from fichero.tools.utils.segment_handler import SegmentHandler
    from fichero.tools.utils.api_keys import get_qwen_key
except ImportError:
    # Fall back to relative imports (when run standalone)
    from utils.batch import BatchProcessor
    from utils.processor import process_file
    from utils.segment_handler import SegmentHandler
    from utils.api_keys import get_qwen_key

# Configure logging
logging.basicConfig(level=logging.INFO)  # Changed from WARNING to INFO
logger = logging.getLogger(__name__)

# Semaphore to limit concurrent API calls
API_SEMAPHORE = asyncio.Semaphore(5)  # Limit to 5 concurrent API calls

# Base 64 encoding format
def encode_image(image: Image.Image) -> str:
    # Resize image if needed - more aggressive resizing for API
    max_size = 1024  # Reduced from 1500 to 1024 for faster API processing
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

async def process_image(file_path: Path, out_path: Path, api_key_cli: str = None) -> dict:
    """Process a single image file, returning manifest-compatible output"""
    try:
        # Ensure output directory exists
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert output path to .txt extension
        out_path = out_path.with_suffix('.txt')
        
        # Skip if already exists and return proper manifest entry
        if out_path.exists():
            rel_path = SegmentHandler.get_relative_path(file_path)
            logger.info(f"Skipping existing file: {rel_path}")
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
            logger.info(f"[{timestamp}] Starting to process: {file_path.name}")
            
            # Load and process image
            try:
                # Convert to RGB and resize if needed
                image = Image.open(file_path).convert("RGB")
                # Log original size
                orig_width, orig_height = image.size
                logger.info(f"Original image size: {orig_width}x{orig_height}")
            except Exception as e:
                logger.error(f"Failed to open image {file_path}: {e}")
                return {
                    "error": f"Failed to open image: {e}",
                    "outputs": [str(SegmentHandler.get_relative_path(out_path))],
                    "source": str(SegmentHandler.get_relative_path(file_path))
                }
            
            # Encode image for API
            base64_image = encode_image(image)
            
            # Get API key using three-tier fallback
            logger.info(f"🔑 Attempting to get Qwen API key...")
            api_key = get_qwen_key(api_key_cli)
            if api_key:
                logger.info(f"✅ Successfully obtained Qwen API key: {api_key[:10]}...{api_key[-4:]}")
            else:
                logger.error(f"❌ Failed to obtain Qwen API key from any source")
                    
            if not api_key:
                raise ValueError("Qwen API key required. Set via CLI argument, app settings, or DASHSCOPE_API_KEY environment variable.")
                
            # Initialize OpenAI client with DashScope endpoint
            client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            )
            
            # Use semaphore to limit concurrent API calls
            async with API_SEMAPHORE:
                timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                logger.info(f"[{timestamp}] Sending to Qwen API: {file_path.name}")
                
                # Get transcription using OpenAI-compatible method
                completion = await client.chat.completions.create(
                    model="qwen-vl-max",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                            {"type": "text", "text": "Extract all text line by line. Do not number lines. SKIP UNREADABLE TEXT. PUT IN SQUARE BRACKETS [GUESSES AND UNCERTAIN] TEXT. RETURN ONLY PLAIN TEXT. RETURN NOTHING IF NOT TEXT. SAY NOTHING ELSE. DO NOT PROCESS REVERSED TEXT, MIRRORED TEXT, GIBBERISH, OR TEXT IN LANGUAGE YOU DO NOT RECOGNIZE. RETURN EMPTY IF NOT TEXT."}
                        ]
                    }]
                )
            
            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            logger.info(f"[{timestamp}] Received response from Qwen API for: {file_path.name}")
            
            # Extract transcription from response
            transcription = completion.choices[0].message.content
            
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
                    "model": "qwen-vl-max",
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
            logger.error(f"Error processing image {file_path}: {str(e)}")
            # Return error but keep empty file
            return {
                "error": str(e),
                "outputs": [str(SegmentHandler.get_relative_path(out_path))],
                "source": str(SegmentHandler.get_relative_path(file_path))
            }

    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}")
        return {"error": str(e)}

def transcribe_batch(
    background_removed_folder: Path,
    background_removed_manifest: Path,
    transcribed_folder: Path,
    testing: bool = False,
    api_key_cli: str = None,
):
    """Batch transcription using Qwen VL Max model"""
    print(f"[green]Transcribing images in {background_removed_folder}")
    print(f"[cyan]Using model qwen-vl-max")
    
    load_dotenv()
    
    # API key validation happens in process_image() using utility

    # Create a custom batch processor that handles async properly
    class AsyncBatchProcessor(BatchProcessor):
        def __init__(self, *args, api_key_cli=None, **kwargs):
            super().__init__(*args, **kwargs)
            self.pending_tasks = []
            self.batch_times = []  # Track time for each batch
            self.api_key_cli = api_key_cli
            
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
                tasks.append(process_image(full_path, out_path, self.api_key_cli))
            
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
            logger.info(f"Batch of {len(batch)} images processed in {batch_time:.1f}s")
            logger.info(f"Sequential processing would take ~{sequential_estimate}s")
            logger.info(f"Time saved: {sequential_estimate - batch_time:.1f}s ({(sequential_estimate - batch_time) / sequential_estimate * 100:.0f}%)")
            
            # Process results
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Error: {result}")
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
                
                logger.info("🚀 Async Processing Summary:")
                logger.info(f"Total images: {total_images}")
                logger.info(f"Processed: {result.get('processed', 0)}")
                logger.info(f"Skipped: {result.get('skipped', 0)}")
                logger.info(f"Failed: {result.get('failed', 0)}")
                logger.info(f"Total time: {total_time:.1f}s")
                logger.info(f"Sequential estimate: {sequential_estimate}s")
                logger.info(f"Time saved: {sequential_estimate - total_time:.1f}s ({(sequential_estimate - total_time) / sequential_estimate * 100:.0f}%)")
                logger.info(f"Average time per image: {total_time / total_images:.1f}s")
                
            return result

    # Use the async batch processor
    processor = AsyncBatchProcessor(
        input_manifest=background_removed_manifest,
        output_folder=transcribed_folder,
        process_name="transcription",
        processor_fn=None,  # Not used in async version
        base_folder=background_removed_folder,
        batch_size=5,  # Process 5 images concurrently
        api_key_cli=api_key_cli
    )
    
    return processor.process()

def transcribe(
    background_removed_folder: Path = typer.Argument(..., help="Input background removed images folder"),
    background_removed_manifest: Path = typer.Argument(..., help="Input background removed manifest"),
    transcribed_folder: Path = typer.Argument(..., help="Output folder for transcriptions"),
    testing: bool = typer.Option(False, help="Run on a small subset of data"),
    api_key: str = typer.Option(None, "--api-key", help="Qwen API key (falls back to shared data, then DASHSCOPE_API_KEY env var)"),
):
    """Batch transcription CLI using Qwen VL Max model"""
    transcribe_batch(
        background_removed_folder,
        background_removed_manifest,
        transcribed_folder,
        testing,
        api_key
    )

if __name__ == "__main__":
    typer.run(transcribe) 