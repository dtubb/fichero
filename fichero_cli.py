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
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.console import Group

from scripts.utils.workflow_progress import WorkflowProgress, StepProgress
from scripts.utils.logging_utils import rich_log, should_show_progress, setup_logging
from scripts.utils.worker_manager import get_best_device

# Configure console for rich logging
console = Console()

app = typer.Typer(help="Fichero CLI - Document Processing and Transcription")

def is_debug_mode() -> bool:
    """Check if debug mode is enabled via flag or environment variable."""
    return os.environ.get('FICHERO_DEBUG', '0') == '1'

def configure_logging(debug: bool = False):
    """Configure logging based on debug mode."""
    if debug or is_debug_mode():
        os.environ['FICHERO_DEBUG'] = '1'
        # Set up logging with DEBUG level
        setup_logging(level="DEBUG")
    else:
        os.environ['FICHERO_DEBUG'] = '0'
        # Set up logging with INFO level
        setup_logging(level="INFO")

def detect_hardware() -> dict:
    """Detect available hardware and return configuration."""
    # Load execution config
    execution_config = load_execution_config()
    hardware_config = execution_config.get('hardware', {})
    
    # First check force_cpu from config
    force_cpu = hardware_config.get('force_cpu', False)
    if force_cpu:
        return {
            "device": "cpu",
            "system": platform.system().lower(),
            "is_apple_silicon": platform.system().lower() == "darwin" and platform.machine() == "arm64",
            "force_cpu": True
        }
    
    # Then check auto_detect setting
    if not hardware_config.get('auto_detect', True):
        # Use configured device
        device = hardware_config.get('device', 'cpu')
    else:
        # Auto-detect device
        device = "cpu"
        if torch.cuda.is_available():
            device = "cuda"
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            device = "mps"
    
    return {
        "device": device,
        "system": platform.system().lower(),
        "is_apple_silicon": platform.system().lower() == "darwin" and platform.machine() == "arm64",
        "force_cpu": force_cpu
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

def get_step_config(execution_config: dict, step: str, device: str, force_cpu: bool = False) -> dict:
    """Get the complete configuration for a step based on the device."""
    if not execution_config:
        return {}
    
    # Get the system config for the current device
    system_config = execution_config.get('system_configs', {}).get(device, {})
    
    # For crop step on MPS (Apple Silicon), check if we should use CPU config
    if step == 'crop' and device == 'mps' and force_cpu:
        return system_config.get('crop_cpu', {})
    
    # Get the step config
    return system_config.get(step, {})

def get_worker_count(execution_config: dict, step: str, device: str, force_cpu: bool = False) -> Optional[int]:
    """Get the configured number of workers for a step based on the device."""
    if not execution_config:
        return None
    
    # If force_cpu is True, always use CPU config regardless of device
    if force_cpu:
        device = "cpu"
    
    # Get the system config for the current device
    system_config = execution_config.get('system_configs', {}).get(device, {})
    
    # Get the step config
    step_config = system_config.get(step, {})
    
    # Handle both new dict format and legacy integer format
    if isinstance(step_config, dict):
        return step_config.get('workers')
    elif isinstance(step_config, int):
        return step_config
    return None

def get_batch_size(execution_config: dict, step: str, device: str, force_cpu: bool = False) -> Optional[int]:
    """Get the configured batch size for a step."""
    step_config = get_step_config(execution_config, step, device, force_cpu)
    if isinstance(step_config, dict):
        return step_config.get('batch_size')
    return None

def get_memory_limit(execution_config: dict, step: str, device: str, force_cpu: bool = False) -> Optional[str]:
    """Get the configured memory limit for a step."""
    step_config = get_step_config(execution_config, step, device, force_cpu)
    if isinstance(step_config, dict):
        return step_config.get('memory_limit')
    return None

def parse_memory_limit(memory_limit: str) -> int:
    """Convert memory limit string to bytes."""
    if not memory_limit:
        return None
        
    units = {
        'B': 1,
        'KB': 1024,
        'MB': 1024 * 1024,
        'GB': 1024 * 1024 * 1024,
        'TB': 1024 * 1024 * 1024 * 1024
    }
    
    match = re.match(r'(\d+)\s*([A-Za-z]+)', memory_limit)
    if match:
        value = int(match.group(1))
        unit = match.group(2).upper()
        if unit in units:
            return value * units[unit]
    return None

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

def run_script(script_path: Path, args: list, force_cpu: bool = False):
    """Run a script with the given arguments."""
    # Set project_root to the directory containing fichero_cli.py
    project_root = Path(__file__).parent.resolve()
    
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
        # Add debug flag to args if not already present
        if '--debug' not in args:
            args.append('--debug')
    
    env['FICHERO_FORCE_CPU'] = '1' if force_cpu else '0'
    
    cmd = ['python', str(script_path)] + args
    rich_log("info", f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        rich_log("error", f"Script failed with exit code {result.returncode}")
        rich_log("error", f"Error output: {result.stderr}")
        raise Exception(f"Script failed: {result.stderr}")
    if result.stdout.strip():
        for line in result.stdout.splitlines():
            if os.environ.get('FICHERO_DEBUG') == '1':
                print(f"  {line}")
            else:
                rich_log("info", f"  {line}")

def run_script_parallel(script_path: Path, args: list, num_workers: int, force_cpu: bool = False, parent_progress: Optional[Progress] = None):
    """Run multiple instances of a script in parallel."""
    # Get manifest path from args
    manifest_path = None
    for i, arg in enumerate(args):
        if arg.endswith('.jsonl'):
            manifest_path = arg
            break
    
    # Use parent progress if provided, otherwise create new one
    progress = parent_progress or Progress(
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
        env = os.environ.copy()
        env['WORKER_ID'] = str(worker_id)
        env['FICHERO_WORKER'] = '1'  # Mark as worker process
        
        # Launch process with output capture
        cmd = ['python', str(script_path)] + args
        rich_log("info", f"Launching worker {worker_id}: {' '.join(cmd)}")
        rich_log("info", f"Worker {worker_id} force_cpu: {force_cpu}")  # Log force_cpu setting
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
    
    # If we created our own progress, wrap it in Live
    if not parent_progress:
        with Live(progress, refresh_per_second=4, vertical_overflow="visible") as live:
            _monitor_workers(processes, worker_tasks, progress)
    else:
        # Otherwise just use the parent progress directly
        _monitor_workers(processes, worker_tasks, progress)
    
    rich_log("info", "All workers finished")

def _monitor_workers(processes, worker_tasks, progress):
    """Monitor worker processes and update progress."""
    while processes:
        for worker_id, process in processes[:]:
            # Check if process has finished
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                if stdout:
                    for line in stdout.splitlines():
                        if "Completed:" in line:
                            progress.update(worker_tasks[worker_id], advance=1)
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
                rich_log("info", f"Worker {worker_id}: {line}")
                
                # Update progress based on output
                if "[CROP] Starting processing:" in line:
                    current_file = line.split("[CROP] Starting processing:")[1].strip()
                    progress.update(
                        worker_tasks[worker_id],
                        description=f"Worker {worker_id}: {current_file}"
                    )
                elif "[CROP] Finished processing:" in line:
                    progress.update(
                        worker_tasks[worker_id],
                        advance=1,
                        description=f"Worker {worker_id}"
                    )
                elif "Total files:" in line:
                    try:
                        total = int(line.split("Total files:")[1].strip())
                        progress.update(
                            worker_tasks[worker_id],
                            total=total,
                            description=f"Worker {worker_id}"
                        )
                    except ValueError:
                        pass
            
            stderr = process.stderr.readline()
            if stderr:
                rich_log("error", f"Worker {worker_id}: {stderr.strip()}")
                progress.update(
                    worker_tasks[worker_id],
                    description=f"Worker {worker_id} (Error)"
                )
        
        time.sleep(0.1)

@app.command(name="run-workflow")
def run_workflow(
    project_yml: Path = typer.Argument(..., help="Path to project.yml file"),
    workflow_name: str = typer.Argument(..., help="Name of workflow to run"),
    debug: bool = typer.Option(False, help="Enable debug logging"),
    force_cpu: bool = typer.Option(False, help="Force CPU usage for YOLO processing")
) -> None:
    """Run a workflow defined in project.yml."""
    start_time = time.time()
    
    # Configure logging based on debug flag
    configure_logging(debug)
    
    # Load configurations
    config = load_project_yml(project_yml)
    execution_config = load_execution_config()
    
    # Set force_cpu based on both config and command line
    config_force_cpu = execution_config.get('hardware', {}).get('force_cpu', False)
    force_cpu = force_cpu or config_force_cpu
    
    # Set environment variable for force_cpu
    os.environ['FICHERO_FORCE_CPU'] = '1' if force_cpu else '0'
    
    if debug:
        rich_log("info", f"Force CPU from config: {config_force_cpu}")
        rich_log("info", f"Force CPU from command line: {force_cpu}")
        rich_log("info", f"Final Force CPU setting: {force_cpu}")
    
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
                configured_workers = get_worker_count(execution_config, step, hardware_info['device'], force_cpu)
                
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
                    rich_log("info", f"Force CPU: {force_cpu}")
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
                
                # Run script with resolved arguments
                try:
                    if num_workers > 1:
                        # Run in parallel if we have multiple workers configured
                        run_script_parallel(Path(script_path), resolved_args, num_workers, force_cpu, progress)
                    else:
                        # Run single process
                        run_script(Path(script_path), resolved_args, force_cpu)
                except Exception as e:
                    rich_log("error", f"Step '{step}' failed: {str(e)}")
                    return
    
    rich_log("info", f"Workflow '{workflow_name}' completed successfully")
    elapsed = time.time() - start_time
    rich_log("info", f"Total time to completion: {elapsed:.2f} seconds")

if __name__ == "__main__":
    app() 