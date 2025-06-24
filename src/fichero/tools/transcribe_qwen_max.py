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
    from utils.batch import BatchProcessor
    from utils.segment_handler import SegmentHandler
    from utils.api_keys import get_qwen_key
    from utils.tool_logger import get_tool_logger

# Configure tool_logger
tool_logger = get_tool_logger('transcribe_qwen_max')

# Enhanced timeout and retry configuration
API_TIMEOUT = 120.0  # Increased from 60 to 120 seconds
MAX_RETRIES = 5      # Increased from 3 to 5 retries
INITIAL_RETRY_DELAY = 2.0  # Increased initial delay

def is_timeout_error(error: Exception) -> bool:
    """Check if error is a timeout-related error"""
    error_str = str(error).lower()
    timeout_indicators = [
        'timeout', 'timed out', 'request timed out',
        'connection timeout', 'read timeout',
        'deadline exceeded', 'timeout exceeded'
    ]
    return any(indicator in error_str for indicator in timeout_indicators)

def is_recoverable_error(error: Exception) -> bool:
    """Check if error is recoverable and worth retrying"""
    error_str = str(error).lower()
    recoverable_indicators = [
        'timeout', 'timed out', 'connection',
        'network', 'temporary', 'busy',
        'rate limit', 'throttling', 'overloaded'
    ]
    return any(indicator in error_str for indicator in recoverable_indicators)

# Base 64 encoding format
def encode_image(image: Image.Image) -> str:
    """Encode image to base64 for API"""
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

