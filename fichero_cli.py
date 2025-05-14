import typer
import yaml
from pathlib import Path
import subprocess
import logging
import torch
import platform
import re
import multiprocessing
import psutil
from concurrent.futures import ProcessPoolExecutor
import asyncio
from typing import List, Dict, Optional
import fcntl
import tempfile
import os
from scripts.utils.jsonl_manager import JSONLManager
import time
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.console import Group

from scripts.utils.workflow_progress import WorkflowProgress, StepProgress

# Configure console for rich logging
console = Console()

def rich_log(level, message):
    """Log a message with rich formatting, respecting debug mode."""
    # Get debug mode from environment
    debug_mode = os.environ.get('FICHERO_DEBUG', '0') == '1'
    
    if level == "info":
        if debug_mode:
            console.log(f"[bold cyan][INFO][/bold cyan] {message}")
        else:
            # In non-debug mode, only show important info messages
            if "Processing complete" in message or "Processing " in message and "files" in message:
                console.log(f"[bold cyan][INFO][/bold cyan] {message}")
    elif level == "warning":
        console.log(f"[bold yellow][WARNING][/bold yellow] {message}")
    elif level == "error":
        console.log(f"[bold red][ERROR][/bold red] {message}")
    else:
        if debug_mode:
            console.log(message)

app = typer.Typer(help="Fichero CLI - Document Processing and Transcription")

def is_debug_mode() -> bool:
    """Check if debug mode is enabled via flag or environment variable."""
    return os.environ.get('FICHERO_DEBUG', '0') == '1'

def configure_logging(debug: bool = False):
    """Configure logging based on debug mode."""
    if debug or is_debug_mode():
        os.environ['FICHERO_DEBUG'] = '1'
    else:
        os.environ['FICHERO_DEBUG'] = '0'

def detect_hardware() -> dict:
    """Detect available hardware and return configuration."""
    device = "cpu"
    if torch.cuda.is_available():
        device = "cuda"
    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        device = "mps"
    
    system = platform.system().lower()
    is_apple_silicon = system == "darwin" and platform.machine() == "arm64"
    
    return {
        "device": device,
        "system": system,
        "is_apple_silicon": is_apple_silicon
    }

def get_system_resources() -> dict:
    """Get system resource information for worker count calculation."""
    cpu_count = multiprocessing.cpu_count()
    memory_gb = psutil.virtual_memory().total / (1024 * 1024 * 1024)  # Convert to GB
    
    # Calculate worker counts based on resources
    # Leave some resources for system and other processes
    cpu_workers = max(1, cpu_count - 1)  # Leave one CPU free
    memory_workers = max(1, int(memory_gb / 2))  # Assume 2GB per worker
    
    return {
        'cpu_count': cpu_count,
        'memory_gb': memory_gb,
        'cpu_workers': cpu_workers,
        'memory_workers': memory_workers,
        'suggested_workers': min(cpu_workers, memory_workers)
    }

