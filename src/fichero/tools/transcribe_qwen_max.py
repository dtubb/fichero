import typer
from pathlib import Path 
from PIL import Image
from dotenv import load_dotenv 
from io import BytesIO
import base64
from openai import OpenAI
import concurrent.futures
from datetime import datetime
import time

# Import utilities with fallback for standalone execution
try:
    # Try absolute imports first (when run from app context)
    from fichero.tools.utils.batch import BatchProcessor
    from fichero.tools.utils.segment_handler import SegmentHandler
    from fichero.tools.utils.api_keys import get_qwen_key
    from fichero.tools.utils.tool_logger import get_tool_logger
except ImportError:
    # Fall back to relative imports (when run standalone)
    from fichero.tools.utils.batch import BatchProcessor
    from fichero.tools.utils.segment_handler import SegmentHandler
    from fichero.tools.utils.api_keys import get_qwen_key
    from fichero.tools.utils.tool_logger import get_tool_logger

# Configure tool_logger
tool_logger = get_tool_logger('transcribe_qwen_max')

# Base 64 encoding format
def encode_image(image: Image.Image, max_size: int = 1024) -> str:
    """Encode image to base64 for API with configurable max size

    Args:
        image: PIL Image to encode
        max_size: Maximum dimension (width or height) in pixels.
                  Progressive values: 1024 (default) -> 768 -> 512 -> 256

    Returns:
        Base64 encoded JPEG string, or empty string for invalid images
    """
    width, height = image.size
    aspect_ratio = max(width, height) / float(min(width, height))

    # Skip extremely wide/tall images
    if aspect_ratio > 200:
        tool_logger.warning(f"Skipping image with extreme aspect ratio: {aspect_ratio:.1f}")
        return ""

    # Resize image if needed
    if width > max_size or height > max_size:
        if width > height:
            new_width = max_size
            new_height = int((max_size / width) * height)
        else:
            new_height = max_size
            new_width = int((max_size / height) * width)
        image = image.resize((new_width, new_height), Image.LANCZOS)
        tool_logger.info(f"Resized image from {width}x{height} to {new_width}x{new_height} (max_size={max_size})")

    # Encode resized image with compression
    buffered = BytesIO()
    image.save(buffered, format="JPEG", quality=80)
    encoded = base64.b64encode(buffered.getvalue()).decode("utf-8")
    size_kb = len(encoded) / 1024
    tool_logger.info(f"Encoded image size: {size_kb:.1f} KB (max_size={max_size})")
    return encoded

