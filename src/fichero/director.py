import typer
import yaml
import os
import shutil
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import subprocess
from typing import List, Optional, Dict
import logging
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn
import platform
import signal
import sys
import psutil
import multiprocessing
from datetime import datetime
from rich.console import Console
from rich.live import Live
from rich.table import Table
import time
import concurrent.futures
import json
import shlex
import re
from celery import Celery
from celery.result import AsyncResult
import tempfile
from pathvalidate import sanitize_filename as pv_sanitize_filename, sanitize_filepath as pv_sanitize_filepath
import redis
import asyncio

def get_celery_module_name() -> str:
    """
    Get the correct module name for Celery based on the runtime environment.
    When running under briefcase dev, use the full module path.
    """
    # Check if we're running as a module (under briefcase dev)
    if __name__ != '__main__':
        return 'fichero.director'
    else:
        return 'fichero_director'

# Set up Celery
celery_app = Celery('fichero_director',
             broker='redis://localhost:6379/0',
             backend='redis://localhost:6379/0')

# Configure Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=14400,  # 4 hour timeout for large folders
    
    # Optimize for M1 MacBook
    worker_concurrency=8,  # Leave 2 cores for system
    worker_max_memory_per_child=2048,  # 2GB per worker
    worker_max_tasks_per_child=10,  # Restart after 10 tasks to prevent memory leaks
    worker_prefetch_multiplier=1,  # Process one task at a time
    
    # Task routing
    task_routes={
        'process_folder': {
            'queue': 'cpu_intensive',
            'routing_key': 'cpu_intensive'
        }
    },
    
    # Queue settings
    task_queues={
        'cpu_intensive': {
            'exchange': 'cpu_intensive',
            'routing_key': 'cpu_intensive',
            'queue_arguments': {
                'x-max-priority': 10
            }
        },
        'io_intensive': {
            'exchange': 'io_intensive',
            'routing_key': 'io_intensive',
            'queue_arguments': {
                'x-max-priority': 10
            }
        }
    },
    
    # Task priority
    task_default_priority=5,
    task_queue_max_priority=10,
    
    # Result backend settings
    result_expires=14400,  # Results expire after 4 hours
    result_backend_transport_options={
        'retry_policy': {
            'timeout': 5.0
        }
    },
    
    # Broker settings
    broker_transport_options={
        'visibility_timeout': 14400,  # 4 hours - must match task_time_limit
        'fanout_prefix': True,
        'fanout_patterns': True
    }
)

# Set up rich logging for better console output
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, markup=True)]
)
log = logging.getLogger("fichero_director")

# Global executor for cleanup
executor = None
current_processes = set()  # Track processes started by this instance
instance_pid = os.getpid()  # Track this instance's PID
# Track worker assignments and status
worker_assignments = {}
folder_status = {}      # folder_name -> status
folder_start_times = {} # folder_name -> start_time
folder_completion_times = {} # folder_name -> completion_time
active_task_ids = set()  # Track all submitted task IDs for cleanup

# Define CPU-intensive and I/O-intensive scripts
CPU_INTENSIVE_SCRIPTS = {
    'crop.py', 'enhance.py', 'remove_background.py', 'rotate.py', 'segment.py',
    'split.py', 'build_documents_manifest.py'  # Image processing and initial setup
}

IO_INTENSIVE_SCRIPTS = {
    'fuzzy_clean.py', 'llm_process.py',
    'transcribe_qwen_max.py', 'transcribe_lmstudio.py', 'transcribe_qwen_2b.py', 'transcribe_qwen_7b.py',
    'recombine_segments.py', 'convert_to_word.py', 'json_to_word.py'  # File I/O and API calls
}

# Define script dependencies
SCRIPT_DEPENDENCIES = {
    'enhance.py': ['crop.py'],
    'segment.py': ['enhance.py'],
    'split.py': ['segment.py'],
    'transcribe_qwen_max.py': ['split.py'],
    'transcribe_lmstudio.py': ['split.py'],
    'transcribe_qwen_2b.py': ['split.py'],
    'transcribe_qwen_7b.py': ['split.py'],
    'recombine_segments.py': ['transcribe_qwen_max.py', 'transcribe_lmstudio.py', 'transcribe_qwen_2b.py', 'transcribe_qwen_7b.py'],
    'llm_process.py': ['recombine_segments.py'],
    'fuzzy_clean.py': ['llm_process.py'],
    'convert_to_word.py': ['fuzzy_clean.py']
}

def get_queue_for_script(script_name: str) -> str:
    """Determine which queue a script should be routed to"""
    script_name = script_name.lower()
    if any(cpu_script in script_name for cpu_script in CPU_INTENSIVE_SCRIPTS):
        return 'cpu_intensive'
    elif any(io_script in script_name for io_script in IO_INTENSIVE_SCRIPTS):
        return 'io_intensive'
    return 'cpu_intensive'  # Default to CPU intensive if unknown

def get_worker_logger(folder_path: Path) -> logging.Logger:
    """Create a logger for a specific worker process that writes to a file"""
    worker_id = multiprocessing.current_process().name
    folder_name = folder_path.name
    
    # Extract the worker number from the process name
    # ProcessPoolExecutor-1 -> 1
    worker_num = worker_id.split("-")[-1] if "-" in worker_id else worker_id
    worker_id = f"Worker {worker_num}"
    
    # Create logs directory in the folder being processed
    log_dir = folder_path / "logs"
    log_dir.mkdir(exist_ok=True)
    
    # Create log file with timestamp in the folder's logs directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"processing_{timestamp}.log"
    
    # Create logger
    logger = logging.getLogger(f"worker-{worker_id}-{folder_name}")
    logger.setLevel(logging.INFO)
    
    # Clear any existing handlers
    logger.handlers = []
    
    # Add file handler - writing to the folder's logs directory
    file_handler = logging.FileHandler(log_file)
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # Disable propagation to root logger to prevent console output
    logger.propagate = False
    
    # Update status to Processing when worker starts
    update_status(folder_name, worker_id, "Processing")
    
    return logger

def get_worker_concurrency():
    """Get the concurrency settings for each worker type"""
    from celery.app.control import Control
    control = Control(celery_app)
    
    # Get worker stats and active queues
    stats = control.inspect().stats()
    active_queues = control.inspect().active_queues()
    
    if not stats:
        return {'cpu_intensive': 4, 'io_intensive': 4}  # Default fallback
    
    # Parse worker concurrency based on queue assignments
    concurrency = {'cpu_intensive': 0, 'io_intensive': 0}
    
    for worker, info in stats.items():
        max_conc = info.get('pool', {}).get('max-concurrency', 4)
        
        # Check which queues this worker is handling
        if active_queues and worker in active_queues:
            worker_queues = active_queues[worker]
            for queue_info in worker_queues:
                queue_name = queue_info.get('name', '')
                if 'cpu_intensive' in queue_name:
                    concurrency['cpu_intensive'] += max_conc
                elif 'io_intensive' in queue_name:
                    concurrency['io_intensive'] += max_conc
        else:
            # Fallback: check worker name patterns
            if 'cpu_worker' in worker or 'worker1' in worker:
                concurrency['cpu_intensive'] += max_conc
            elif 'io_worker' in worker or 'worker2' in worker:
                concurrency['io_intensive'] += max_conc
    
    # If no workers found, use defaults
    if concurrency['cpu_intensive'] == 0:
        concurrency['cpu_intensive'] = 4
    if concurrency['io_intensive'] == 0:
        concurrency['io_intensive'] = 4
        
    log.info(f"Detected worker concurrency: CPU={concurrency['cpu_intensive']}, IO={concurrency['io_intensive']}")
    return concurrency

def update_status(folder_name: str, worker_id: str, status: str, step: str = None, error: str = None):
    """Update the status of a folder"""
    # Extract queue name from worker_id if it's in the format "worker_name (queue_name)"
    queue_name = "unknown"
    if "(" in worker_id and ")" in worker_id:
        queue_name = worker_id.split("(")[1].split(")")[0]
    elif worker_id in ["CPU", "I/O"]:
        queue_name = "cpu_intensive" if worker_id == "CPU" else "io_intensive"
    elif worker_id == "Waiting":
        queue_name = "waiting"
    elif worker_id == "Completed":
        queue_name = "completed"
    elif worker_id == "Failed":
        queue_name = "failed"
    elif worker_id == "Waiting I/O":
        queue_name = "waiting_io"
    
    # Update worker assignment and status
    worker_assignments[folder_name] = queue_name
    folder_status[folder_name] = status
    
    # Update step and error if provided
    if step:
        folder_status[f"{folder_name}_step"] = step
    if error:
        folder_status[f"{folder_name}_error"] = error
    
    # Track timing
    current_time = time.time()
    if status in ["Processing", "Starting"] and folder_name not in folder_start_times:
        folder_start_times[folder_name] = current_time
    elif status in ["Completed", "Failed"]:
        if folder_name not in folder_completion_times:
            folder_completion_times[folder_name] = current_time
        # Calculate total processing time
        if folder_name in folder_start_times:
            processing_time = current_time - folder_start_times[folder_name]
            folder_status[f"{folder_name}_total_time"] = processing_time

