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

from scripts.utils.workflow_progress import WorkflowProgress, StepProgress

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)
logger = logging.getLogger("fichero")

app = typer.Typer(help="Fichero CLI - Document Processing and Transcription")
console = Console()

def is_debug_mode() -> bool:
    """Check if debug mode is enabled via flag or environment variable."""
    return os.environ.get('FICHERO_DEBUG', '0') == '1'

def configure_logging(debug: bool = False):
    """Configure logging based on debug mode."""
    if debug or is_debug_mode():
        logging.getLogger().setLevel(logging.DEBUG)
        # Enable all debug logging
        logging.getLogger('ultralytics').setLevel(logging.DEBUG)
        logging.getLogger('PIL').setLevel(logging.DEBUG)
        logging.getLogger('torch').setLevel(logging.DEBUG)
        os.environ['FICHERO_DEBUG'] = '1'
    else:
        logging.getLogger().setLevel(logging.WARNING)
        # Disable all debug logging from other modules
        logging.getLogger('ultralytics').setLevel(logging.WARNING)
        logging.getLogger('PIL').setLevel(logging.WARNING)
        logging.getLogger('torch').setLevel(logging.WARNING)
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
    
    cmd = ['python', str(script_path)] + args
    logger.info(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        logger.error(f"Script failed with exit code {result.returncode}")
        logger.error(f"Error output: {result.stderr}")
        raise Exception(f"Script failed: {result.stderr}")
    if result.stdout.strip():
        logger.info("Script output:")
        for line in result.stdout.splitlines():
            logger.info(f"  {line}")

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
    
    # Launch workers
    processes = []
    for worker_id in range(num_workers):
        # Add worker ID to environment
        env = os.environ.copy()
        env['WORKER_ID'] = str(worker_id)
        
        # Launch process with output capture
        cmd = ['python', str(script_path)] + args
        logger.info(f"Launching worker {worker_id}: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        processes.append((worker_id, process))
    
    # Monitor and log output from all workers
    while processes:
        for worker_id, process in processes[:]:
            # Check if process has finished
            if process.poll() is not None:
                # Get any remaining output
                stdout, stderr = process.communicate()
                if stdout:
                    for line in stdout.splitlines():
                        logger.info(f"Worker {worker_id}: {line}")
                if stderr:
                    for line in stderr.splitlines():
                        logger.error(f"Worker {worker_id}: {line}")
                
                # Check return code
                if process.returncode != 0:
                    raise Exception(f"Worker {worker_id} failed with exit code {process.returncode}")
                
                # Remove finished process
                processes.remove((worker_id, process))
                continue
            
            # Check for output
            stdout = process.stdout.readline()
            if stdout:
                logger.info(f"Worker {worker_id}: {stdout.strip()}")
            stderr = process.stderr.readline()
            if stderr:
                logger.error(f"Worker {worker_id}: {stderr.strip()}")
        
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
    
    # Load project configuration
    config = load_project_yml(project_yml)
    
    # Get workflow steps
    workflow = config.get('workflows', {}).get(workflow_name)
    if not workflow:
        raise typer.BadParameter(f"Workflow '{workflow_name}' not found in project.yml")
    
    # Create workflow progress tracker
    workflow_progress = WorkflowProgress(total_steps=len(workflow))
    
    with workflow_progress:
        # Execute each step in the workflow
        for step in workflow:
            workflow_progress.start_step(step)
            
            # Get command configuration
            cmd_config = get_command_config(config, step)
            if not cmd_config:
                raise Exception(f"Command '{step}' not found in project.yml")
            
            # Get system resources for parallel processing
            system_resources = get_system_resources()
            
            # Determine if this is a GPU task
            is_gpu_task = (
                step in ['crop', 'transcribe_qwen_max', 'transcribe_qwen_7b', 'transcribe_lmstudio'] or
                any('gpu' in str(arg).lower() for arg in cmd_config.get('script', []))
            )
            is_yolo_task = (
                step == 'crop' or
                any('yolo' in str(arg).lower() for arg in cmd_config.get('script', []))
            )
            
            # Calculate optimal number of workers
            num_workers = calculate_auto_workers(system_resources, is_gpu_task, is_yolo_task)
            
            if debug or is_debug_mode():
                # Log detailed system information
                logger.info("\n=== System Resource Information ===")
                logger.info(f"System: {platform.system()} {platform.release()}")
                logger.info(f"Machine: {platform.machine()}")
                logger.info(f"Processor: {platform.processor()}")
                logger.info(f"CPU Cores: {system_resources['cpu_count']}")
                logger.info(f"Total Memory: {system_resources['memory_gb']:.1f} GB")
                
                # Log GPU information
                if torch.cuda.is_available():
                    logger.info("\n=== CUDA Information ===")
                    logger.info(f"CUDA Available: Yes")
                    logger.info(f"CUDA Version: {torch.version.cuda}")
                    logger.info(f"GPU Device: {torch.cuda.get_device_name(0)}")
                    logger.info(f"GPU Count: {torch.cuda.device_count()}")
                    for i in range(torch.cuda.device_count()):
                        logger.info(f"GPU {i} Memory: {torch.cuda.get_device_properties(i).total_memory / 1024**3:.1f} GB")
                elif torch.backends.mps.is_available():
                    logger.info("\n=== MPS Information ===")
                    logger.info("MPS (Metal Performance Shaders) Available: Yes")
                    logger.info("Using Apple Silicon GPU")
                
                # Log worker configuration
                logger.info("\n=== Worker Configuration ===")
                logger.info(f"Step: {step}")
                logger.info(f"GPU Task: {is_gpu_task}")
                logger.info(f"YOLO Task: {is_yolo_task}")
                logger.info(f"CPU Workers Available: {system_resources['cpu_workers']}")
                logger.info(f"Memory Workers Available: {system_resources['memory_workers']}")
                logger.info(f"Suggested Workers: {system_resources['suggested_workers']}")
                logger.info(f"Actual Workers: {num_workers}")
                logger.info("=============================\n")
            
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
                
                # Add debug flag to script arguments if debug is enabled
                if debug or is_debug_mode():
                    resolved_args.append("--debug")
                
                # Run script with resolved arguments
                try:
                    if num_workers > 1 and manifest_path and manifest_path.exists():
                        # Run in parallel if we have a manifest file
                        run_script_parallel(Path(script_path), resolved_args, num_workers)
                    else:
                        # Run single process
                        run_script(Path(script_path), resolved_args)
                except Exception as e:
                    logger.error(f"Step '{step}' failed: {str(e)}")
                    return
    
    logger.info(f"Workflow '{workflow_name}' completed successfully")

if __name__ == "__main__":
    app() 