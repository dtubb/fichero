from pathlib import Path
from typing import List, Callable, Any, Dict, Optional
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
import logging
from .workflow_progress import StepProgress
import os

logger = logging.getLogger(__name__)

def process_batch(
    files: List[Path],
    process_func: Callable[[Path], Any],
    batch_size: int = 10,
    max_workers: Optional[int] = None,
    progress: Optional[StepProgress] = None
) -> List[Any]:
    """Process a batch of files in parallel.
    
    Args:
        files: List of file paths to process
        process_func: Function to process each file
        batch_size: Number of files to process in each batch
        max_workers: Maximum number of worker processes (defaults to CPU count)
        progress: Optional progress tracker
        
    Returns:
        List of results from processing each file
    """
    if max_workers is None:
        max_workers = mp.cpu_count()
        
    results = []
    processed = 0
    worker_id = os.environ.get('WORKER_ID', '0')
    
    # Process files in batches to avoid memory issues
    for i in range(0, len(files), batch_size):
        batch = files[i:i + batch_size]
        
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(process_func, file): file 
                for file in batch
            }
            
            for future in as_completed(future_to_file):
                file = future_to_file[future]
                try:
                    # Log worker status
                    logger.info(f"Worker {worker_id} processing: {file.name}")
                    result = future.result()
                    results.append(result)
                    logger.info(f"Worker {worker_id} completed: {file.name}")
                except Exception as e:
                    logger.error(f"Worker {worker_id} failed {file.name}: {str(e)}")
                    results.append(None)
                    
                processed += 1
                if progress:
                    progress.update(processed)
                    
    return results

def process_directory(
    directory: Path,
    process_func: Callable[[Path], Any],
    file_pattern: str = "*.jpg",
    batch_size: int = 10,
    max_workers: Optional[int] = None,
    progress: Optional[StepProgress] = None
) -> Dict[Path, Any]:
    """Process all files in a directory in parallel.
    
    Args:
        directory: Directory containing files to process
        process_func: Function to process each file
        file_pattern: Glob pattern to match files
        batch_size: Number of files to process in each batch
        max_workers: Maximum number of worker processes
        progress: Optional progress tracker (only used in main process)
        
    Returns:
        Dictionary mapping file paths to their processing results
    """
    files = list(directory.glob(file_pattern))
    
    # Only use progress tracking in main process
    if os.environ.get('WORKER_ID') is None and progress is not None:
        results = process_batch(
            files,
            process_func,
            batch_size=batch_size,
            max_workers=max_workers,
            progress=progress
        )
    else:
        # Worker process - no progress tracking
        results = process_batch(
            files,
            process_func,
            batch_size=batch_size,
            max_workers=max_workers,
            progress=None
        )
    
    return dict(zip(files, results)) 