def format_time(seconds: float) -> str:
    """Format time in seconds to a human readable string"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"

def create_status_table() -> Table:
    """Create a table showing progress for each worker"""
    # Get unique folders and their latest status
    unique_folders = {}
    for folder_name, status in folder_status.items():
        # Skip step, error, and time entries
        if "_step" in folder_name or "_error" in folder_name or "_total_time" in folder_name:
            continue
        unique_folders[folder_name] = status
    
    # Calculate task counts
    total_tasks = len(unique_folders)
    # Only count as active if actually processing (not waiting for IO)
    active_cpu = sum(1 for folder, status in unique_folders.items() 
                    if status in ["Processing", "Starting"] and worker_assignments.get(folder) == "cpu_intensive")
    active_io = sum(1 for folder, status in unique_folders.items() 
                   if status in ["Processing", "Starting"] and worker_assignments.get(folder) == "io_intensive")
    # Count all waiting statuses including waiting for IO
    waiting_tasks = sum(1 for folder, status in unique_folders.items() 
                       if status == "Waiting" or worker_assignments.get(folder) in ["waiting", "waiting_io"])
    completed_tasks = sum(1 for folder, status in unique_folders.items() 
                         if status == "Completed")
    failed_tasks = sum(1 for folder, status in unique_folders.items() 
                      if status == "Failed")
    
    # Calculate total running time
    current_time = time.time()
    total_running_time = 0
    for folder_name, status in unique_folders.items():
        if status in ["Processing", "Starting"] and folder_name in folder_start_times:
            total_running_time += current_time - folder_start_times[folder_name]
    
    # Create title with task counts and total running time
    title = f"Tasks: {total_tasks} | Active: {active_cpu + active_io} (CPU: {active_cpu}, I/O: {active_io}) | Waiting: {waiting_tasks} | Completed: {completed_tasks} | Failed: {failed_tasks} | Running Time: {format_time(total_running_time)}"
    
    table = Table(
        title=title,
        show_header=True,
        header_style="bold magenta",
        border_style="blue"
    )
    table.add_column("#", style="dim", width=3)
    table.add_column("Worker", style="cyan", width=12)
    table.add_column("Folder", style="green", width=35, no_wrap=True)
    table.add_column("Progress", style="yellow", width=50, no_wrap=True)
    table.add_column("Time", style="blue", width=8)
    
    # Define status priority (lower number = higher priority)
    status_priority = {
        "Failed": 0,     # Highest priority - show at top
        "Processing": 1, # Second priority
        "Starting": 2,
        "Waiting": 3,
        "Completed": 999 # Always at the bottom
    }
    
    # Sort folders by status priority first, then by queue type, then by name
    def get_folder_priority(folder_name):
        status = unique_folders.get(folder_name, "Waiting")
        queue = worker_assignments.get(folder_name, "unknown")
        
        # Define queue priority (CPU > IO > unknown)
        queue_priority = {
            "cpu_intensive": 0,
            "io_intensive": 1,
            "waiting": 2,
            "unknown": 3
        }
        
        # For processing tasks, sort by queue first
        if status in ["Processing", "Starting"]:
            return (1, queue_priority.get(queue, 3), folder_name.lower())
        # For failed tasks, always at top
        elif status == "Failed":
            return (0, folder_name.lower())
        # For other statuses, sort by status priority
        return (status_priority.get(status, 999), folder_name.lower())
    
    # Sort all folders by priority
    sorted_folders = sorted(unique_folders.keys(), key=get_folder_priority)
    
    # Add rows with task numbers
    for idx, folder_name in enumerate(sorted_folders, 1):
        queue_name = worker_assignments.get(folder_name, "unknown")
        status = unique_folders[folder_name]
        
        # Skip completed tasks that are older than 60 seconds
        if status == "Completed":
            if folder_name in folder_completion_times:
                completion_time = folder_completion_times[folder_name]
                if current_time - completion_time > 60:  # 60 seconds
                    continue
        
        # Skip folders that somehow don't have a valid status
        if not status:
            continue
        
        # Calculate time spent
        time_spent = ""
        if status in ["Processing", "Starting"] and folder_name in folder_start_times:
            elapsed = current_time - folder_start_times[folder_name]
            time_spent = format_time(elapsed)
        elif status == "Waiting" and folder_name in folder_start_times:
            # For folders waiting for I/O, show time since original start
            elapsed = current_time - folder_start_times[folder_name]
            time_spent = format_time(elapsed)
        elif status == "Completed" and f"{folder_name}_total_time" in folder_status:
            total_time = folder_status[f"{folder_name}_total_time"]
            time_spent = format_time(total_time)
        
        # Get current step if available
        current_step = folder_status.get(f"{folder_name}_step", "")
        if current_step:
            # Clean up step name
            current_step = current_step.replace("Running step: ", "").replace("Running ", "").replace("Processing ", "")
            
        # Add warning for long-running tasks
        long_running_threshold = 600  # 10 minutes for warning
        very_long_threshold = 1800  # 30 minutes for severe warning
        if status in ["Processing", "Starting", "Waiting"] and folder_name in folder_start_times:
            elapsed = current_time - folder_start_times[folder_name]
            if elapsed > very_long_threshold:
                current_step = f"{current_step} 🔥 (very long: {format_time(elapsed)})"
            elif elapsed > long_running_threshold:
                current_step = f"{current_step} ⚠️ (long: {format_time(elapsed)})"
        
        # Create progress display with appropriate colors and actual status
        if status == "Failed":
            # Extract error message if available
            error_msg = folder_status.get(f"{folder_name}_error", "Unknown error")
            progress = f"[red]✗[/red] {error_msg}"
            row_style = "red"
            worker_display = "[red]Failed[/red]"
        elif status == "Completed":
            progress = "[green]✓[/green] Completed"
            row_style = "green"
            worker_display = "[green]Done[/green]"
        elif status in ["Processing", "Starting"]:
            # Active task - show with spinner
            spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            frame = spinner_frames[int(current_time * 2) % len(spinner_frames)]
            
            if current_step:
                progress = f"[yellow]{frame}[/yellow] {current_step}"
            else:
                progress = f"[yellow]{frame}[/yellow] {status}"
            
            # Determine row style and worker display based on queue
            if queue_name == "cpu_intensive":
                row_style = "purple"
                worker_display = "[purple]CPU[/purple]"
            elif queue_name == "io_intensive":
                row_style = "orange3"
                worker_display = "[orange3]I/O[/orange3]"
            else:
                row_style = "yellow"
                worker_display = "[yellow]Active[/yellow]"
        else:  # Waiting
            # Check if this is waiting for IO queue after CPU completion
            if current_step and "I/O queue" in current_step:
                progress = f"⏳ {current_step}"
                row_style = "cyan"
                worker_display = "[cyan]Wait I/O[/cyan]"
            else:
                progress = "⏳ Waiting to start..."
                row_style = "dim"
                worker_display = "[dim]Waiting[/dim]"
        
        # Add the row with appropriate styling
        table.add_row(
            str(idx), 
            worker_display, 
            f"[{row_style}]{folder_name}[/{row_style}]", 
            progress, 
            f"[{row_style}]{time_spent}[/{row_style}]"
        )
    
    return table

def kill_process_tree(pid):
    """Kill a process and all its children"""
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in children:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        try:
            parent.kill()
        except psutil.NoSuchProcess:
            pass
    except psutil.NoSuchProcess:
        pass

def kill_all_python_processes():
    """Kill all Python processes except the current one"""
    current_pid = os.getpid()
    killed_pids = set()
    
    # First pass: kill processes running our scripts
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # Skip the current process
            if proc.pid == current_pid:
                continue
                
            # Check if it's a Python process
            if 'python' in proc.name().lower():
                # Check if it's one of our scripts
                cmdline = ' '.join(proc.cmdline()).lower()
                if any(script in cmdline for script in CPU_INTENSIVE_SCRIPTS | IO_INTENSIVE_SCRIPTS):
                    log.info(f"Killing Python process: {proc.pid} ({cmdline})")
                    kill_process_tree(proc.pid)
                    killed_pids.add(proc.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    # Second pass: kill any remaining Python processes that might be related
    # This catches processes that might have been started by our scripts
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.pid == current_pid or proc.pid in killed_pids:
                continue
                
            if 'python' in proc.name().lower():
                cmdline = ' '.join(proc.cmdline()).lower()
                # Check for common patterns in our scripts
                if any(pattern in cmdline for pattern in [
                    'fichero', 'weasel', 'celery', 'worker',
                    'process', 'crop', 'enhance', 'transcribe'
                ]):
                    log.info(f"Killing related Python process: {proc.pid} ({cmdline})")
                    kill_process_tree(proc.pid)
                    killed_pids.add(proc.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    # Wait a moment for processes to die
    time.sleep(1)
    
    # Final pass: force kill any remaining Python processes that match our patterns
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.pid == current_pid or proc.pid in killed_pids:
                continue
                
            if 'python' in proc.name().lower():
                cmdline = ' '.join(proc.cmdline()).lower()
                if any(pattern in cmdline for pattern in [
                    'fichero', 'weasel', 'celery', 'worker',
                    'process', 'crop', 'enhance', 'transcribe'
                ]):
                    log.info(f"Force killing Python process: {proc.pid} ({cmdline})")
                    try:
                        proc.kill()
                    except psutil.NoSuchProcess:
                        pass
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

def kill_celery_workers():
    """Kill all Celery worker processes"""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = ' '.join(proc.cmdline()).lower()
            if 'celery' in cmdline and 'worker' in cmdline:
                log.info(f"Killing Celery worker: {proc.pid}")
                kill_process_tree(proc.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

def purge_celery_tasks():
    """Purge all pending tasks from Celery queues"""
    try:
        from celery.app.control import Control
        control = Control(celery_app)
        
        # Revoke all tracked task IDs first
        if active_task_ids:
            log.info(f"Revoking {len(active_task_ids)} tracked tasks...")
            for task_id in active_task_ids:
                celery_app.control.revoke(task_id, terminate=True)
            active_task_ids.clear()
        
        # Purge all tasks from all queues
        log.info("Purging all pending Celery tasks...")
        celery_app.control.purge()
        
        # Also revoke any active tasks that might not be tracked
        inspect = control.inspect()
        active_tasks = inspect.active()
        
        if active_tasks:
            for worker, tasks in active_tasks.items():
                for task in tasks:
                    task_id = task.get('id')
                    if task_id:
                        celery_app.control.revoke(task_id, terminate=True)
                        log.info(f"Revoked active task {task_id}")
        
        # Clear scheduled tasks too
        scheduled = inspect.scheduled()
        if scheduled:
            for worker, tasks in scheduled.items():
                for task in tasks:
                    task_id = task.get('id')
                    if task_id:
                        celery_app.control.revoke(task_id, terminate=True)
                        log.info(f"Revoked scheduled task {task_id}")
        
        # Clear reserved tasks
        reserved = inspect.reserved()
        if reserved:
            for worker, tasks in reserved.items():
                for task in tasks:
                    task_id = task.get('id')
                    if task_id:
                        celery_app.control.revoke(task_id, terminate=True)
                        log.info(f"Revoked reserved task {task_id}")
        
        log.info("All Celery tasks purged and revoked")
    except Exception as e:
        log.error(f"Error purging Celery tasks: {e}")

def signal_handler(signum, frame):
    """Handle interrupt signals by cleaning up only processes started by this instance"""
    log.info("\nReceived interrupt signal. Cleaning up processes started by this instance...")
    
    try:
        # Only kill Python processes started by this instance
        for pid in current_processes:
            try:
                proc = psutil.Process(pid)
                # Verify this is a process we started
                if proc.ppid() == instance_pid or pid in current_processes:
                    log.info(f"Killing process started by this instance: {pid}")
                    kill_process_tree(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        # Only purge tasks submitted by this instance
        if active_task_ids:
            log.info(f"Revoking {len(active_task_ids)} tracked tasks...")
            for task_id in active_task_ids:
                celery_app.control.revoke(task_id, terminate=True)
            active_task_ids.clear()
        
        # Shutdown executor if it exists
        if executor:
            executor.shutdown(wait=False, cancel_futures=True)
        
        # Clear status tracking for this instance
        worker_assignments.clear()
        folder_status.clear()
        folder_start_times.clear()
        folder_completion_times.clear()
        
        log.info("Cleanup complete. Exiting...")
        # Use sys.exit instead of os._exit for cleaner shutdown
        sys.exit(0)
    except Exception as e:
        log.error(f"Error during cleanup: {e}")
        # Force exit if cleanup fails
        os._exit(1)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Initialize Typer CLI app
cli = typer.Typer()

def is_apfs(path: Path) -> bool:
    """
    Check if the given path is on an APFS filesystem.
    This is important for macOS systems where we can use fast APFS cloning.
    
    Args:
        path: Path to check
        
    Returns:
        bool: True if path is on APFS filesystem, False otherwise
    """
    if platform.system() != "Darwin":  # Not macOS
        return False
    try:
        # Log the path we're checking
        log.info(f"Checking if path is APFS: {path}")
        # Use df command to check filesystem type
        result = subprocess.run(
            ["df", "-t", "apfs", str(path)],  # Changed from -T to -t apfs
            capture_output=True,
            text=True
        )
        is_apfs = result.returncode == 0  # If command succeeds, it's APFS
        log.info(f"Path {path} is APFS: {is_apfs}")
        return is_apfs
    except Exception as e:
        log.error(f"Error checking APFS: {e}")
        return False

def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename using pathvalidate library.
    Preserves Unicode characters but replaces problematic characters with hyphens.
    Problematic characters include:
    - Special characters: , ; { } $ & . 
    - Invalid filesystem characters: / \\ : * ? " < > |
    - Other problematic characters: # @ ! ~ ` ^ + = [ ] ( ) { }
    Preserves the file extension.
    """
    # Split into name and extension
    name, ext = os.path.splitext(filename)
    
    # First replace all problematic characters with hyphens
    name = (name.replace(',', '-')
                .replace(';', '-')
                .replace('{', '-')
                .replace('}', '-')
                .replace(' ', '-')
                .replace('$', '-')
                .replace('&', '-')
                # Filesystem invalid characters
                .replace('/', '-')
                .replace('\\', '-')
                .replace(':', '-')
                .replace('*', '-')
                .replace('?', '-')
                .replace('"', '-')
                .replace('<', '-')
                .replace('>', '-')
                .replace('|', '-')
                # Other problematic characters
                .replace('#', '-')
                .replace('@', '-')
                .replace('!', '-')
                .replace('~', '-')
                .replace('`', '-')
                .replace('^', '-')
                .replace('+', '-')
                .replace('=', '-')
                .replace('[', '-')
                .replace(']', '-')
                .replace('(', '-')
                .replace(')', '-'))
    
    # Use pathvalidate to sanitize the name
    sanitized = pv_sanitize_filename(name)
    
    # Replace any remaining periods with hyphens
    sanitized = sanitized.replace('.', '-')
    
    # Remove multiple consecutive hyphens
    sanitized = re.sub(r'-+', '-', sanitized)
    
    # Remove leading/trailing hyphens
    sanitized = sanitized.strip('-')
    
    # Recombine with extension
    final_name = sanitized + ext
    log.info(f"Sanitized filename: {filename} -> {final_name}")
    
    return final_name