def process_image_sync(file_path: Path, out_path: Path, api_key: str) -> dict:
    """Process a single image file synchronously"""
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
        # Add timestamp to show processing
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        tool_logger.info(f"[{timestamp}] Starting to process: {file_path.name}")
        
        # Load and process image
        try:
            image = Image.open(file_path).convert("RGB")
            orig_width, orig_height = image.size
            tool_logger.info(f"Original image size: {orig_width}x{orig_height}")
        except Exception as e:
            tool_logger.error(f"Failed to open image {file_path}: {e}")
            # Save error to transcription file
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(f"[ERROR] Failed to open image: {e}")
            return {
                "error": f"Failed to open image: {e}",
                "outputs": [str(SegmentHandler.get_relative_path(out_path))],
                "source": str(SegmentHandler.get_relative_path(file_path))
            }
        
        # Progressive size reduction strategy for timeouts
        # Try sizes: 1024 -> 768 -> 512 -> 256
        size_attempts = [1024, 768, 512, 256]

        # Initialize synchronous OpenAI client with timeout
        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            timeout=180.0  # 3 minute timeout
        )

        completion = None

        try:
            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            tool_logger.info(f"[{timestamp}] Sending to Qwen API: {file_path.name}")

            # Try progressively smaller sizes on timeout
            for size_index, max_size in enumerate(size_attempts):
                # Encode image at current size
                base64_image = encode_image(image, max_size=max_size)

                if not base64_image:
                    tool_logger.warning(f"Failed to encode image at size {max_size}, skipping to next size")
                    continue

                # Retry logic for API calls at this size
                max_retries = 2  # 2 retries per size
                retry_delay = 1.0

                size_succeeded = False

                for attempt in range(max_retries):
                    try:
                        size_msg = f" (size={max_size}px)" if size_index > 0 else ""
                        tool_logger.info(f"🌐 Calling Qwen API{size_msg} (attempt {attempt + 1}/{max_retries}) for: {file_path.name}")

                        # Synchronous API call
                        completion = client.chat.completions.create(
                            model="qwen3-vl-235b-a22b-instruct",
                            messages=[{
                                "role": "user",
                                "content": [
                                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                                    {"type": "text", "text": "Extract all text line by line. Do not number lines. SKIP UNREADABLE TEXT. PUT IN SQUARE BRACKETS [GUESSES AND UNCERTAIN] TEXT. RETURN ONLY PLAIN TEXT. RETURN NOTHING IF NOT TEXT. SAY NOTHING ELSE. DO NOT PROCESS REVERSED TEXT, MIRRORED TEXT, OR GIBBERISH. RETURN EMPTY IF NO TEXT. SAY NOTHING ELSE."}
                                ]
                            }],
                            timeout=180  # 3 minute timeout per attempt
                        )
                        tool_logger.info(f"✅ API call succeeded for: {file_path.name}")
                        size_succeeded = True
                        break

                    except Exception as api_error:
                        error_str = str(api_error).lower()

                        # Check for 401 API key errors - these should stop everything
                        is_auth_error = "401" in error_str or "unauthorized" in error_str or "invalid_api_key" in error_str

                        if is_auth_error:
                            tool_logger.error(f"🔑 FATAL: Invalid API key error: {api_error}")
                            # Save error to file and raise to stop batch processing
                            with open(out_path, 'w', encoding='utf-8') as f:
                                f.write(f"[ERROR] Invalid API key: {api_error}")
                            raise ValueError(f"Invalid API key - processing stopped: {api_error}")

                        # Check for timeout errors - try smaller size
                        is_timeout = "timeout" in error_str or "timed out" in error_str

                        if is_timeout and size_index < len(size_attempts) - 1:
                            # This is a timeout and we have smaller sizes to try
                            next_size = size_attempts[size_index + 1]
                            tool_logger.warning(f"⏱️ Timeout at size {max_size}px, will try smaller size {next_size}px")
                            break  # Break retry loop, continue to next size

                        if attempt < max_retries - 1:
                            tool_logger.warning(f"API call failed (attempt {attempt + 1}/{max_retries}): {api_error}")
                            tool_logger.info(f"Retrying in {retry_delay:.1f} seconds...")
                            time.sleep(retry_delay)
                            retry_delay *= 2
                        else:
                            # Final attempt at this size failed
                            error_str = str(api_error).lower()
                            is_connection_error = "connection error" in error_str

                            if is_connection_error:
                                tool_logger.error(f"🌐 FATAL: Connection error after {max_retries} attempts: {api_error}")
                                # Save error to file and raise to stop batch processing
                                with open(out_path, 'w', encoding='utf-8') as f:
                                    f.write(f"[ERROR] API call failed after {max_retries} attempts: {api_error}")
                                raise ValueError(f"Connection error after {max_retries} attempts - processing stopped: {api_error}")

                            # If this is the last size attempt, fail completely
                            if size_index >= len(size_attempts) - 1:
                                tool_logger.error(f"❌ API call failed after trying all sizes: {api_error}")
                                tool_logger.warning(f"⚠️ Continuing with other files...")
                                # Save error to transcription file
                                with open(out_path, 'w', encoding='utf-8') as f:
                                    f.write(f"[ERROR] API call failed after trying all sizes: {api_error}")
                                return {
                                    "error": f"API call failed after trying all sizes: {api_error}",
                                    "outputs": [str(SegmentHandler.get_relative_path(out_path))],
                                    "source": str(SegmentHandler.get_relative_path(file_path))
                                }
                            else:
                                # Try next smaller size
                                tool_logger.warning(f"⚠️ Failed at size {max_size}px, trying smaller size")
                                break

                # If this size succeeded, stop trying smaller sizes
                if size_succeeded and completion:
                    break

            # Check if we got a completion
            if not completion:
                error_msg = "Failed to get response after trying all image sizes"
                tool_logger.error(f"❌ {error_msg}")
                with open(out_path, 'w', encoding='utf-8') as f:
                    f.write(f"[ERROR] {error_msg}")
                return {
                    "error": error_msg,
                    "outputs": [str(SegmentHandler.get_relative_path(out_path))],
                    "source": str(SegmentHandler.get_relative_path(file_path))
                }
        
            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            tool_logger.info(f"[{timestamp}] Received response from Qwen API for: {file_path.name}")
            
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
            tool_logger.error(f"API processing failed for {file_path}: {str(e)}")
            # Check if this is a fatal API key error
            error_str = str(e).lower()
            is_auth_error = "401" in error_str or "unauthorized" in error_str or "invalid_api_key" in error_str
            if is_auth_error:
                tool_logger.error(f"🔑 FATAL: Invalid API key error in API processing: {e}")
                raise ValueError(f"Invalid API key - processing stopped: {e}")
            # Otherwise continue with other files
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(f"[ERROR] API processing failed: {e}")
            return {
                "error": str(e),
                "outputs": [str(SegmentHandler.get_relative_path(out_path))],
                "source": str(SegmentHandler.get_relative_path(file_path))
            }
        
    except Exception as e:
        tool_logger.error(f"Error processing image {file_path}: {str(e)}")
        # Save error to transcription file
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(f"[ERROR] Error processing image: {e}")
        return {
            "error": str(e),
            "outputs": [str(SegmentHandler.get_relative_path(out_path))],
            "source": str(SegmentHandler.get_relative_path(file_path))
        }