def process_image_sync(file_path: Path, out_path: Path, api_key: str) -> dict:
    """Process a single image file synchronously with enhanced timeout handling"""
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
            return {
                "error": f"Failed to open image: {e}",
                "outputs": [str(SegmentHandler.get_relative_path(out_path))],
                "source": str(SegmentHandler.get_relative_path(file_path)),
                "recoverable": False
            }
        
        # Encode image for API
        base64_image = encode_image(image)
        
        # Initialize synchronous OpenAI client with increased timeout
        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            timeout=API_TIMEOUT
        )
        
        try:
            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            tool_logger.info(f"[{timestamp}] Sending to Qwen API: {file_path.name}")
            
            # Enhanced retry logic for API calls with timeout-specific handling
            retry_delay = INITIAL_RETRY_DELAY
            
            for attempt in range(MAX_RETRIES):
                try:
                    tool_logger.info(f"🌐 Calling Qwen API (attempt {attempt + 1}/{MAX_RETRIES}) for: {file_path.name}")
                    
                    # Synchronous API call with increased timeout
                    completion = client.chat.completions.create(
                        model="qwen-vl-max",
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                                {"type": "text", "text": "Extract all text line by line. Do not number lines. SKIP UNREADABLE TEXT. PUT IN SQUARE BRACKETS [GUESSES AND UNCERTAIN] TEXT. RETURN ONLY PLAIN TEXT. RETURN NOTHING IF NOT TEXT. SAY NOTHING ELSE. DO NOT PROCESS REVERSED TEXT, MIRRORED TEXT, GIBBERISH, OR TEXT IN LANGUAGE YOU DO NOT RECOGNIZE. RETURN EMPTY IF NOT TEXT."}
                            ]
                        }],
                        timeout=API_TIMEOUT
                    )
                    tool_logger.info(f"✅ API call succeeded for: {file_path.name}")
                    break
                    
                except Exception as api_error:
                    is_timeout = is_timeout_error(api_error)
                    is_recoverable = is_recoverable_error(api_error)
                    
                    if attempt < MAX_RETRIES - 1:
                        if is_timeout:
                            tool_logger.warning(f"⏰ Timeout error (attempt {attempt + 1}/{MAX_RETRIES}): {api_error}")
                            tool_logger.info(f"🔄 Retrying with longer delay in {retry_delay:.1f} seconds...")
                        elif is_recoverable:
                            tool_logger.warning(f"🔄 Recoverable error (attempt {attempt + 1}/{MAX_RETRIES}): {api_error}")
                            tool_logger.info(f"🔄 Retrying in {retry_delay:.1f} seconds...")
                        else:
                            tool_logger.warning(f"❌ Non-recoverable error (attempt {attempt + 1}/{MAX_RETRIES}): {api_error}")
                            tool_logger.info(f"🔄 Final retry attempt in {retry_delay:.1f} seconds...")
                        
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        # Final attempt failed - but make timeout errors non-fatal
                        if is_timeout:
                            tool_logger.error(f"⏰ TIMEOUT: API call failed after {MAX_RETRIES} attempts: {api_error}")
                            tool_logger.warning(f"⚠️ Skipping {file_path.name} due to persistent timeout - continuing with other files")
                            return {
                                "error": f"Timeout after {MAX_RETRIES} attempts: {api_error}",
                                "outputs": [str(SegmentHandler.get_relative_path(out_path))],
                                "source": str(SegmentHandler.get_relative_path(file_path)),
                                "timeout": True,
                                "recoverable": True,
                                "attempts": MAX_RETRIES
                            }
                        else:
                            tool_logger.error(f"❌ API call failed after {MAX_RETRIES} attempts: {api_error}")
                            return {
                                "error": f"API failed after {MAX_RETRIES} attempts: {api_error}",
                                "outputs": [str(SegmentHandler.get_relative_path(out_path))],
                                "source": str(SegmentHandler.get_relative_path(file_path)),
                                "recoverable": is_recoverable,
                                "attempts": MAX_RETRIES
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
                "success": True,
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
            # Make sure this doesn't stop the entire batch
            return {
                "error": f"Processing failed: {str(e)}",
                "outputs": [str(SegmentHandler.get_relative_path(out_path))],
                "source": str(SegmentHandler.get_relative_path(file_path)),
                "recoverable": is_recoverable_error(e)
            }
        
    except Exception as e:
        tool_logger.error(f"Error processing image {file_path}: {str(e)}")
        return {
            "error": str(e),
            "outputs": [str(SegmentHandler.get_relative_path(out_path))],
            "source": str(SegmentHandler.get_relative_path(file_path)),
            "recoverable": False
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
    
    # Create a custom batch processor that handles parallel processing
    class ParallelBatchProcessor(BatchProcessor):
        def __init__(self, *args, api_key=None, **kwargs):
            super().__init__(*args, **kwargs)
            self.api_key = api_key
            self.current_workers = 5  # Start with 5 workers
            self.timeout_count = 0
            self.total_processed = 0
            self.batch_count = 0
            
        def process_batch_parallel(self, batch: list):
            """Process a batch of files using adaptive parallel processing"""
            self.batch_count += 1
            tool_logger.info(f"⚡ Starting parallel processing for {len(batch)} files (Batch {self.batch_count})")
            
            # Prepare file tasks
            file_tasks = []
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
                
                file_tasks.append((full_path, out_path, self.api_key))
            
            if not file_tasks:
                tool_logger.warning("⚠️ No tasks created for batch")
                return []
            
            # Adaptive worker count based on timeout history
            timeout_rate = self.timeout_count / max(self.total_processed, 1)
            
            if timeout_rate > 0.3 and self.current_workers > 1:  # More than 30% timeouts
                self.current_workers = max(1, self.current_workers - 1)
                tool_logger.warning(f"🔻 High timeout rate ({timeout_rate:.1%}), reducing workers to {self.current_workers}")
            elif timeout_rate < 0.1 and self.current_workers < 5:  # Less than 10% timeouts
                self.current_workers = min(5, self.current_workers + 1)
                tool_logger.info(f"🔺 Low timeout rate ({timeout_rate:.1%}), increasing workers to {self.current_workers}")
            
            # Use adaptive worker count
            max_workers = min(self.current_workers, len(file_tasks))
            tool_logger.info(f"🧵 Using ThreadPoolExecutor with {max_workers} workers (adaptive: {timeout_rate:.1%} timeout rate)")
            
            results = []
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks
                future_to_path = {
                    executor.submit(process_image_sync, full_path, out_path, api_key): full_path
                    for full_path, out_path, api_key in file_tasks
                }
                
                # Collect results as they complete with enhanced error handling
                for future in concurrent.futures.as_completed(future_to_path):
                    file_path = future_to_path[future]
                    try:
                        result = future.result()
                        results.append(result)
                        
                        # Log different types of completion
                        if result.get("timeout"):
                            tool_logger.warning(f"⏰ Timeout (but continuing): {file_path.name}")
                        elif result.get("error"):
                            tool_logger.warning(f"⚠️ Error (but continuing): {file_path.name}")
                        else:
                            tool_logger.info(f"✅ Completed processing: {file_path.name}")
                            
                    except Exception as e:
                        # This should rarely happen now since process_image_sync catches most errors
                        is_timeout = is_timeout_error(e)
                        is_recoverable = is_recoverable_error(e)
                        
                        if is_timeout:
                            tool_logger.error(f"⏰ Thread timeout {file_path.name}: {e}")
                        else:
                            tool_logger.error(f"❌ Thread failed {file_path.name}: {e}")
                            
                        results.append({
                            "error": str(e),
                            "outputs": [str(SegmentHandler.get_relative_path(file_path.with_suffix('.txt')))],
                            "source": str(SegmentHandler.get_relative_path(file_path)),
                            "timeout": is_timeout,
                            "recoverable": is_recoverable,
                            "thread_error": True
                        })
            
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
            
            # Process results with enhanced error categorization and adaptive tracking
            batch_timeout_count = 0
            recoverable_errors = 0
            batch_processed = 0
            
            for result in results:
                if isinstance(result, dict):
                    self.output_proc.save_entry(result)
                    if result.get("error"):
                        if result.get("timeout"):
                            batch_timeout_count += 1
                            self.timeout_count += 1  # Track global timeouts
                            tool_logger.warning(f"⏰ Timeout: {result.get('source', 'unknown')}")
                        elif result.get("recoverable"):
                            recoverable_errors += 1
                        stats["failed"] += 1
                    elif result.get("skipped"):
                        stats["skipped"] += 1
                    elif result.get("success"):
                        stats["processed"] += 1
                        batch_processed += 1
                    else:
                        stats["processed"] += 1  # Default to processed if no clear status
                        batch_processed += 1
                        
                    # Track total processed for adaptive algorithm
                    self.total_processed += 1
            
            # Log batch timeout summary and adaptive adjustments
            if batch_timeout_count > 0:
                batch_timeout_rate = batch_timeout_count / len(results)
                tool_logger.warning(f"⏰ Batch {self.batch_count}: {batch_timeout_count}/{len(results)} files timed out ({batch_timeout_rate:.1%})")
                
                # Immediate adjustment for very high timeout rates in this batch
                if batch_timeout_rate > 0.5 and self.current_workers > 1:
                    old_workers = self.current_workers
                    self.current_workers = max(1, self.current_workers - 1)
                    tool_logger.warning(f"🚨 Emergency reduction: {old_workers} → {self.current_workers} workers due to {batch_timeout_rate:.1%} timeout rate")
                    
            if recoverable_errors > 0:
                tool_logger.info(f"🔄 {recoverable_errors} recoverable errors occurred")
                
            # Log adaptive status
            global_timeout_rate = self.timeout_count / max(self.total_processed, 1)
            tool_logger.info(f"📊 Global stats: {self.timeout_count}/{self.total_processed} timeouts ({global_timeout_rate:.1%}), using {self.current_workers} workers")
                
        def process(self):
            """Override to add timing summary with enhanced error reporting"""
            result = super().process()
            
            # Show overall summary
            total_images = result.get('processed', 0) + result.get('failed', 0) + result.get('skipped', 0)
            
            tool_logger.info("🚀 Parallel Processing Summary:")
            tool_logger.info(f"Total images: {total_images}")
            tool_logger.info(f"✅ Processed: {result.get('processed', 0)}")
            tool_logger.info(f"⏭️ Skipped: {result.get('skipped', 0)}")
            tool_logger.info(f"❌ Failed: {result.get('failed', 0)}")
            
            # Count timeout and recoverable errors from manifest
            if hasattr(self, 'output_proc') and hasattr(self.output_proc, 'manifest_data'):
                timeout_errors = sum(1 for entry in self.output_proc.manifest_data if entry.get('timeout'))
                recoverable_errors = sum(1 for entry in self.output_proc.manifest_data if entry.get('recoverable') and not entry.get('timeout'))
                
                if timeout_errors > 0:
                    tool_logger.warning(f"⏰ Timeout errors: {timeout_errors} (these files can be retried later)")
                if recoverable_errors > 0:
                    tool_logger.info(f"🔄 Other recoverable errors: {recoverable_errors}")
                
                if timeout_errors > 0 or recoverable_errors > 0:
                    tool_logger.info(f"💡 Enhanced timeout handling: Doubled timeout to {API_TIMEOUT}s, increased retries to {MAX_RETRIES}")
                    tool_logger.info(f"💡 Timeout errors are now non-fatal and don't stop batch processing")
                
            return result

    # Use the parallel batch processor
    processor = ParallelBatchProcessor(
        input_manifest=source_manifest,
        output_folder=output_folder,
        process_name="segmented_transcription",
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