def sanitize_path(path: str) -> str:
    """
    Sanitize a path using pathvalidate library.
    Preserves Unicode characters but replaces problematic characters with hyphens.
    Problematic characters include:
    - Special characters: , ; { } $ & . 
    - Invalid filesystem characters: / \\ : * ? " < > |
    - Other problematic characters: # @ ! ~ ` ^ + = [ ] ( ) { }
    """
    # First replace all problematic characters with hyphens
    path = (path.replace(',', '-')
                .replace(';', '-')
                .replace('{', '-')
                .replace('}', '-')
                .replace(' ', '-')
                .replace('$', '-')
                .replace('&', '-')
                # Filesystem invalid characters
                .replace('/', '-')
                .replace('\\', '-')
                .replace(':', '-')
                .replace('*', '-')
                .replace('?', '-')
                .replace('"', '-')
                .replace('<', '-')
                .replace('>', '-')
                .replace('|', '-')
                # Other problematic characters
                .replace('#', '-')
                .replace('@', '-')
                .replace('!', '-')
                .replace('~', '-')
                .replace('`', '-')
                .replace('^', '-')
                .replace('+', '-')
                .replace('=', '-')
                .replace('[', '-')
                .replace(']', '-')
                .replace('(', '-')
                .replace(')', '-'))
    
    # Use pathvalidate to sanitize the path
    sanitized = pv_sanitize_filepath(path)
    
    # Replace any remaining periods with hyphens
    sanitized = sanitized.replace('.', '-')
    
    # Remove multiple consecutive hyphens
    sanitized = re.sub(r'-+', '-', sanitized)
    
    # Remove leading/trailing hyphens
    sanitized = sanitized.strip('-')
    
    log.info(f"Sanitized path: {path} -> {sanitized}")
    
    return sanitized

