"""
Worker Management Utilities for Fichero Processing Scripts

This module provides common utilities for managing worker processes,
GPU memory, and progress tracking across different processing scripts.
"""

import os
import sys
import time
import signal
import subprocess
import threading
from pathlib import Path
import torch
import multiprocessing
from typing import Optional, Callable, Dict, Any, List
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.live import Live
import logging

from scripts.utils.step_manifest import StepManifestManager
from scripts.utils.logging_utils import rich_log, should_show_progress

# Initialize console
console = Console()

def get_best_device() -> str:
    """Determine the best available device for processing."""
    force_cpu = os.environ.get('FICHERO_FORCE_CPU', '0') == '1'
    if force_cpu:
        rich_log("info", "Force CPU mode enabled - using CPU for processing")
        return "cpu"
        
    if torch.backends.mps.is_available() and torch.backends.mps.is_built():
        rich_log("info", "Using MPS (Metal Performance Shaders) for GPU acceleration")
        return "mps"
    elif torch.cuda.is_available():
        rich_log("info", "Using CUDA for GPU acceleration")
        return "cuda"
    else:
        rich_log("info", "Using CPU for processing")
        return "cpu"

def get_worker_device(worker_id: int, device: str) -> str:
    """Get the specific device for a worker based on worker ID."""
    if device == "cuda" and torch.cuda.is_available():
        gpu_count = torch.cuda.device_count()
        if gpu_count > 1:
            # Distribute workers across available GPUs
            gpu_id = worker_id % gpu_count
            rich_log("info", f"Worker {worker_id} using CUDA device {gpu_id}")
            return f"cuda:{gpu_id}"
    elif device == "mps":
        rich_log("info", f"Worker {worker_id} using MPS device")
    else:
        rich_log("info", f"Worker {worker_id} using device: {device}")
    return device

def clear_gpu_memory():
    """Clear GPU memory after processing."""
    device = get_best_device()
    if device == "mps":
        torch.mps.empty_cache()
    elif "cuda" in device:
        torch.cuda.empty_cache()

def run_worker_process(
    manifest_file: Path,
    project_folder: Path,
    step: str,
    process_func: Callable,
    source_prefix: Optional[str] = None,
    output_folder: Optional[Path] = None
) -> None:
    """Run a worker process that processes files from the manifest.
    
    Args:
        manifest_file: Path to the manifest file
        project_folder: Path to the project folder
        step: Name of the processing step
        process_func: Function to process each file
        source_prefix: Optional prefix for source files
        output_folder: Optional output folder path
    """
    # Initialize manifest manager
    manifest = StepManifestManager(manifest_file, step)
    
    # Get batch size from environment
    batch_size = int(os.environ.get('FICHERO_BATCH_SIZE', '1'))
    rich_log("info", f"Worker {os.environ.get('WORKER_ID')} using batch size: {batch_size}")
    
    while True:
        # Get next batch of files to process
        input_paths = manifest.get_next_pending()
        if not input_paths:
            rich_log("info", f"Worker {os.environ.get('WORKER_ID')} no more files to process")
            break
            
        rich_log("info", f"Worker {os.environ.get('WORKER_ID')} processing batch of {len(input_paths)} files")
        
        # Process each file in the batch
        successful_files = []
        failed_files = []
        error_message = None
        results = {}
        
        for input_path in input_paths:
            try:
                # Remove prefix from input_path if present
                if source_prefix and input_path.startswith(source_prefix):
                    input_path = input_path[len(source_prefix):]
                
                # Construct full paths
                if source_prefix:
                    # If source_prefix is provided, use it to construct the full path
                    full_input_path = project_folder / input_path
                else:
                    # Otherwise use the input path as is
                    full_input_path = project_folder / input_path
                
                # Log current file being processed
                rich_log("info", f"Worker {os.environ.get('WORKER_ID')} processing: {input_path}")
                rich_log("info", f"Full input path: {full_input_path}")
                
                # Process the file
                result = process_func(str(full_input_path), output_folder or project_folder)
                
                if result["success"]:
                    successful_files.append(input_path)
                    results[input_path] = {
                        f"{step}_outputs": result.get("outputs", []),
                        f"{step}_details": result.get("details", {})
                    }
                    rich_log("info", f"Worker {os.environ.get('WORKER_ID')} completed: {input_path}")
                    rich_log("info", f"Result: {result}")
                else:
                    error_message = result.get("error", "Unknown error")
                    failed_files.append(input_path)
                    rich_log("error", f"Worker {os.environ.get('WORKER_ID')} failed {input_path}: {error_message}")
            except Exception as e:
                error_message = str(e)
                failed_files.append(input_path)
                rich_log("error", f"Worker {os.environ.get('WORKER_ID')} failed {input_path}: {error_message}")
        
        # Mark successful files as done with their results
        if successful_files:
            for input_path in successful_files:
                manifest.mark_done(input_path, **results[input_path])
            
        # Mark failed files as error
        if failed_files:
            for input_path in failed_files:
                manifest.mark_error(input_path, error_message)

