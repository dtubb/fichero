"""
Parallel Batch Processor Utility

Creates parallel-enabled BatchProcessor classes that tools can use.
Follows the pattern from transcribe_qwen_max.py but with backend-driven parallel decisions.
"""

import concurrent.futures
import time
from pathlib import Path
from typing import Callable

try:
    from fichero.tools.utils.tool_logger import get_tool_logger
except ImportError:
    from utils.tool_logger import get_tool_logger

logger = get_tool_logger('parallel_batch_processor')


def create_parallel_batch_processor(tool_name: str, base_batch_processor_class, process_image_fn: Callable):
    """
    Factory function to create a parallel-enabled BatchProcessor for image tools.
    
    Args:
        tool_name: Name of the tool (for logging)
        base_batch_processor_class: The BatchProcessor class to extend  
        process_image_fn: Function to process individual images (file_path, out_path, output_format) -> dict
        
    Returns:
        Parallel-enabled BatchProcessor class
    """
    
    class ParallelBatchProcessor(base_batch_processor_class):
        def __init__(self, *args, output_format="jpg", parallel_workers=1, **kwargs):
            super().__init__(*args, **kwargs)
            self.output_format = output_format
            self.parallel_workers = parallel_workers
            self.tool_name = tool_name
            
        def _process_batch(self, batch: list, stats: dict):
            """Override to use parallel processing when instructed by workflow executor"""
            batch_start = time.time()
            
            # Use parallel workers as determined by workflow executor
            if self.parallel_workers <= 1:
                logger.info(f"[{self.tool_name}] 🔄 Using sequential processing (parallel_workers={self.parallel_workers})")
                # Use original sequential processing
                super()._process_batch(batch, stats)
                return
            
            workers = min(self.parallel_workers, len(batch))
            logger.info(f"[{self.tool_name}] ⚡ Using parallel processing with {workers} workers (from workflow executor)")
            
            # Prepare file tasks for parallel processing
            file_tasks = []
            for doc in batch:
                path = Path(doc["path"])
                
                # Use base folder directly with documents/ prefix for _staging
                # For external collections, use direct path without adding documents/
                if self.base_folder:
                    base_str = str(self.base_folder)
                    # Only add documents/ if processing from _staging (internal collection)
                    if "_staging" in base_str and "documents" not in base_str.lower():
                        full_path = self.base_folder / "documents" / path
                    else:
                        # External collection or already in documents/ - use direct path
                        full_path = self.base_folder / path
                else:
                    full_path = path
                
                # Create output path - only add documents/ for _staging workflows
                parts = path.parts
                if 'documents' in parts:
                    rel_path = Path(*parts[parts.index('documents') + 1:])
                else:
                    rel_path = path

                # Only add documents/ subdirectory if source is from _staging (internal workflow)
                if "_staging" in base_str and "documents" not in base_str.lower():
                    out_path = self.output_folder / "documents" / rel_path
                else:
                    # External collection or processing from assets - no documents/ subdirectory
                    out_path = self.output_folder / rel_path
                
                file_tasks.append((full_path, out_path))
            
            if not file_tasks:
                logger.warning(f"[{self.tool_name}] ⚠️ No tasks created for batch")
                return
            
            logger.info(f"[{self.tool_name}] 🧵 Using ThreadPoolExecutor with {workers} workers")

            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                    # Submit all tasks
                    future_to_path = {}
                    for full_path, out_path in file_tasks:
                        try:
                            future = executor.submit(process_image_fn, full_path, out_path, self.output_format)
                            future_to_path[future] = full_path
                        except RuntimeError as e:
                            if "shutdown" in str(e):
                                logger.warning(f"[{self.tool_name}] ⚠️ Executor shutting down, processing {full_path.name} sequentially")
                                # Process this file sequentially as fallback
                                try:
                                    result = process_image_fn(full_path, out_path, self.output_format)
                                    if isinstance(result, dict):
                                        self.output_proc.save_entry(result)
                                        if result.get("error"):
                                            stats["failed"] += 1
                                        else:
                                            stats["processed"] += 1
                                except Exception as seq_e:
                                    logger.error(f"[{self.tool_name}] ❌ Sequential fallback failed for {full_path.name}: {seq_e}")
                                    error_result = {
                                        "error": str(seq_e),
                                        "outputs": [],
                                        "source": str(full_path)
                                    }
                                    self.output_proc.save_entry(error_result)
                                    stats["failed"] += 1
                            else:
                                raise
                
                # Collect results as they complete
                for future in concurrent.futures.as_completed(future_to_path):
                    file_path = future_to_path[future]
                    try:
                        result = future.result()
                        
                        # Process result using original BatchProcessor logic
                        if isinstance(result, dict):
                            self.output_proc.save_entry(result)
                            if result.get("error"):
                                stats["failed"] += 1
                            else:
                                stats["processed"] += 1
                        
                        logger.info(f"[{self.tool_name}] ✅ Completed processing: {file_path.name}")
                        
                    except Exception as e:
                        logger.error(f"[{self.tool_name}] ❌ Failed processing {file_path.name}: {e}")
                        # Create error result and save it
                        error_result = {
                            "error": str(e),
                            "outputs": [],
                            "source": str(file_path)
                        }
                        self.output_proc.save_entry(error_result)
                        stats["failed"] += 1

            except RuntimeError as e:
                if "shutdown" in str(e):
                    logger.warning(f"[{self.tool_name}] ⚠️ Executor error during processing: {e}")
                    logger.info(f"[{self.tool_name}] Falling back to sequential processing for remaining tasks...")
                    # Process any remaining tasks sequentially
                    for full_path, out_path in file_tasks:
                        try:
                            result = process_image_fn(full_path, out_path, self.output_format)
                            if isinstance(result, dict):
                                self.output_proc.save_entry(result)
                                if result.get("error"):
                                    stats["failed"] += 1
                                else:
                                    stats["processed"] += 1
                                logger.info(f"[{self.tool_name}] ✅ Completed processing: {full_path.name}")
                        except Exception as seq_e:
                            logger.error(f"[{self.tool_name}] ❌ Failed processing {full_path.name}: {seq_e}")
                            error_result = {
                                "error": str(seq_e),
                                "outputs": [],
                                "source": str(full_path)
                            }
                            self.output_proc.save_entry(error_result)
                            stats["failed"] += 1
                else:
                    raise

            batch_time = time.time() - batch_start
            logger.info(f"[{self.tool_name}] Batch of {len(file_tasks)} images processed in {batch_time:.1f}s")
    
    return ParallelBatchProcessor 