def smart_copy(src: Path, dst: Path) -> None:
    """
    Copy files using the most efficient method available.
    On macOS with APFS, uses fast cloning if on same volume. Otherwise falls back to regular copy.
    Sanitizes filenames during copy.
    
    Args:
        src: Source path to copy from
        dst: Destination path to copy to
    """
    # Skip .DS_Store files
    if src.name == '.DS_Store':
        log.info(f"Skipping .DS_Store file: {src}")
        return

    # Create parent directory first
    dst.parent.mkdir(parents=True, exist_ok=True)
    
    # If source is a file, copy it directly
    if src.is_file():
        shutil.copy2(str(src), str(dst))
        log.info(f"Copied file: {src.name}")
        return
    
    # If source is a directory, copy its contents
    log.info(f"Copying folder: {src.name}")
    
    # Check if source and destination are on the same volume
    try:
        # Get source volume
        src_df = subprocess.run(
            ["df", str(src)],
            capture_output=True,
            text=True
        ).stdout.strip().split('\n')
        if len(src_df) < 2:
            raise ValueError(f"Unexpected df output for source: {src_df}")
        src_volume = src_df[1].split()[0]
        
        # Get destination volume
        dst_df = subprocess.run(
            ["df", str(dst.parent)],  # Use parent since dst might not exist yet
            capture_output=True,
            text=True
        ).stdout.strip().split('\n')
        if len(dst_df) < 2:
            raise ValueError(f"Unexpected df output for destination: {dst_df}")
        dst_volume = dst_df[1].split()[0]
        
        same_volume = src_volume == dst_volume
        log.info(f"Source volume: {src_volume}, Destination volume: {dst_volume}, Same volume: {same_volume}")
    except Exception as e:
        log.error(f"Error checking volumes: {e}")
        same_volume = False
    
    # Only use APFS clone if on same volume and it's APFS
    if same_volume and is_apfs(dst.parent):
        try:
            # Create a temporary directory for the clone
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                # Clone to temp directory first
                result = subprocess.run(
                    ["cp", "-Rc", str(src), str(temp_path)],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    # Move contents from temp to destination, sanitizing filenames
                    for item in temp_path.iterdir():
                        # Skip .DS_Store files
                        if item.name == '.DS_Store':
                            continue
                        # Use sanitize_filename for files and sanitize_path for directories
                        if item.is_file():
                            sanitized_name = sanitize_filename(item.name)
                        else:
                            sanitized_name = sanitize_path(item.name)
                        sanitized_dst = dst / sanitized_name
                        shutil.move(str(item), str(sanitized_dst))
                    log.info(f"Completed APFS clone of {src.name}")
                else:
                    log.error(f"APFS clone failed with error: {result.stderr}")
                    raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)
        except subprocess.CalledProcessError as e:
            # Fallback to regular copy if clone fails
            log.info(f"APFS clone failed, falling back to regular copy for {src.name}")
            # Copy contents directly with sanitized names
            for item in src.iterdir():
                # Skip .DS_Store files
                if item.name == '.DS_Store':
                    continue
                # Use sanitize_filename for files and sanitize_path for directories
                if item.is_file():
                    sanitized_name = sanitize_filename(item.name)
                else:
                    sanitized_name = sanitize_path(item.name)
                sanitized_dst = dst / sanitized_name
                if item.is_file():
                    shutil.copy2(str(item), str(sanitized_dst))
                else:
                    shutil.copytree(str(item), str(sanitized_dst), dirs_exist_ok=True)
            log.info(f"Completed regular copy of {src.name}")
    else:
        # Regular copy for cross-volume or non-APFS
        log.info(f"Using regular copy for {src.name} (cross-volume or non-APFS)")
        # Copy contents directly with sanitized names
        for item in src.iterdir():
            # Skip .DS_Store files
            if item.name == '.DS_Store':
                continue
            sanitized_name = sanitize_filename(item.name)
            sanitized_dst = dst / sanitized_name
            if item.is_file():
                shutil.copy2(str(item), str(sanitized_dst))
            else:
                shutil.copytree(str(item), str(sanitized_dst), dirs_exist_ok=True)
        log.info(f"Completed regular copy of {src.name}")

def get_python_path() -> str:
    """Get the Python executable path from the current environment"""
    return sys.executable

def get_python_env() -> Dict[str, str]:
    """Get the current environment variables"""
    return os.environ.copy()

def run_script_directly(script_path: str, cwd: str, worker_log: logging.Logger) -> bool:
    """Run a Python script directly and return success status"""
    try:
        # Get the current Python executable
        python_exe = get_python_path()
        worker_log.info(f"Using Python: {python_exe}")
        
        # Get current environment
        env = get_python_env()
        
        # Use Popen to get process handle for cleanup
        process = subprocess.Popen(
            script_path,
            text=True,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True,
            env=env
        )
        
        # Track this process
        current_processes.add(process.pid)
        
        try:
            # Read output line by line
            for line in iter(process.stdout.readline, ''):
                if line:
                    # Log to file
                    worker_log.info(line.strip())
            
            process.wait()
            return process.returncode == 0
        except KeyboardInterrupt:
            # Kill the entire process group
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait()
            raise
        finally:
            # Remove from tracked processes
            current_processes.discard(process.pid)
    except Exception as e:
        worker_log.error(f"Error running script {script_path}: {str(e)}")
        return False

def expand_vars(text: str, vars_dict: Dict) -> str:
    """Expand variables in text using the vars dictionary"""
    def expand_nested(value):
        if isinstance(value, str):
            # First pass: expand direct variables
            for key, val in vars_dict.items():
                value = value.replace(f"${{{key}}}", str(val))
            
            # Second pass: expand vars.* variables
            for key, val in vars_dict.items():
                value = value.replace(f"${{vars.{key}}}", str(val))
            
            # Third pass: expand any remaining nested variables
            while "${" in value:
                for key, val in vars_dict.items():
                    value = value.replace(f"${{{key}}}", str(val))
                    value = value.replace(f"${{vars.{key}}}", str(val))
            return value
        return value

    # Expand all variables in the vars_dict first
    expanded_vars = {k: expand_nested(v) for k, v in vars_dict.items()}
    
    # Now expand the text using the expanded vars
    result = text
    for key, value in expanded_vars.items():
        result = result.replace(f"${{{key}}}", str(value))
        result = result.replace(f"${{vars.{key}}}", str(value))
    
    # Convert relative paths to absolute paths
    if result.startswith("python "):
        parts = result.split()
        if len(parts) >= 2:
            # Convert script path to absolute if it's relative
            script_path = parts[1]
            if not os.path.isabs(script_path):
                script_path = os.path.abspath(script_path)
            parts[1] = script_path
            result = " ".join(parts)
    
    return result

def create_plan_yml(template_path: Path, target_folder: Path, output_path: Path) -> None:
    """
    Create a new plan.yml file for a specific folder.
    Just copies the template and updates the project_folder path.
    """
    log.info(f"Starting create_plan_yml with:")
    log.info(f"  template_path: {template_path}")
    log.info(f"  target_folder: {target_folder}")
    log.info(f"  output_path: {output_path}")
    
    try:
        # Read the template file
        log.info("Reading template file...")
        with open(template_path, 'r') as f:
            content = f.read()
        log.info("Template file read successfully")
        
        # Update project_folder to use the target folder path, properly escaped
        target_folder_str = str(target_folder.absolute()).replace('\\', '\\\\').replace('$', '\\$')
        log.info(f"Updating project_folder to: {target_folder_str}")
        content = re.sub(
            r'project_folder: ".*"',
            f'project_folder: "{target_folder_str}"',  # Use escaped absolute path
            content
        )
        
        # Update fichero_root to use relative path to the fichero directory
        fichero_root = str(Path(__file__).parent.absolute()).replace('\\', '\\\\').replace('$', '\\$')
        log.info(f"Updating fichero_root to: {fichero_root}")
        content = re.sub(
            r'fichero_root: ".*"',
            f'fichero_root: "{fichero_root}"',
            content
        )
        
        # Write the modified content
        log.info(f"Writing plan.yml to: {output_path}")
        with open(output_path, 'w') as f:
            f.write(content)
        log.info("Plan.yml written successfully")
    except Exception as e:
        log.error(f"Error creating plan.yml: {str(e)}")
        log.error(f"Full traceback:\n{traceback.format_exc()}")
        raise