def run_main_process(
    manifest_file: Path,
    project_folder: Path,
    step: str,
    max_workers: Optional[int],
    debug: bool,
    source_folder: Optional[Path] = None,
    output_folder: Optional[Path] = None,
    extra_args: Optional[list] = None
) -> None:
    """Run the main process that spawns and manages workers."""
    # Set debug mode in environment
    os.environ['FICHERO_DEBUG'] = '1' if debug else '0'
    
    # Set up paths
    if output_folder:
        output_folder.mkdir(parents=True, exist_ok=True)
    
    # Use provided max_workers or default to CPU count
    if max_workers is None:
        max_workers = os.cpu_count() - 1 if os.cpu_count() > 1 else 1
    
    # Set worker count in environment for manifest partitioning
    os.environ['FICHERO_WORKER_COUNT'] = str(max_workers)
    rich_log("info", f"Using {max_workers} workers")
    
    # Initialize manifest manager to get total files
    manifest = StepManifestManager(manifest_file, step)
    total_files = len([e for e in manifest.manifest.read_all() 
                      if e.get("type") == "file" and 
                      e.get(f"{step}_status") in [None, "pending", "error"]])
    
    rich_log("info", f"Found {total_files} files to process")
    
    # Initialize progress tracking
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True
    )
    
    # Create tasks for each worker
    worker_tasks = {}
    for worker_id in range(max_workers):
        # Calculate expected files for this worker
        worker_files = total_files // max_workers
        if worker_id < total_files % max_workers:  # Distribute remainder
            worker_files += 1
            
        worker_tasks[worker_id] = progress.add_task(
            f"Worker {worker_id}",
            total=worker_files
        )
    
    # Create and start worker processes
    processes = []
    rich_log("info", "Starting worker processes...")
    for worker_id in range(max_workers):
        env = os.environ.copy()
        env['WORKER_ID'] = str(worker_id)
        env['FICHERO_WORKER'] = '1'
        
        # Find the script in the scripts directory
        script_path = Path(__file__).parent.parent / f"{step}.py"
        if not script_path.exists():
            raise FileNotFoundError(f"Script not found: {script_path}")
        
        # Launch process
        cmd = [sys.executable, str(script_path), str(manifest_file), str(project_folder)]
        if extra_args:
            cmd.extend(extra_args)
        if debug:
            cmd.append('--debug')
        
        rich_log("info", f"Launching worker {worker_id} with command: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        processes.append((worker_id, process))
    
    # Monitor progress and output
    with Live(progress, refresh_per_second=4) as live:
        while processes:
            for worker_id, process in processes[:]:
                # Check if process has finished
                if process.poll() is not None:
                    stdout, stderr = process.communicate()
                    if process.returncode != 0:
                        rich_log("error", f"Worker {worker_id} failed with code {process.returncode}")
                        if stderr:
                            rich_log("error", f"Worker {worker_id} error output: {stderr}")
                        if stdout:
                            rich_log("error", f"Worker {worker_id} output: {stdout}")
                    else:
                        rich_log("info", f"Worker {worker_id} completed successfully")
                        if stdout:
                            for line in stdout.splitlines():
                                if "Completed:" in line:
                                    progress.update(worker_tasks[worker_id], advance=1)
                                rich_log("info", f"Worker {worker_id}: {line}")
                    processes.remove((worker_id, process))
                    continue
                
                # Read output in real-time
                while True:
                    stdout_line = process.stdout.readline()
                    if stdout_line:
                        stdout_line = stdout_line.strip()
                        if "Completed:" in stdout_line:
                            progress.update(worker_tasks[worker_id], advance=1)
                        rich_log("info", f"Worker {worker_id}: {stdout_line}")
                        sys.stdout.flush()  # Force flush output
                    else:
                        break
                
                # Read error in real-time
                while True:
                    stderr_line = process.stderr.readline()
                    if stderr_line:
                        stderr_line = stderr_line.strip()
                        rich_log("error", f"Worker {worker_id}: {stderr_line}")
                        sys.stderr.flush()  # Force flush error output
                    else:
                        break
            
            time.sleep(0.1)
    
    rich_log("info", "All workers finished")

class WorkerManager:
    """Manages worker processes with proper error handling and logging."""
    
    def __init__(self, max_workers: int = 4, timeout: int = 300):
        """
        Initialize WorkerManager.
        
        Args:
            max_workers: Maximum number of concurrent workers
            timeout: Timeout in seconds for worker processes
        """
        self.max_workers = max_workers
        self.timeout = timeout
        self.active_workers: Dict[int, subprocess.Popen] = {}
        self.worker_outputs: Dict[int, List[str]] = {}
        self._lock = threading.Lock()

    def _handle_worker_output(self, worker_id: int, process: subprocess.Popen):
        """
        Handle output from a worker process.
        
        Args:
            worker_id: ID of the worker
            process: Process object
        """
        try:
            if process.stdout:
                for line in iter(process.stdout.readline, b''):
                    if line:
                        output = line.decode('utf-8').strip()
                        with self._lock:
                            if worker_id not in self.worker_outputs:
                                self.worker_outputs[worker_id] = []
                            self.worker_outputs[worker_id].append(output)
                            # Force flush the output
                            sys.stdout.flush()
                            rich_log("debug", f"Worker {worker_id}: {output}")
                            # Force flush the logging output
                            logging.getLogger().handlers[0].flush()
        except Exception as e:
            rich_log("error", f"Error handling worker {worker_id} output: {str(e)}")

    def _cleanup_worker(self, worker_id: int):
        """
        Clean up resources for a worker.
        
        Args:
            worker_id: ID of the worker to clean up
        """
        with self._lock:
            if worker_id in self.active_workers:
                del self.active_workers[worker_id]
            if worker_id in self.worker_outputs:
                del self.worker_outputs[worker_id]

    def start_worker(self, command: List[str], worker_id: int) -> bool:
        """
        Start a new worker process.
        
        Args:
            command: Command to run
            worker_id: ID for the worker
            
        Returns:
            bool: True if worker started successfully
        """
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            with self._lock:
                self.active_workers[worker_id] = process
                self.worker_outputs[worker_id] = []
            
            # Start output handling thread
            thread = threading.Thread(
                target=self._handle_worker_output,
                args=(worker_id, process),
                daemon=True
            )
            thread.start()
            
            rich_log("info", f"Started worker {worker_id}")
            return True
            
        except Exception as e:
            rich_log("error", f"Error starting worker {worker_id}: {str(e)}")
            self._cleanup_worker(worker_id)
            return False

    def stop_worker(self, worker_id: int, force: bool = False) -> bool:
        """
        Stop a worker process.
        
        Args:
            worker_id: ID of the worker to stop
            force: Whether to force kill the process
            
        Returns:
            bool: True if worker was stopped successfully
        """
        try:
            with self._lock:
                if worker_id not in self.active_workers:
                    rich_log("warning", f"Worker {worker_id} not found")
                    return False
                    
                process = self.active_workers[worker_id]
                
            if force:
                process.kill()
            else:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            
            self._cleanup_worker(worker_id)
            rich_log("info", f"Stopped worker {worker_id}")
            return True
            
        except Exception as e:
            rich_log("error", f"Error stopping worker {worker_id}: {str(e)}")
            return False

    def stop_all_workers(self, force: bool = False) -> bool:
        """
        Stop all active workers.
        
        Args:
            force: Whether to force kill the processes
            
        Returns:
            bool: True if all workers were stopped successfully
        """
        success = True
        with self._lock:
            worker_ids = list(self.active_workers.keys())
            
        for worker_id in worker_ids:
            if not self.stop_worker(worker_id, force):
                success = False
                
        return success

    def get_worker_status(self, worker_id: int) -> Optional[Dict[str, Any]]:
        """
        Get status information for a worker.
        
        Args:
            worker_id: ID of the worker
            
        Returns:
            Optional[Dict[str, Any]]: Status information or None if worker not found
        """
        try:
            with self._lock:
                if worker_id not in self.active_workers:
                    return None
                    
                process = self.active_workers[worker_id]
                return {
                    "pid": process.pid,
                    "returncode": process.returncode,
                    "running": process.poll() is None,
                    "output": self.worker_outputs.get(worker_id, [])
                }
        except Exception as e:
            rich_log("error", f"Error getting status for worker {worker_id}: {str(e)}")
            return None

    def get_active_workers(self) -> List[int]:
        """
        Get list of active worker IDs.
        
        Returns:
            List[int]: List of active worker IDs
        """
        with self._lock:
            return list(self.active_workers.keys())

    def wait_for_worker(self, worker_id: int, timeout: Optional[int] = None) -> bool:
        """
        Wait for a worker to complete.
        
        Args:
            worker_id: ID of the worker to wait for
            timeout: Timeout in seconds (None for no timeout)
            
        Returns:
            bool: True if worker completed successfully
        """
        try:
            with self._lock:
                if worker_id not in self.active_workers:
                    rich_log("warning", f"Worker {worker_id} not found")
                    return False
                    
                process = self.active_workers[worker_id]
            
            try:
                process.wait(timeout=timeout)
                success = process.returncode == 0
                if success:
                    rich_log("info", f"Worker {worker_id} completed successfully")
                else:
                    rich_log("error", f"Worker {worker_id} failed with return code {process.returncode}")
                return success
            except subprocess.TimeoutExpired:
                rich_log("error", f"Worker {worker_id} timed out")
                return False
                
        except Exception as e:
            rich_log("error", f"Error waiting for worker {worker_id}: {str(e)}")
            return False

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop_all_workers() 