def transcribe_batch(
    source_folder: Path,
    source_manifest: Path,
    output_folder: Path,
    testing: bool = False,
    api_key_cli: str = None,
    **kwargs
) -> dict:
    """Batch transcription using Qwen VL Max model with parallel processing"""
    tool_logger.info(f"[green]Transcribing images in {source_folder}")
    tool_logger.info(f"[cyan]Using model qwen-vl-max")
    
    load_dotenv()
    
    # Get API key once
    api_key = get_qwen_key(api_key_cli)
    if not api_key:
        raise ValueError("Qwen API key required")
    
    # Test API key validity before starting any processing
    tool_logger.info("🔑 Testing API key validity before starting batch processing...")
    try:
        test_client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            timeout=30.0
        )
        # Make a minimal API call to test the key
        test_response = test_client.chat.completions.create(
            model="qwen-vl-max",
            messages=[{
                "role": "user", 
                "content": [{"type": "text", "text": "test"}]
            }],
            timeout=30
        )
        tool_logger.info("✅ API key validated successfully")
    except Exception as e:
        error_str = str(e).lower()
        if "401" in error_str or "unauthorized" in error_str or "invalid_api_key" in error_str:
            tool_logger.error(f"🔑 FATAL: Invalid API key detected before processing started: {e}")
            raise ValueError(f"Invalid API key - processing stopped: {e}")
        else:
            tool_logger.warning(f"⚠️ API key test failed (but may be transient): {e}")
            tool_logger.info("Proceeding with batch processing...")
    
    # Create a custom batch processor that handles parallel processing
    class ParallelBatchProcessor(BatchProcessor):
        def __init__(self, *args, api_key=None, **kwargs):
            super().__init__(*args, **kwargs)
            self.api_key = api_key
            
        def process_batch_parallel(self, batch: list):
            """Process a batch of files using parallel processing"""
            tool_logger.info(f"⚡ Starting parallel processing for {len(batch)} files")
            
            # Prepare file tasks
            file_tasks = []
            for doc in batch:
                path = Path(doc["path"])
                
                # Use base folder directly with documents/ prefix like other scripts
                if self.base_folder:
                    if "documents" not in str(self.base_folder).lower():
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
                
                file_tasks.append((full_path, out_path, self.api_key))
            
            if not file_tasks:
                tool_logger.warning("⚠️ No tasks created for batch")
                return []
            
            # Process using ThreadPoolExecutor with synchronous functions - start with 5 workers
            max_workers = min(5, len(file_tasks))  # Start with 5 workers as requested
            tool_logger.info(f"🧵 Using ThreadPoolExecutor with {max_workers} workers")

            results = []
            api_key_error_detected = False

            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    # Submit all tasks
                    future_to_path = {
                        executor.submit(process_image_sync, full_path, out_path, api_key): full_path
                        for full_path, out_path, api_key in file_tasks
                    }

                    # Collect results as they complete
                    for future in concurrent.futures.as_completed(future_to_path):
                        file_path = future_to_path[future]
                        try:
                            result = future.result()
                            results.append(result)
                            tool_logger.info(f"✅ Completed processing: {file_path.name}")
                        except Exception as e:
                            # Check if this is a fatal error that should stop everything
                            error_str = str(e).lower()
                            is_auth_error = "401" in error_str or "unauthorized" in error_str or "invalid_api_key" in error_str
                            is_connection_error = "connection error" in error_str

                            if is_auth_error:
                                tool_logger.error(f"🔑 FATAL: Invalid API key error detected, stopping ALL processing immediately: {e}")
                                api_key_error_detected = True

                                # Cancel all remaining futures
                                for pending_future in future_to_path:
                                    if not pending_future.done():
                                        pending_future.cancel()
                                        tool_logger.info(f"🚫 Cancelled remaining task: {future_to_path[pending_future].name}")

                                # Raise immediately to stop everything
                                raise ValueError(f"Invalid API key - all processing stopped: {e}")

                            elif is_connection_error:
                                tool_logger.error(f"🌐 FATAL: Connection error detected, stopping ALL processing immediately: {e}")

                                # Cancel all remaining futures
                                for pending_future in future_to_path:
                                    if not pending_future.done():
                                        pending_future.cancel()
                                        tool_logger.info(f"🚫 Cancelled remaining task: {future_to_path[pending_future].name}")

                                # Raise immediately to stop everything
                                raise ValueError(f"Connection error - all processing stopped: {e}")

                            tool_logger.error(f"❌ Failed processing {file_path.name}: {e}")
                            results.append({
                                "error": str(e),
                                "outputs": [],
                                "source": str(file_path)
                            })
            except RuntimeError as e:
                # Fall back to sequential processing if executor can't be created (e.g., during shutdown)
                if "cannot schedule new futures after interpreter shutdown" in str(e):
                    tool_logger.warning(f"⚠️ ThreadPoolExecutor unavailable (interpreter shutting down), falling back to sequential processing")
                    # Process sequentially
                    for full_path, out_path, api_key in file_tasks:
                        try:
                            result = process_image_sync(full_path, out_path, api_key)
                            results.append(result)
                            tool_logger.info(f"✅ Completed processing: {full_path.name}")
                        except Exception as file_error:
                            tool_logger.error(f"❌ Failed processing {full_path.name}: {file_error}")
                            results.append({
                                "error": str(file_error),
                                "outputs": [],
                                "source": str(full_path)
                            })
                    tool_logger.info(f"✅ Sequential processing complete, got {len(results)} results")
                    return results
                else:
                    raise
            
            tool_logger.info(f"✅ Parallel processing complete, got {len(results)} results")
            return results

        def _process_batch(self, batch: list, stats: dict):
            """Override to use parallel processing"""
            batch_start = time.time()
            
            tool_logger.info("🚀 Using unified parallel processing (works for both CLI and GUI)")
            results = self.process_batch_parallel(batch)
            
            batch_time = time.time() - batch_start
            
            # Show time savings
            sequential_estimate = len(batch) * 8  # Assume ~8 seconds per image sequentially
            tool_logger.info(f"Batch of {len(batch)} images processed in {batch_time:.1f}s")
            tool_logger.info(f"Sequential processing would take ~{sequential_estimate}s")
            time_saved = sequential_estimate - batch_time
            tool_logger.info(f"Time saved: {time_saved:.1f}s ({(time_saved / sequential_estimate * 100):.0f}%)")
            
            # Process results
            for result in results:
                if isinstance(result, dict):
                    self.output_proc.save_entry(result)
                    if result.get("error"):
                        stats["failed"] += 1
                    elif result.get("skipped"):
                        stats["skipped"] += 1
                    else:
                        stats["processed"] += 1
                
        def process(self):
            """Override to add timing summary"""
            result = super().process()
            
            # Show overall summary
            total_images = result.get('processed', 0) + result.get('failed', 0) + result.get('skipped', 0)
            
            tool_logger.info("🚀 Parallel Processing Summary:")
            tool_logger.info(f"Total images: {total_images}")
            tool_logger.info(f"Processed: {result.get('processed', 0)}")
            tool_logger.info(f"Skipped: {result.get('skipped', 0)}")
            tool_logger.info(f"Failed: {result.get('failed', 0)}")
                
            return result

    # Use the parallel batch processor
    # Derive process name from output folder to avoid hardcoded names
    process_name = output_folder.name if output_folder.name else "transcription"
    
    processor = ParallelBatchProcessor(
        input_manifest=source_manifest,
        output_folder=output_folder,
        process_name=process_name,
        processor_fn=None,  # Not used in parallel version
        base_folder=source_folder,
        batch_size=5,  # Process 5 images per batch
        api_key=api_key
    )
    
    return processor.process()

def transcribe(
    source_folder: Path = typer.Argument(..., help="Input source images folder"),
    source_manifest: Path = typer.Argument(..., help="Input source manifest"),
    output_folder: Path = typer.Argument(..., help="Output folder for transcriptions"),
    testing: bool = typer.Option(False, help="Run on a small subset of data"),
    api_key: str = typer.Option(None, "--api-key", help="Qwen API key (falls back to shared data, then DASHSCOPE_API_KEY env var)"),
):
    """Batch transcription CLI using Qwen VL Max model"""
    transcribe_batch(
        source_folder,
        source_manifest,
        output_folder,
        testing,
        api_key
    )

def main():
    """Main CLI entry point"""
    typer.run(transcribe)

if __name__ == "__main__":
    main() 