def parse_plan_yml(plan_yml_path: Path) -> Dict:
    """Parse plan.yml and return the workflow configuration"""
    with open(plan_yml_path, 'r') as f:
        return yaml.safe_load(f)

def prepare_folder(input_folder: Path, output_folder: Path) -> Path:
    """
    Prepare a folder for processing by creating the required structure and copying files.
    Returns the path to the prepared folder.
    """
    # Create output folder with same name as input folder
    output_subfolder = output_folder / input_folder.name
    output_subfolder.mkdir(parents=True, exist_ok=True)
    
    # Create assets folder
    assets_folder = output_subfolder / "assets"
    assets_folder.mkdir(parents=True, exist_ok=True)
    
    # Create documents folder
    documents_folder = output_subfolder / "documents"
    documents_folder.mkdir(parents=True, exist_ok=True)
    
    # Copy input files to documents folder
    for item in input_folder.iterdir():
        # Skip .DS_Store files
        if item.name == '.DS_Store':
            continue
        if item.is_file():
            smart_copy(item, documents_folder / item.name)
        elif item.is_dir():
            # For subdirectories, copy their contents
            target_dir = documents_folder / item.name
            target_dir.mkdir(exist_ok=True)
            for subitem in item.iterdir():
                # Skip .DS_Store files in subdirectories too
                if subitem.name == '.DS_Store':
                    continue
                if subitem.is_file():
                    smart_copy(subitem, target_dir / subitem.name)
    
    return output_subfolder

@celery_app.task(bind=True, name='process_folder')
def process_folder(self, folder_path: str, template_yml: str, workflow_name: str, steps: List[str] = None) -> bool:
    """
    Process a single folder using direct script execution.
    Can process specific steps if provided, otherwise processes the entire workflow.
    """
    folder_path = Path(folder_path)
    template_yml = Path(template_yml)
    folder_name = folder_path.name
    
    # Get worker-specific logger (for file logging only)
    worker_log = get_worker_logger(folder_path)
    
    # Initialize display_worker variable
    display_worker = "Unknown"
    
    try:
        # Get current worker name
        worker_name = self.request.hostname
        queue_name = self.request.delivery_info.get('routing_key', 'unknown')
        
        # Update task state with worker info
        self.update_state(state='PROGRESS', meta={
            'status': 'Starting processing',
            'step': 'Initializing',
            'worker': worker_name,
            'queue': queue_name
        })
        
        # Determine display worker based on queue
        if queue_name == 'cpu_intensive':
            display_worker = "CPU"
        elif queue_name == 'io_intensive':
            display_worker = "I/O"
        else:
            display_worker = f"{worker_name} ({queue_name})"
            
        update_status(folder_name, display_worker, "Starting", "Initializing")
        
        # Create plan.yml for this folder
        plan_yml = folder_path / "plan.yml"
        log.info(f"Creating plan.yml at {plan_yml}")
        log.info(f"Using template from {template_yml}")
        log.info(f"Template exists: {template_yml.exists()}")
        log.info(f"Folder path exists: {folder_path.exists()}")
        log.info(f"Folder path is writable: {os.access(folder_path, os.W_OK)}")
        
        create_plan_yml(template_yml, folder_path, plan_yml)
        log.info(f"Plan.yml created at {plan_yml}")
        log.info(f"Plan.yml exists after creation: {plan_yml.exists()}")
        
        # Parse plan.yml and run scripts directly
        plan_config = parse_plan_yml(plan_yml)
        
        # Get workflow steps
        workflow_steps = plan_config.get('workflows', {}).get(workflow_name)
        if not workflow_steps:
            error_msg = f"Workflow {workflow_name} not found in plan.yml"
            log.error(error_msg)
            update_status(folder_name, display_worker, "Failed", error_msg)
            return False
        
        # Get commands configuration
        commands = {cmd['name']: cmd for cmd in plan_config.get('commands', [])}
        
        # Process each step
        for step_name in workflow_steps:
            if step_name not in commands:
                error_msg = f"Command {step_name} not found in plan.yml"
                log.error(error_msg)
                update_status(folder_name, display_worker, "Failed", error_msg)
                return False
            
            # Get command configuration
            cmd_config = commands[step_name]
            
            # Update status
            update_status(folder_name, display_worker, "Processing", step_name)
            
            # Run each script in the command
            for script in cmd_config['script']:
                # Expand variables in script command
                expanded_script = expand_vars(script, plan_config.get('vars', {}))
                
                # Run the script
                success = run_script_directly(expanded_script, str(folder_path), worker_log)
                if not success:
                    error_msg = f"Script failed: {expanded_script}"
                    log.error(error_msg)
                    update_status(folder_name, display_worker, "Failed", error_msg)
                    return False
        
        update_status(folder_name, display_worker, "Completed", "All steps finished")
        return True
        
    except Exception as e:
        error_msg = f"Error processing folder: {str(e)}"
        log.error(error_msg)
        update_status(folder_name, display_worker, "Failed", error_msg)
        return False