def calculate_auto_workers(system_resources: dict, is_gpu_task: bool = False, is_yolo_task: bool = False) -> int:
    """Calculate optimal number of workers based on system resources."""
    # For YOLO tasks, use more workers as they're memory efficient
    if is_yolo_task:
        return max(1, int(system_resources['cpu_count'] * 0.9))  # Use 90% of cores for YOLO
    
    # For other GPU tasks, use fewer workers to avoid memory issues
    if is_gpu_task:
        return max(1, min(4, system_resources['cpu_count'] // 2))
    
    # For CPU tasks, use 75% of available cores
    return max(1, int(system_resources['cpu_count'] * 0.75))

def resolve_vars(vars_dict: dict) -> dict:
    """Recursively resolve variables in the vars dictionary."""
    resolved = {}
    for key, value in vars_dict.items():
        if isinstance(value, str):
            # Keep resolving until no more variables are found
            while True:
                new_value = value
                for k, v in vars_dict.items():
                    if isinstance(v, str):
                        new_value = new_value.replace(f"${{vars.{k}}}", v)
                    else:
                        new_value = new_value.replace(f"${{vars.{k}}}", str(v))
                if new_value == value:  # No more changes
                    break
                value = new_value
        resolved[key] = value
    return resolved

def load_project_yml(project_yml: Path) -> dict:
    """Load and process project.yml configuration."""
    with open(project_yml, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # Recursively resolve variables in vars
    if 'vars' in config:
        config['vars'] = resolve_vars(config['vars'])
    
    return config

def load_execution_config() -> dict:
    """Load execution configuration from execution_config.yml."""
    config_path = Path(__file__).parent / "execution_config.yml"
    if not config_path.exists():
        rich_log("warning", "execution_config.yml not found, using default configuration")
        return {}
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def get_worker_count(execution_config: dict, step: str, device: str) -> int:
    """Get the configured number of workers for a step based on the device."""
    if not execution_config:
        return None
    
    # Get the system config for the current device
    system_config = execution_config.get('system_configs', {}).get(device, {})
    
    # Get the worker count for this step
    return system_config.get(step)

def get_command_config(config: dict, step: str) -> dict:
    """Get the configuration for a specific command."""
    for cmd in config.get('commands', []):
        if cmd['name'] == step:
            return cmd
    return None

def parse_script_command(cmd: str) -> tuple[str, list[str]]:
    """Parse a script command into script path and arguments, handling quotes."""
    # Split the command into parts, preserving quoted strings
    parts = []
    current = []
    in_quotes = False
    for char in cmd:
        if char == '"':
            in_quotes = not in_quotes
        elif char.isspace() and not in_quotes:
            if current:
                parts.append(''.join(current))
                current = []
        else:
            current.append(char)
    if current:
        parts.append(''.join(current))
    
    # Remove quotes from parts
    parts = [p.strip('"') for p in parts]
    
    # First part is 'python', second is script path, rest are arguments
    return parts[1], parts[2:]

def run_script(script_path: Path, args: list):
    """Run a script with the given arguments."""
    # Get the project root directory (parent of scripts directory)
    project_root = script_path.parent.parent
    
    # Add project root to PYTHONPATH
    env = os.environ.copy()
    if 'PYTHONPATH' in env:
        env['PYTHONPATH'] = f"{project_root}:{env['PYTHONPATH']}"
    else:
        env['PYTHONPATH'] = str(project_root)
    
    # Add flag to indicate this is a child process
    env['FICHERO_CHILD_PROCESS'] = '1'
    
    # Add debug flag to environment if enabled
    if os.environ.get('FICHERO_DEBUG') == '1':
        env['FICHERO_DEBUG'] = '1'
    
    cmd = ['python', str(script_path)] + args
    rich_log("info", f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        rich_log("error", f"Script failed with exit code {result.returncode}")
        rich_log("error", f"Error output: {result.stderr}")
        raise Exception(f"Script failed: {result.stderr}")
    if result.stdout.strip():
        rich_log("info", "Script output:")
        for line in result.stdout.splitlines():
            rich_log("info", f"  {line}")

def run_script_parallel(script_path: Path, args: list, num_workers: int):
    """Run multiple instances of a script in parallel with proper manifest locking."""
    # Get manifest path from args
    manifest_path = None
    for i, arg in enumerate(args):
        if arg.endswith('.jsonl'):
            manifest_path = arg
            break
    
    if not manifest_path:
        raise ValueError("No manifest file found in arguments")
    
    # Create progress bars for each worker using Rich
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("[progress.files]{task.fields[processed]}/{task.fields[total]} files"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        expand=True
    )
    
    # Create tasks for each worker
    worker_tasks = {}
    for worker_id in range(num_workers):
        worker_tasks[worker_id] = progress.add_task(
            f"Worker {worker_id}",
            total=0,  # Will be updated when we know the total
            processed=0,
            current_file="Initializing..."
        )
    
    # Launch workers
    processes = []
    for worker_id in range(num_workers):
        # Add worker ID to environment
        env = os.environ.copy()
        env['WORKER_ID'] = str(worker_id)
        env['FICHERO_WORKER'] = '1'  # Mark as worker process
        
        # Add debug flag to environment if enabled
        if os.environ.get('FICHERO_DEBUG') == '1':
            env['FICHERO_DEBUG'] = '1'
        
        # Add project root to PYTHONPATH
        project_root = script_path.parent.parent
        if 'PYTHONPATH' in env:
            env['PYTHONPATH'] = f"{project_root}:{env['PYTHONPATH']}"
        else:
            env['PYTHONPATH'] = str(project_root)
        
        # Launch process with output capture
        cmd = ['python', str(script_path)] + args
        rich_log("info", f"Launching worker {worker_id}: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
            universal_newlines=True
        )
        processes.append((worker_id, process))
    
    # Monitor and log output from all workers
    with Live(progress, refresh_per_second=4, vertical_overflow="visible") as live:
        while processes:
            for worker_id, process in processes[:]:
                # Check if process has finished
                if process.poll() is not None:
                    # Get any remaining output
                    stdout, stderr = process.communicate()
                    if stdout:
                        for line in stdout.splitlines():
                            rich_log("info", f"Worker {worker_id}: {line}")
                    if stderr:
                        for line in stderr.splitlines():
                            rich_log("error", f"Worker {worker_id}: {line}")
                    
                    # Check return code
                    if process.returncode != 0:
                        raise Exception(f"Worker {worker_id} failed with exit code {process.returncode}")
                    
                    # Update progress for completed worker
                    progress.update(
                        worker_tasks[worker_id],
                        completed=True,
                        description=f"Worker {worker_id} (Completed)"
                    )
                    
                    # Remove finished process
                    processes.remove((worker_id, process))
                    continue
                
                # Check for output
                stdout = process.stdout.readline()
                if stdout:
                    line = stdout.strip()
                    # Always log debug output
                    if os.environ.get('FICHERO_DEBUG') == '1':
                        rich_log("info", f"Worker {worker_id}: {line}")
                    
                    # Update progress based on output
                    if "Processing:" in line:
                        current_file = line.split("Processing:")[1].strip()
                        progress.update(
                            worker_tasks[worker_id],
                            description=f"Worker {worker_id}: {current_file}"
                        )
                    elif "Completed:" in line:
                        progress.update(
                            worker_tasks[worker_id],
                            advance=1,
                            description=f"Worker {worker_id}"
                        )
                    elif "Total files:" in line:
                        total = int(line.split("Total files:")[1].strip())
                        progress.update(
                            worker_tasks[worker_id],
                            total=total,
                            description=f"Worker {worker_id}"
                        )
                    elif "=== Starting YOLO Processing" in line:
                        progress.update(
                            worker_tasks[worker_id],
                            description=f"Worker {worker_id}: Initializing YOLO"
                        )
                    elif "=== YOLO Processing Complete" in line:
                        progress.update(
                            worker_tasks[worker_id],
                            description=f"Worker {worker_id}: YOLO Ready"
                        )
                
                stderr = process.stderr.readline()
                if stderr:
                    rich_log("error", f"Worker {worker_id}: {stderr.strip()}")
                    progress.update(
                        worker_tasks[worker_id],
                        description=f"Worker {worker_id} (Error)"
                    )
            
            # Small sleep to prevent CPU spinning
            time.sleep(0.1)

@app.command(name="run-workflow")
def run_workflow(
    project_yml: Path = typer.Argument(..., help="Path to project.yml file"),
    workflow_name: str = typer.Argument(..., help="Name of workflow to run"),
    debug: bool = typer.Option(False, help="Enable debug logging")
) -> None:
    """Run a workflow defined in project.yml."""
    # Configure logging based on debug flag
    configure_logging(debug)
    
    # Load configurations
    config = load_project_yml(project_yml)
    execution_config = load_execution_config()
    
    # Get workflow steps
    workflow = config.get('workflows', {}).get(workflow_name)
    if not workflow:
        raise typer.BadParameter(f"Workflow '{workflow_name}' not found in project.yml")
    
    # Create progress bars for workflow and workers
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn
    from rich.live import Live
    
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        expand=True
    )
    
    # Add workflow task
    workflow_task = progress.add_task(
        "[cyan]Workflow Progress",
        total=len(workflow)
    )
    
    with Live(progress, refresh_per_second=4, vertical_overflow="visible") as live:
        # Execute each step in the workflow
        for step_idx, step in enumerate(workflow, 1):
            progress.update(
                workflow_task,
                description=f"[cyan]Step {step_idx}/{len(workflow)}: {step}",
                advance=1
            )
            
            # Get command configuration
            cmd_config = get_command_config(config, step)
            if not cmd_config:
                raise Exception(f"Command '{step}' not found in project.yml")
            
            # Check if this is a concurrent step
            is_concurrent = step in execution_config.get('concurrent_steps', [])
            
            # Only get system resources and hardware info for concurrent steps
            if is_concurrent:
                system_resources = get_system_resources()
                hardware_info = detect_hardware()
                
                # Get configured worker count from execution_config.yml
                configured_workers = get_worker_count(execution_config, step, hardware_info['device'])
                
                # Determine if this is a GPU task
                is_gpu_task = (
                    step in ['crop', 'transcribe_qwen_max', 'transcribe_qwen_7b', 'transcribe_lmstudio'] or
                    any('gpu' in str(arg).lower() for arg in cmd_config.get('script', []))
                )
                is_yolo_task = (
                    step == 'crop' or
                    any('yolo' in str(arg).lower() for arg in cmd_config.get('script', []))
                )
                
                # Use configured workers if available, otherwise calculate optimal number
                num_workers = configured_workers if configured_workers is not None else calculate_auto_workers(system_resources, is_gpu_task, is_yolo_task)
                
                if debug or is_debug_mode():
                    # Log detailed system information
                    rich_log("info", "\n=== System Resource Information ===")
                    rich_log("info", f"System: {platform.system()} {platform.release()}")
                    rich_log("info", f"Machine: {platform.machine()}")
                    rich_log("info", f"Processor: {platform.processor()}")
                    rich_log("info", f"CPU Cores: {system_resources['cpu_count']}")
                    rich_log("info", f"Total Memory: {system_resources['memory_gb']:.1f} GB")
                    
                    # Log GPU information
                    if torch.cuda.is_available():
                        rich_log("info", "\n=== CUDA Information ===")
                        rich_log("info", "CUDA Available: Yes")
                        rich_log("info", f"CUDA Version: {torch.version.cuda}")
                        rich_log("info", f"GPU Device: {torch.cuda.get_device_name(0)}")
                        rich_log("info", f"GPU Count: {torch.cuda.device_count()}")
                        for i in range(torch.cuda.device_count()):
                            rich_log("info", f"GPU {i} Memory: {torch.cuda.get_device_properties(i).total_memory / 1024**3:.1f} GB")
                    elif torch.backends.mps.is_available():
                        rich_log("info", "\n=== MPS Information ===")
                        rich_log("info", "MPS (Metal Performance Shaders) Available: Yes")
                        rich_log("info", "Using Apple Silicon GPU")
                    
                    # Log worker configuration
                    rich_log("info", "\n=== Worker Configuration ===")
                    rich_log("info", f"Step: {step}")
                    rich_log("info", f"Device: {hardware_info['device']}")
                    rich_log("info", f"GPU Task: {is_gpu_task}")
                    rich_log("info", f"YOLO Task: {is_yolo_task}")
                    rich_log("info", f"CPU Workers Available: {system_resources['cpu_workers']}")
                    rich_log("info", f"Memory Workers Available: {system_resources['memory_workers']}")
                    rich_log("info", f"Configured Workers: {configured_workers}")
                    rich_log("info", f"Suggested Workers: {system_resources['suggested_workers']}")
                    rich_log("info", f"Actual Workers: {num_workers}")
                    rich_log("info", "=============================\n")
            else:
                # For sequential steps, just log that we're running it
                if debug or is_debug_mode():
                    rich_log("info", f"\n=== Running Sequential Step: {step} ===\n")
                num_workers = 1  # Sequential steps use single process
            
            # Execute each script in the command
            for script_cmd in cmd_config['script']:
                script_path, args = parse_script_command(script_cmd)
                
                # Replace variables in arguments
                resolved_args = []
                for arg in args:
                    if isinstance(arg, str):
                        # Replace all ${vars.key} with their values
                        for var_key, var_value in config.get('vars', {}).items():
                            if isinstance(var_value, str):
                                arg = arg.replace(f"${{vars.{var_key}}}", var_value)
                            else:
                                arg = arg.replace(f"${{vars.{var_key}}}", str(var_value))
                    resolved_args.append(arg)
                
                # Create manifest file if needed
                manifest_path = None
                if step == "crop_split":
                    # Create manifest file in project directory
                    project_folder = Path(config['vars']['project_folder'])
                    manifest_path = project_folder / "manifest.jsonl"
                    if not manifest_path.exists():
                        # Initialize manifest with all files in documents directory
                        docs_dir = project_folder / "documents"
                        manifest = JSONLManager(str(manifest_path))
                        for file_path in docs_dir.glob("**/*"):
                            if file_path.is_file():
                                manifest.add_file(str(file_path.relative_to(docs_dir)))
                        manifest.save()
                    resolved_args = [str(manifest_path), str(project_folder)] + resolved_args[2:]
                
                # Run script with resolved arguments
                try:
                    if num_workers > 1 and manifest_path and manifest_path.exists():
                        # Run in parallel if we have a manifest file
                        run_script_parallel(Path(script_path), resolved_args, num_workers)
                    else:
                        # Run single process
                        run_script(Path(script_path), resolved_args)
                except Exception as e:
                    rich_log("error", f"Step '{step}' failed: {str(e)}")
                    return
    
    rich_log("info", f"Workflow '{workflow_name}' completed successfully")

if __name__ == "__main__":
    app() 