def ensure_workers_running():
    """Ensure Redis and Celery workers are running, start them if not"""
    console = Console()
    
    # Check if Redis is running
    redis_running = False
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.pid == 1:  # Skip launchd/init process
                continue
            cmdline = ' '.join(proc.cmdline()).lower()
            if 'redis-server' in cmdline and not any(x in cmdline for x in ['launchd', 'init']):
                redis_running = True
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    
    # Start Redis if not running
    if not redis_running:
        console.print("[yellow]Starting Redis server...[/yellow]")
        redis_process = subprocess.Popen(['redis-server'], 
                       stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE)
        time.sleep(2)  # Give Redis time to start
        
        # Check if Redis started successfully
        if redis_process.poll() is not None:
            out, err = redis_process.communicate()
            console.print(f"[red]Failed to start Redis: {err.decode()}[/red]")
            raise RuntimeError("Failed to start Redis server")
    
    # Check if Celery workers are running
    workers_running = False
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.pid == 1:  # Skip launchd/init process
                continue
            cmdline = ' '.join(proc.cmdline()).lower()
            if 'celery' in cmdline and 'worker' in cmdline:
                workers_running = True
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    
    # Start workers if not running
    if not workers_running:
        console.print("[yellow]Starting Celery workers...[/yellow]")
        
        # Get CPU count and detect architecture
        cpu_count = multiprocessing.cpu_count()
        
        # Check if we're on an M1/M2 Mac
        is_m1_mac = False
        if platform.system() == "Darwin" and platform.machine() == "arm64":
            try:
                result = subprocess.run(['sysctl', '-n', 'machdep.cpu.brand_string'], 
                                      capture_output=True, text=True)
                if 'Apple' in result.stdout:
                    is_m1_mac = True
            except:
                pass
        
        # Calculate worker counts
        if is_m1_mac:
            cpu_workers = max(1, cpu_count // 2)
            io_workers = max(4, cpu_count * 2)
        else:
            cpu_workers = max(1, cpu_count // 2)
            io_workers = max(4, cpu_count * 2)
        
        # Get the correct module name for Celery
        celery_module = get_celery_module_name()
        
        # Start CPU worker
        cpu_worker_cmd = [
            'celery', '-A', celery_module, 'worker',
            '-Q', 'cpu_intensive',
            '-n', 'cpu_worker@%h',
            '-c', str(cpu_workers),
            '--loglevel=INFO',
            '--pidfile=cpu_worker.pid',
            '--logfile=cpu_worker.log',
            '--detach'  # Run in background
        ]
        subprocess.run(cpu_worker_cmd, check=True)
        
        # Start IO worker
        io_worker_cmd = [
            'celery', '-A', celery_module, 'worker',
            '-Q', 'io_intensive',
            '-n', 'io_worker@%h',
            '-c', str(io_workers),
            '--loglevel=INFO',
            '--pidfile=io_worker.pid',
            '--logfile=io_worker.log',
            '--detach'  # Run in background
        ]
        subprocess.run(io_worker_cmd, check=True)
        
        # Wait for workers to start
        console.print("[yellow]Waiting for workers to start...[/yellow]")
        max_retries = 10
        retry_count = 0
        workers_ready = False
        
        while retry_count < max_retries and not workers_ready:
            try:
                # Check worker status
                result = subprocess.run(
                    ['celery', '-A', celery_module, 'status'],
                    capture_output=True,
                    text=True,
                    check=True
                )
                if 'cpu_worker' in result.stdout and 'io_worker' in result.stdout:
                    workers_ready = True
                    break
            except subprocess.CalledProcessError:
                pass
            
            retry_count += 1
            time.sleep(2)
        
        if not workers_ready:
            console.print("[red]⚠️  Workers failed to start properly[/red]")
            raise RuntimeError("Failed to start Celery workers")

def ensure_celery_backend():
    """Ensure Celery is using Redis backend, not DisabledBackend"""
    try:
        # Check if we have a disabled backend
        if 'Disabled' in str(type(celery_app.backend)):
            log.info("Detected DisabledBackend, reconfiguring Celery to use Redis...")
            
            # Force reconfigure with Redis backend
            celery_app.conf.update(
                broker_url='redis://localhost:6379/0',
                result_backend='redis://localhost:6379/0',
                backend='redis://localhost:6379/0'
            )
            
            # Recreate the backend
            from celery.backends.redis import RedisBackend
            celery_app.backend = RedisBackend(app=celery_app)
            
            log.info(f"Reconfigured backend type: {type(celery_app.backend)}")
            
        # Test the connection
        try:
            import redis
            r = redis.Redis(host='localhost', port=6379, db=0)
            r.ping()
            log.info("Redis connection test: SUCCESS")
        except Exception as e:
            log.error(f"Redis connection test: FAILED - {e}")
            
    except Exception as e:
        log.error(f"Error ensuring Celery backend: {e}")

@cli.command()
def process_folders(
    input_folder: Path = typer.Argument(..., help="Folder containing images or subfolders to process"),
    output_folder: Path = typer.Argument(..., help="Base folder for output"),
    workflow_name: str = typer.Argument("default", help="Name of the workflow to run (defaults to 'default')"),
    template_yml: Optional[Path] = typer.Option(None, help="Template plan.yml file (defaults to resources/plans/plans.yml)")
):
    """
    Process folders concurrently using Celery tasks with smart scheduling.
    
    Strategy:
    1. Prioritize completing folders that have started (IO tasks for CPU-completed folders)
    2. Keep CPU cores busy even if IO queue is backed up (within limits)
    3. Prevent excessive backlog by limiting how far CPU can run ahead of IO
    4. Process folders in order to maintain predictable completion
    
    This ensures:
    - Maximum resource utilization (no idle cores)
    - Folders complete as fast as possible
    - Memory usage stays reasonable (limited backlog)
    - Long-running tasks (5+ minutes) are visually flagged
    """
    console = Console()
    try:
        # Set default template path if none provided
        if template_yml is None:
            template_yml = Path(__file__).parent / "resources" / "plans" / "plans.yml"
            log.info(f"Using default template: {template_yml}")
        
        # Ensure Celery backend is properly configured
        ensure_celery_backend()
        
        # Debug: Check Celery backend configuration
        log.info(f"Celery backend type: {type(celery_app.backend)}")
        log.info(f"Celery backend URL: {celery_app.backend.url if hasattr(celery_app.backend, 'url') else 'No URL'}")
        log.info(f"Celery broker URL: {celery_app.broker_connection().as_uri()}")
        
        # Test Redis connection
        try:
            r = redis.Redis(host='localhost', port=6379, db=0)
            r.ping()
            log.info("Redis connection test: SUCCESS")
        except Exception as e:
            log.error(f"Redis connection test: FAILED - {e}")
        
        # Ensure Redis and Celery workers are running
        ensure_workers_running()
        
        # Validate inputs
        if not template_yml.exists():
            raise typer.BadParameter(f"Template file {template_yml} does not exist")
        
        # Create output base folder if it doesn't exist
        output_folder.mkdir(parents=True, exist_ok=True)
        
        # Get list of folders to process
        if input_folder:
            # Process new folders from input_folder
            if not input_folder.exists():
                raise typer.BadParameter(f"Input folder {input_folder} does not exist")
            
            # Check if input_folder contains subfolders
            subfolders = [f for f in input_folder.iterdir() if f.is_dir()]
            
            if subfolders:
                # If input_folder contains subfolders, process each subfolder
                subfolders = sorted(subfolders, key=lambda x: x.name.lower())
                log.info(f"Found {len(subfolders)} subfolders to process")
                
                # Phase 1: Prepare all folders
                prepared_folders = []
                for folder in subfolders:
                    prepared_folder = prepare_folder(folder, output_folder)
                    prepared_folders.append(prepared_folder)
            else:
                # If input_folder is empty or contains only files, treat it as a single folder to process
                log.info("No subfolders found, treating input folder as a single folder to process")
                prepared_folder = prepare_folder(input_folder, output_folder)
                prepared_folders = [prepared_folder]
        else:
            # Process existing folders in output_folder, sorted alphanumerically
            prepared_folders = sorted([f for f in output_folder.iterdir() if f.is_dir()], key=lambda x: x.name.lower())
            if not prepared_folders:
                raise typer.BadParameter(f"No folders found in {output_folder}. Please use --input-folder to specify input folders to process.")
            
            log.info(f"Found {len(prepared_folders)} existing folders to process")
        
        # Phase 2: Process folders concurrently
        console = Console()
        
        # Parse template plan.yml once to get workflow info
        template_config = parse_plan_yml(template_yml)
        workflow_steps = template_config.get('workflows', {}).get(workflow_name, [])
        commands = {cmd['name']: cmd for cmd in template_config.get('commands', [])}
        
        # Initialize status for all folders
        for folder in prepared_folders:
            folder_name = folder.name
            update_status(folder_name, "Waiting", "Waiting to start...")
        
        # Separate steps into CPU and IO
        cpu_steps = []
        io_steps = []
        
        for step in workflow_steps:
            if step in commands:
                cmd = commands[step]
                if 'cpu_intensive' in cmd.get('tags', []):
                    cpu_steps.append(step)
                else:
                    io_steps.append(step)
        
        # Process folders
        active_tasks = {}
        active_task_ids = set()
        completed_folders = set()
        current_cpu_tasks = 0
        current_io_tasks = 0
        max_cpu_tasks = 4  # Limit CPU tasks to prevent memory issues
        max_io_tasks = 8   # IO tasks are less memory intensive
        
        with Live(create_status_table(), refresh_per_second=1) as live:
            while prepared_folders or active_tasks:
                # Update status table
                live.update(create_status_table())
                
                # Check for completed tasks
                completed_tasks = []
                for folder_name, task_info in list(active_tasks.items()):
                    task_id = task_info['task_id']
                    result = AsyncResult(task_id, app=celery_app)
                    
                    if result.ready():
                        if result.successful():
                            completed_folders.add(folder_name)
                            completed_tasks.append(folder_name)
                            if task_info['queue'] == 'cpu_intensive':
                                current_cpu_tasks -= 1
                            else:
                                current_io_tasks -= 1
                        else:
                            error_msg = f"Task failed: {result.result}"
                            update_status(folder_name, task_info['queue'], "Failed", error_msg)
                            completed_tasks.append(folder_name)
                            if task_info['queue'] == 'cpu_intensive':
                                current_cpu_tasks -= 1
                            else:
                                current_io_tasks -= 1
                
                # Remove completed tasks
                for folder_name in completed_tasks:
                    del active_tasks[folder_name]
                    active_task_ids.discard(task_info['task_id'])
                
                # Submit new tasks if we have capacity
                if prepared_folders:
                    # Try to submit CPU task first
                    if current_cpu_tasks < max_cpu_tasks and cpu_steps:
                        folder = prepared_folders.pop(0)
                        folder_name = folder.name
                        
                        # Submit CPU task
                        task = process_folder.apply_async(
                            args=[str(folder), str(template_yml), workflow_name],
                            queue='cpu_intensive',
                            kwargs={'steps': cpu_steps}
                        )
                        active_task_ids.add(task.id)
                        active_tasks[folder_name] = {
                            'task_id': task.id,
                            'queue': 'cpu_intensive',
                            'steps': cpu_steps,
                            'folder': folder
                        }
                        current_cpu_tasks += 1
                        log.info(f"Submitted CPU task for {folder_name}")
                    
                    # If no CPU steps or CPU queue is full, try IO task
                    elif current_io_tasks < max_io_tasks:
                        folder = prepared_folders.pop(0)
                        folder_name = folder.name
                        
                        # Submit IO task
                        task = process_folder.apply_async(
                            args=[str(folder), str(template_yml), workflow_name],
                            queue='io_intensive',
                            kwargs={'steps': io_steps}
                        )
                        active_task_ids.add(task.id)
                        active_tasks[folder_name] = {
                            'task_id': task.id,
                            'queue': 'io_intensive',
                            'steps': io_steps,
                            'folder': folder
                        }
                        current_io_tasks += 1
                        log.info(f"Submitted IO task for {folder_name}")
                
                # Small delay to prevent CPU spinning
                time.sleep(0.1)
        
        # Final status update
        console.print("\n[green]Processing completed![/green]")
        console.print(f"Successfully processed {len(completed_folders)} folders")
        
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        sys.exit(1)

@cli.command()
def purge_tasks():
    """Purge all pending Celery tasks from all queues"""
    console = Console()
    console.print("[yellow]Purging all Celery tasks...[/yellow]")
    purge_celery_tasks()
    console.print("[green]All tasks purged successfully![/green]")

@cli.command()
def worker_status():
    """Check the status of Celery workers"""
    from celery.app.control import Control
    control = Control(celery_app)
    
    # Get active workers
    active = control.inspect().active()
    # Get registered workers
    registered = control.inspect().registered()
    # Get stats
    stats = control.inspect().stats()
    
    if not stats:
        print("No workers found")
        return
    
    console = Console()
    table = Table(title="Worker Status")
    table.add_column("Worker", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Active Tasks", style="yellow")
    table.add_column("Processed", style="magenta")
    
    for worker, info in stats.items():
        # Get active tasks for this worker
        active_tasks = len(active.get(worker, [])) if active else 0
        # Get processed tasks count
        processed = info.get('total', {}).get('processed', 0)
        # Get worker status
        status = "Active" if active_tasks > 0 else "Idle"
        
        table.add_row(
            worker,
            status,
            str(active_tasks),
            str(processed)
        )
    
    console.print(table)

@cli.command()
def example():
    """Show example usage of the prepare and process-folders commands"""
    console = Console()
    console.print("\n[bold cyan]Example Usage:[/bold cyan]")
    console.print("""
    [yellow]Step 1: Prepare the folders[/yellow]
    python fichero_director.py prepare \\
        /path/to/input \\
        /path/to/output

    [yellow]Step 2: Process the prepared folders[/yellow]
    python fichero_director.py process-folders \\
        /path/to/output \\
        /path/to/output \\
        archive-to-word-qwen-max

    [yellow]Arguments for prepare:[/yellow]
    - INPUT_FOLDER: Folder containing images or subfolders to process
    - OUTPUT_FOLDER: Base folder for output (will be created if it doesn't exist)

    [yellow]Arguments for process-folders:[/yellow]
    - INPUT_FOLDER: The output folder from the prepare step
    - OUTPUT_FOLDER: The same output folder from the prepare step
    - WORKFLOW_NAME: Name of the workflow to run (defaults to 'default')

    [yellow]Options:[/yellow]
    --template-yml: Template plan.yml file (defaults to resources/plans/plans.yml)
    """)

@cli.command()
def prepare(
    input_folder: Path = typer.Argument(..., help="Folder containing subfolders to prepare"),
    output_folder: Path = typer.Argument(..., help="Base folder for output"),
):
    """
    Prepare folders for processing by creating the required structure and copying files.
    This is the first phase of the process, which:
    1. Creates output folder structure
    2. Creates assets folder
    3. Creates documents folder with subfolder matching input folder name
    4. Copies input files to documents subfolder
    """
    console = Console()
    try:
        # Validate inputs
        if not input_folder.exists():
            raise typer.BadParameter(f"Input folder {input_folder} does not exist")
        
        # Create output base folder
        output_folder.mkdir(parents=True, exist_ok=True)
        
        # Check if input_folder contains subfolders
        subfolders = [f for f in input_folder.iterdir() if f.is_dir()]
        
        if subfolders:
            # If input_folder contains subfolders, prepare each subfolder
            subfolders = sorted(subfolders, key=lambda x: x.name.lower())
            log.info(f"Found {len(subfolders)} subfolders to prepare")
            
            with Progress() as progress:
                task = progress.add_task("[cyan]Preparing folders...", total=len(subfolders))
                
                for folder in subfolders:
                    progress.update(task, description=f"[cyan]Preparing {folder.name}...")
                    prepared_folder = prepare_folder(folder, output_folder)
                    progress.advance(task)
            
            console.print(f"[green]Successfully prepared {len(subfolders)} folders in {output_folder}[/green]")
        else:
            # If input_folder is empty or contains only files, treat it as a single folder to prepare
            log.info("No subfolders found, treating input folder as a single folder to prepare")
            prepared_folder = prepare_folder(input_folder, output_folder)
            console.print(f"[green]Successfully prepared folder {input_folder.name} in {output_folder}[/green]")
        
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        sys.exit(1)

@cli.command()
def reset_workers(
    cpu_workers: Optional[int] = typer.Option(None, "--cpu", "-c", help="Number of CPU workers"),
    io_workers: Optional[int] = typer.Option(None, "--io", "-i", help="Number of IO workers")
):
    """Reset all Celery workers and clear all tasks"""
    console = Console()
    console.print("[yellow]Resetting all Celery workers...[/yellow]")
    
    try:
        # Kill all Celery workers
        kill_celery_workers()
        
        # Purge all tasks
        purge_celery_tasks()
        
        # Kill Redis if running
        redis_pids = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.pid == 1:  # Skip launchd/init process
                    continue
                cmdline = ' '.join(proc.cmdline()).lower()
                if 'redis-server' in cmdline and not any(x in cmdline for x in ['launchd', 'init']):
                    log.info(f"Killing Redis server: {proc.pid}")
                    redis_pids.append(proc.pid)
                    kill_process_tree(proc.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        # Wait a moment for processes to die
        time.sleep(2)
        
        # Start Redis if not running
        redis_running = False
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.pid == 1:  # Skip launchd/init process
                    continue
                cmdline = ' '.join(proc.cmdline()).lower()
                if 'redis-server' in cmdline and not any(x in cmdline for x in ['launchd', 'init']):
                    redis_running = True
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        if not redis_running:
            console.print("[yellow]Starting Redis server...[/yellow]")
            redis_process = subprocess.Popen(['redis-server'], 
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
            time.sleep(2)  # Give Redis time to start
            
            # Check if Redis started successfully
            if redis_process.poll() is not None:
                out, err = redis_process.communicate()
                console.print(f"[red]Failed to start Redis: {err.decode()}[/red]")
                sys.exit(1)
        
        # Start new workers
        console.print("[yellow]Starting new workers...[/yellow]")
        
        # Get CPU count and detect architecture
        cpu_count = multiprocessing.cpu_count()
        
        # Check if we're on an M1/M2 Mac
        is_m1_mac = False
        if platform.system() == "Darwin" and platform.machine() == "arm64":
            try:
                # Check CPU brand string for Apple
                result = subprocess.run(['sysctl', '-n', 'machdep.cpu.brand_string'], 
                                      capture_output=True, text=True)
                if 'Apple' in result.stdout:
                    is_m1_mac = True
            except:
                pass
        
        # Use provided values or smart defaults
        if cpu_workers is None:
            if is_m1_mac:
                # M1/M2 Mac: use half the cores (performance cores)
                cpu_workers = max(1, cpu_count // 2)
            else:
                # Other systems: use half the cores
                cpu_workers = max(1, cpu_count // 2)
        
        if io_workers is None:
            # IO workers can be much higher than CPU count since they're mostly idle
            # Base it on expected IO task duration vs CPU task duration
            # If IO tasks take 10x longer than CPU tasks, we need more IO workers
            if is_m1_mac:
                # M1/M2 Mac: 2x total cores for IO workers
                io_workers = max(4, cpu_count * 3)
            else:
                # Other systems: 2x total cores for IO workers
                io_workers = max(4, cpu_count * 3)
        
        console.print(f"[cyan]System: {'M1/M2 Mac' if is_m1_mac else 'Standard'} with {cpu_count} cores[/cyan]")
        console.print(f"[cyan]Starting {cpu_workers} CPU workers and {io_workers} IO workers[/cyan]")
        
        # Get the correct module name for Celery
        celery_module = get_celery_module_name()
        
        # Start CPU worker
        cpu_worker_cmd = [
            'celery', '-A', celery_module, 'worker',
            '-Q', 'cpu_intensive',
            '-n', 'cpu_worker@%h',
            '-c', str(cpu_workers),
            '--loglevel=INFO',
            '--pidfile=cpu_worker.pid',
            '--logfile=cpu_worker.log',
            '--detach'  # Run in background
        ]
        subprocess.run(cpu_worker_cmd, check=True)
        
        # Start IO worker
        io_worker_cmd = [
            'celery', '-A', celery_module, 'worker',
            '-Q', 'io_intensive',
            '-n', 'io_worker@%h',
            '-c', str(io_workers),
            '--loglevel=INFO',
            '--pidfile=io_worker.pid',
            '--logfile=io_worker.log',
            '--detach'  # Run in background
        ]
        subprocess.run(io_worker_cmd, check=True)
        
        # Wait for workers to start
        console.print("[yellow]Waiting for workers to start...[/yellow]")
        max_retries = 10
        retry_count = 0
        workers_ready = False
        
        while retry_count < max_retries and not workers_ready:
            try:
                # Check worker status
                result = subprocess.run(
                    ['celery', '-A', celery_module, 'status'],
                    capture_output=True,
                    text=True,
                    check=True
                )
                if 'cpu_worker' in result.stdout and 'io_worker' in result.stdout:
                    workers_ready = True
                    break
            except subprocess.CalledProcessError:
                pass
            
            retry_count += 1
            time.sleep(2)
        
        if not workers_ready:
            console.print("[red]⚠️  Workers failed to start properly[/red]")
            sys.exit(1)
        
        # Verify workers are running
        cpu_worker_running = False
        io_worker_running = False
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.pid == 1:  # Skip launchd/init process
                    continue
                cmdline = ' '.join(proc.cmdline()).lower()
                if 'celery' in cmdline and 'worker' in cmdline:
                    if 'cpu_worker' in cmdline:
                        cpu_worker_running = True
                    elif 'io_worker' in cmdline:
                        io_worker_running = True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        if cpu_worker_running and io_worker_running:
            console.print(f"[green]✓ Workers reset successfully with {cpu_workers} CPU and {io_workers} IO workers[/green]")
        else:
            if not cpu_worker_running:
                console.print("[red]⚠️  CPU worker failed to start[/red]")
            if not io_worker_running:
                console.print("[red]⚠️  IO worker failed to start[/red]")
            sys.exit(1)
            
    except Exception as e:
        console.print(f"[red]Error resetting workers: {str(e)}[/red]")
        sys.exit(1)

@cli.command()
def stop_workers():
    """Stop all Celery workers and Redis server gracefully"""
    console = Console()
    console.print("[yellow]Stopping all workers and Redis...[/yellow]")
    
    try:
        # First kill all running Python scripts
        kill_all_python_processes()
        
        # Purge all Celery tasks
        purge_celery_tasks()
        
        # Kill Celery workers gracefully
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.pid == 1:  # Skip launchd/init process
                    continue
                cmdline = ' '.join(proc.cmdline()).lower()
                if 'celery' in cmdline and 'worker' in cmdline:
                    log.info(f"Stopping Celery worker: {proc.pid}")
                    # Try graceful shutdown first
                    try:
                        proc.terminate()
                    except psutil.NoSuchProcess:
                        continue
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        # Wait a moment for workers to shut down
        time.sleep(2)
        
        # Try to purge Redis data before stopping the server
        try:
            console.print("[yellow]Purging Redis data...[/yellow]")
            subprocess.run(['redis-cli', 'FLUSHALL'], check=True)
            subprocess.run(['redis-cli', 'FLUSHDB'], check=True)
            console.print("[green]✓ Redis data purged successfully[/green]")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            console.print(f"[yellow]⚠️  Could not purge Redis data: {str(e)}[/yellow]")
        
        # Kill Redis if running
        redis_running = False
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.pid == 1:  # Skip launchd/init process
                    continue
                cmdline = ' '.join(proc.cmdline()).lower()
                if 'redis-server' in cmdline and not any(x in cmdline for x in ['launchd', 'init']):
                    log.info(f"Stopping Redis server: {proc.pid}")
                    # Try graceful shutdown first
                    try:
                        proc.terminate()
                    except psutil.NoSuchProcess:
                        continue
                    redis_running = True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        # Wait a moment for Redis to shut down
        time.sleep(2)
        
        # Force kill any remaining processes
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.pid == 1:  # Skip launchd/init process
                    continue
                cmdline = ' '.join(proc.cmdline()).lower()
                if ('celery' in cmdline and 'worker' in cmdline) or 'redis-server' in cmdline:
                    log.info(f"Force killing process: {proc.pid}")
                    try:
                        proc.kill()
                    except psutil.NoSuchProcess:
                        continue
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        # Clear status tracking
        worker_assignments.clear()
        folder_status.clear()
        folder_start_times.clear()
        folder_completion_times.clear()
        
        console.print("[green]✓ All workers and Redis stopped successfully[/green]")
            
    except Exception as e:
        console.print(f"[red]Error stopping workers: {str(e)}[/red]")
        sys.exit(1)

async def process_folders_async(
    input_folder: Path,
    output_folder: Path,
    workflow_name: str = "default",
    template_yml: Optional[Path] = None
) -> bool:
    """
    Async version of process_folders that can be called directly from app.py.
    Returns True if processing was successful, False otherwise.
    """
    try:
        # Set default template path if none provided
        if template_yml is None:
            template_yml = Path(__file__).parent / "resources" / "plans" / "plans.yml"
            log.info(f"Using default template: {template_yml}")
        
        # Ensure Celery backend is properly configured
        ensure_celery_backend()
        
        # Test Redis connection
        try:
            r = redis.Redis(host='localhost', port=6379, db=0)
            r.ping()
            log.info("Redis connection test: SUCCESS")
        except Exception as e:
            log.error(f"Redis connection test: FAILED - {e}")
            return False
        
        # Ensure Redis and Celery workers are running
        ensure_workers_running()
        
        # Validate inputs
        if not template_yml.exists():
            log.error(f"Template file {template_yml} does not exist")
            return False
        
        # Create output base folder if it doesn't exist
        output_folder.mkdir(parents=True, exist_ok=True)
        
        # Get list of folders to process
        if not input_folder.exists():
            log.error(f"Input folder {input_folder} does not exist")
            return False
        
        # Check if input_folder contains subfolders
        subfolders = [f for f in input_folder.iterdir() if f.is_dir()]
        
        if subfolders:
            # If input_folder contains subfolders, process each subfolder
            subfolders = sorted(subfolders, key=lambda x: x.name.lower())
            log.info(f"Found {len(subfolders)} subfolders to process")
            
            # Phase 1: Prepare all folders
            prepared_folders = []
            for folder in subfolders:
                prepared_folder = prepare_folder(folder, output_folder)
                prepared_folders.append(prepared_folder)
        else:
            # If input_folder is empty or contains only files, treat it as a single folder to process
            log.info("No subfolders found, treating input folder as a single folder to process")
            prepared_folder = prepare_folder(input_folder, output_folder)
            prepared_folders = [prepared_folder]
        
        # Parse template plan.yml once to get workflow info
        template_config = parse_plan_yml(template_yml)
        workflow_steps = template_config.get('workflows', {}).get(workflow_name, [])
        commands = {cmd['name']: cmd for cmd in template_config.get('commands', [])}
        
        # Initialize status for all folders
        for folder in prepared_folders:
            folder_name = folder.name
            update_status(folder_name, "Waiting", "Waiting to start...")
        
        # Process each folder
        for folder in prepared_folders:
            folder_name = folder.name
            try:
                # Process the folder
                result = process_folder.delay(
                    str(folder),
                    str(template_yml),
                    workflow_name,
                    steps=workflow_steps
                )
                
                # Wait for the task to complete
                while not result.ready():
                    await asyncio.sleep(0.1)
                
                if not result.successful():
                    log.error(f"Failed to process folder {folder_name}")
                    return False
                
            except Exception as e:
                log.error(f"Error processing folder {folder_name}: {e}")
                return False
        
        return True
        
    except Exception as e:
        log.error(f"Error in process_folders_async: {e}")
        return False

if __name__ == "__main__":
    cli() 