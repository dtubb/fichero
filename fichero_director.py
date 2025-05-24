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
    task_time_limit=3600,  # 1 hour timeout
    worker_max_tasks_per_child=1,  # Restart worker after each task
    worker_prefetch_multiplier=1,  # Process one task at a time
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
current_processes = set()
# Track worker assignments and status
worker_assignments = {}  # folder_name -> worker_id
folder_status = {}      # folder_name -> status
folder_start_times = {} # folder_name -> start_time
folder_completion_times = {} # folder_name -> completion_time

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

def update_status(folder_name: str, worker_id: str, status: str, step: str = None, error: str = None):
    """Update the status of a folder"""
    worker_assignments[folder_name] = worker_id
    folder_status[folder_name] = status
    
    if step:
        folder_status[f"{folder_name}_step"] = step
    if error:
        folder_status[f"{folder_name}_error"] = error
    
    # Track start time when status changes to Processing
    if status == "Processing" and folder_name not in folder_start_times:
        folder_start_times[folder_name] = time.time()
    # Track completion time when status changes to Completed or Failed
    elif status in ["Completed", "Failed"] and folder_name not in folder_completion_times:
        folder_completion_times[folder_name] = time.time()

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
    table = Table(
        title="Processing Status",
        show_header=True,
        header_style="bold magenta",
        border_style="blue"
    )
    table.add_column("Worker", style="cyan", width=10)
    table.add_column("Folder", style="green", width=40, no_wrap=True)
    table.add_column("Progress", style="yellow", width=50)
    
    # Get all folders and sort them alphanumerically
    all_folders = sorted(folder_status.keys(), key=lambda x: x.lower())
    
    # Define status priority (lower number = higher priority)
    status_priority = {
        "Processing": 0,  # Highest priority
        "Waiting": 1,
        "Completed": 2,
        "Failed": 2
    }
    
    # Sort folders by status priority first, then by name
    def get_folder_priority(folder_name):
        status = folder_status.get(folder_name, "Waiting")
        return (status_priority.get(status, 3), folder_name.lower())
    
    # Sort all folders by priority and name
    sorted_folders = sorted(all_folders, key=get_folder_priority)
    
    for folder_name in sorted_folders:
        worker_id = worker_assignments.get(folder_name, "Waiting")
        status = folder_status.get(folder_name, "Waiting")
        
        # Create progress display
        if status == "Completed":
            progress = "[green]✓[/green] Completed"
        elif status == "Failed":
            # Extract error message if available
            error_msg = folder_status.get(f"{folder_name}_error", "Unknown error")
            progress = f"[red]✗[/red] Failed: {error_msg}"
        else:
            # Use different spinner frames for visual variety
            spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            frame = spinner_frames[int(time.time() * 2) % len(spinner_frames)]
            # Get current step if available
            current_step = folder_status.get(f"{folder_name}_step", "")
            if current_step:
                progress = f"[yellow]{frame}[/yellow] {status}: {current_step}"
            else:
                progress = f"[yellow]{frame}[/yellow] {status}"
        
        table.add_row(worker_id, folder_name, progress)
    
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

def signal_handler(signum, frame):
    """Handle interrupt signals by cleaning up processes"""
    log.info("\nReceived interrupt signal. Cleaning up processes...")
    
    # Kill all tracked processes
    for pid in current_processes:
        kill_process_tree(pid)
    
    # Shutdown executor
    if executor:
        executor.shutdown(wait=False, cancel_futures=True)
    
    # Force exit
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

def smart_copy(src: Path, dst: Path) -> None:
    """
    Copy files using the most efficient method available.
    On macOS with APFS, uses fast cloning if on same volume. Otherwise falls back to regular copy.
    
    Args:
        src: Source path to copy from
        dst: Destination path to copy to
    """
    log.info(f"Copying folder: {src.name}")
    
    # Create parent directory first
    dst.parent.mkdir(parents=True, exist_ok=True)
    
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
            result = subprocess.run(
                ["cp", "-Rc", str(src), str(dst)],  # Added -R for recursive cloning
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                log.info(f"Completed APFS clone of {src.name}")
            else:
                log.error(f"APFS clone failed with error: {result.stderr}")
                raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)
        except subprocess.CalledProcessError as e:
            # Fallback to regular copy if clone fails
            log.info(f"APFS clone failed, falling back to regular copy for {src.name}")
            shutil.copytree(src, dst, dirs_exist_ok=True)
            log.info(f"Completed regular copy of {src.name}")
    else:
        # Regular copy for cross-volume or non-APFS
        log.info(f"Using regular copy for {src.name} (cross-volume or non-APFS)")
        shutil.copytree(src, dst, dirs_exist_ok=True)
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
    # First pass: expand direct variables
    for key, value in vars_dict.items():
        text = text.replace(f"${{{key}}}", str(value))
    
    # Second pass: expand vars.* variables
    for key, value in vars_dict.items():
        text = text.replace(f"${{vars.{key}}}", str(value))
    
    # Third pass: expand any remaining nested variables
    while "${" in text:
        for key, value in vars_dict.items():
            text = text.replace(f"${{{key}}}", str(value))
            text = text.replace(f"${{vars.{key}}}", str(value))
    
    # Convert relative paths to absolute paths
    if text.startswith("python "):
        parts = text.split()
        if len(parts) >= 2:
            # Convert script path to absolute if it's relative
            script_path = parts[1]
            if not os.path.isabs(script_path):
                script_path = os.path.abspath(script_path)
            parts[1] = script_path
            text = " ".join(parts)
    
    return text

def create_project_yml(template_path: Path, target_folder: Path, output_path: Path) -> None:
    """
    Create a new project.yml file for a specific folder.
    Just copies the template and updates the project_folder path.
    
    Args:
        template_path: Path to the template project.yml
        target_folder: The folder this project.yml is for
        output_path: Where to save the new project.yml
    """
    # Read the template file
    with open(template_path, 'r') as f:
        content = f.read()
    
    # Update project_folder to use the target folder path
    content = re.sub(
        r'project_folder: ".*"',
        f'project_folder: "{target_folder.absolute()}"',  # Use absolute path
        content
    )
    
    # Update fichero_root to use absolute path to the fichero directory
    fichero_root = Path(__file__).parent.absolute()
    content = re.sub(
        r'fichero_root: ".*"',
        f'fichero_root: "{fichero_root}"',
        content
    )
    
    # Write the modified content
    with open(output_path, 'w') as f:
        f.write(content)

def prepare_folder(input_folder: Path, output_base: Path) -> Path:
    """
    Prepare a folder for processing by creating the required structure and copying files.
    Creates a new folder in output_base with the same name as input_folder,
    sets up the documents and assets folders, and copies the input files.
    Skips copying if the folder already exists.
    
    Args:
        input_folder: Source folder to process
        output_base: Base directory for output
        
    Returns:
        Path: Path to the prepared folder
    """
    # Create the output folder with the same name as input
    output_folder = output_base / input_folder.name
    output_folder.mkdir(parents=True, exist_ok=True)
    
    # Create assets folder for processed files
    assets_folder = output_folder / "assets"
    assets_folder.mkdir(exist_ok=True)
    
    # Create documents folder with subfolder matching input folder name
    documents_folder = output_folder / "documents" / input_folder.name
    
    # Skip if documents folder already exists and has content
    if documents_folder.exists() and any(documents_folder.iterdir()):
        log.info(f"Documents subfolder already exists in {output_folder} with content, skipping copy")
        return output_folder
    
    # Smart copy the input folder contents to documents subfolder
    # This will use APFS clone on macOS if available
    smart_copy(input_folder, documents_folder)
    
    return output_folder

def parse_project_yml(project_yml_path: Path) -> Dict:
    """Parse project.yml and return the workflow configuration"""
    with open(project_yml_path, 'r') as f:
        return yaml.safe_load(f)

@celery_app.task(bind=True, name='process_folder')
def process_folder(self, folder_path: str, template_yml: str, workflow_name: str, use_weasel: bool = True) -> bool:
    """
    Process a single folder using either Weasel workflow or direct script execution.
    Creates project.yml and runs the specified workflow.
    """
    folder_path = Path(folder_path)
    template_yml = Path(template_yml)
    folder_name = folder_path.name
    
    # Get worker-specific logger (for file logging only)
    worker_log = get_worker_logger(folder_path)
    
    try:
        # Update task state
        self.update_state(state='PROGRESS', meta={'status': 'Starting processing', 'step': 'Initializing'})
        update_status(folder_name, "Processing", "Starting", "Initializing")
        
        # Create project.yml for this folder
        project_yml = folder_path / "project.yml"
        create_project_yml(template_yml, folder_path, project_yml)
        
        # Check for DashScope API key if using Qwen Max
        if "qwen-max" in workflow_name:
            if not os.getenv("DASHSCOPE_API_KEY"):
                error_msg = "DASHSCOPE_API_KEY not found in environment variables"
                update_status(folder_name, "Failed", error_msg)
                raise ValueError(error_msg)
        
        # Run the workflow
        worker_log.info("Starting processing")
        
        # Change to the folder directory before running
        original_dir = os.getcwd()
        os.chdir(str(folder_path))
        
        try:
            if use_weasel:
                # Use Weasel to run the workflow
                cmd = f"weasel run '{workflow_name}'"
                update_status(folder_name, "Processing", "Running Weasel workflow", "Starting Weasel")
            else:
                # Parse project.yml and run scripts directly
                project_config = parse_project_yml(project_yml)
                workflow_steps = project_config.get('workflows', {}).get(workflow_name)
                commands = {cmd['name']: cmd for cmd in project_config.get('commands', [])}
                vars_dict = project_config.get('vars', {})
                
                if not workflow_steps:
                    error_msg = f"Workflow {workflow_name} not found in project.yml"
                    update_status(folder_name, "Failed", error_msg)
                    return False
                
                # Run each script in the workflow
                for step_name in workflow_steps:
                    # Update task state
                    self.update_state(state='PROGRESS', meta={'status': f'Running step: {step_name}'})
                    update_status(folder_name, "Processing", f"Running step: {step_name}")
                    
                    command = commands.get(step_name)
                    if not command:
                        error_msg = f"Command {step_name} not found in project.yml"
                        update_status(folder_name, "Failed", error_msg)
                        return False
                    
                    # Get the script command
                    script_cmd = command.get('script', [])[0]  # Take first script command
                    if not script_cmd:
                        error_msg = f"No script found for command {step_name}"
                        update_status(folder_name, "Failed", error_msg)
                        return False
                    
                    # Expand variables in the script command
                    script_cmd = expand_vars(script_cmd, vars_dict)
                    
                    worker_log.info(f"Running command: {step_name}")
                    worker_log.info(f"Script command: {script_cmd}")
                    
                    if not run_script_directly(script_cmd, str(folder_path), worker_log):
                        error_msg = f"Command {step_name} failed"
                        update_status(folder_name, "Failed", error_msg)
                        return False
                
                worker_log.info("Successfully completed all commands")
                update_status(folder_name, "Completed", "All steps completed successfully")
                return True

            if use_weasel:
                process = subprocess.Popen(
                    cmd,
                    text=True,
                    shell=True,
                    preexec_fn=os.setsid,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=1,
                    universal_newlines=True
                )
                
                # Track this process
                current_processes.add(process.pid)
                
                try:
                    # Read output line by line
                    for line in iter(process.stdout.readline, ''):
                        if line:
                            # Log to file
                            worker_log.info(line.strip())
                            # Update task state with progress
                            self.update_state(state='PROGRESS', meta={'status': line.strip()})
                            update_status(folder_name, "Processing", line.strip())
                    
                    process.wait()
                    if process.returncode != 0:
                        error_msg = f"Process failed with return code {process.returncode}"
                        update_status(folder_name, "Failed", error_msg)
                        return False
                    else:
                        worker_log.info("Successfully completed")
                        update_status(folder_name, "Completed", "Weasel workflow completed successfully")
                        return True
                except KeyboardInterrupt:
                    # Kill the entire process group
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    process.wait()
                    raise
                finally:
                    # Remove from tracked processes
                    current_processes.discard(process.pid)
        finally:
            # Always change back to original directory
            os.chdir(original_dir)
        
    except Exception as e:
        error_msg = str(e)
        worker_log.error(f"Error: {error_msg}")
        # Print the full traceback for debugging
        import traceback
        worker_log.error(f"Full traceback:\n{traceback.format_exc()}")
        update_status(folder_name, "Failed", error_msg)
        return False

@cli.command()
def process_folders(
    output_folder: Path = typer.Argument(..., help="Base folder for output"),
    template_yml: Path = typer.Argument(..., help="Template project.yml file"),
    workflow_name: str = typer.Argument(..., help="Name of the Weasel workflow to run"),
    input_folder: Optional[Path] = typer.Option(None, help="Optional: Folder containing subfolders to process. If not provided, will process existing folders in output_folder"),
    use_weasel: bool = typer.Option(True, help="Whether to use Weasel or run scripts directly")
):
    """
    Process multiple folders in parallel using Celery tasks.
    Each folder will get its own project.yml and be processed independently.
    
    The process happens in two phases:
    1. Preparation: Create folder structure and copy files (if input_folder provided)
    2. Processing: Run workflows in parallel using Celery tasks
    
    Args:
        output_folder: Base folder for output
        template_yml: Template project.yml file
        workflow_name: Name of the workflow to run
        input_folder: Optional folder containing subfolders to process. If not provided, will process existing folders in output_folder
        use_weasel: Whether to use Weasel or run scripts directly
    """
    try:
        # Validate inputs
        if not template_yml.exists():
            raise typer.BadParameter(f"Template file {template_yml} does not exist")
        
        # Create output base folder
        output_folder.mkdir(parents=True, exist_ok=True)
        
        # Get list of folders to process
        if input_folder:
            # Process new folders from input_folder
            if not input_folder.exists():
                raise typer.BadParameter(f"Input folder {input_folder} does not exist")
            
            # Get list of subfolders to process and sort them alphanumerically
            subfolders = sorted([f for f in input_folder.iterdir() if f.is_dir()], key=lambda x: x.name.lower())
            if not subfolders:
                raise typer.BadParameter(f"No subfolders found in {input_folder}")
            
            # Phase 1: Prepare all folders
            prepared_folders = []
            for folder in subfolders:
                prepared_folder = prepare_folder(folder, output_folder)
                prepared_folders.append(prepared_folder)
        else:
            # Process existing folders in output_folder, sorted alphanumerically
            prepared_folders = sorted([f for f in output_folder.iterdir() if f.is_dir()], key=lambda x: x.name.lower())
            if not prepared_folders:
                raise typer.BadParameter(f"No folders found in {output_folder}")
            
            log.info(f"Found {len(prepared_folders)} existing folders to process")
        
        # Phase 2: Process folders using Celery tasks
        console = Console()
        
        # Initialize status for all folders as waiting
        for folder in prepared_folders:
            update_status(folder.name, "Waiting", "Waiting to start...")
        
        # Submit all tasks to Celery at once
        tasks = []
        for folder in prepared_folders:
            task = process_folder.delay(
                str(folder),
                str(template_yml),
                workflow_name,
                use_weasel
            )
            tasks.append((task, folder.name))
        
        # Monitor task progress with a more efficient update strategy
        with Live(create_status_table(), refresh_per_second=1, auto_refresh=True) as live:
            while tasks:
                # Check all tasks in batches
                for task, folder_name in tasks[:]:
                    result = AsyncResult(task.id)
                    if result.ready():
                        if result.successful():
                            update_status(folder_name, "Completed", "Task completed successfully")
                        else:
                            update_status(folder_name, "Failed", f"Task failed: {result.result}")
                        tasks.remove((task, folder_name))
                    else:
                        # Update status with current progress
                        if result.state == 'PROGRESS':
                            update_status(folder_name, "Processing", result.info.get('status', 'Processing...'))
                
                # Update the display
                live.update(create_status_table(), refresh=True)
                
                # Adaptive sleep based on number of remaining tasks
                if len(tasks) > 10:
                    time.sleep(0.5)  # More frequent updates when many tasks are running
                else:
                    time.sleep(2)  # Slower updates when fewer tasks remain
            
            # Final update to show completion
            live.update(create_status_table(), refresh=True)
            console.print("[green]All folders processed successfully![/green]")
            
    except KeyboardInterrupt:
        console.print("\n[yellow]Received keyboard interrupt. Cleaning up...[/yellow]")
        sys.exit(0)

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
    """Show example usage of the process-folders command"""
    console = Console()
    console.print("\n[bold cyan]Example Usage:[/bold cyan]")
    console.print("""
    [yellow]Basic usage:[/yellow]
    python fichero_director.py process-folders /Volumes/Fichero/output /path/to/template.yml my_workflow

    [yellow]With all options:[/yellow]
    python fichero_director.py process-folders \\
        /Volumes/Fichero/output \\
        /path/to/template.yml \\
        my_workflow \\
        --input-folder /Volumes/Fichero/input \\
        --use-weasel

    [yellow]Arguments:[/yellow]
    - OUTPUT_FOLDER: Base folder for output (required)
    - TEMPLATE_YML: Template project.yml file (required)
    - WORKFLOW_NAME: Name of the workflow to run (required)

    [yellow]Options:[/yellow]
    --input-folder: Optional folder containing subfolders to process
    --use-weasel: Whether to use Weasel or run scripts directly (default: True)
    """)

@cli.command()
def prepare(
    output_folder: Path = typer.Argument(..., help="Base folder for output"),
    input_folder: Path = typer.Argument(..., help="Folder containing subfolders to prepare"),
):
    """
    Prepare folders for processing by creating the required structure and copying files.
    This is the first phase of the process, which:
    1. Creates output folder structure
    2. Creates assets folder
    3. Creates documents folder with subfolder matching input folder name
    4. Copies input files to documents subfolder
    """
    try:
        # Validate inputs
        if not input_folder.exists():
            raise typer.BadParameter(f"Input folder {input_folder} does not exist")
        
        # Create output base folder
        output_folder.mkdir(parents=True, exist_ok=True)
        
        # Get list of subfolders to process and sort them
        subfolders = sorted([f for f in input_folder.iterdir() if f.is_dir()], key=lambda x: x.name.lower())
        if not subfolders:
            raise typer.BadParameter(f"No subfolders found in {input_folder}")
        
        console = Console()
        with Progress() as progress:
            task = progress.add_task("[cyan]Preparing folders...", total=len(subfolders))
            
            for folder in subfolders:
                progress.update(task, description=f"[cyan]Preparing {folder.name}...")
                prepared_folder = prepare_folder(folder, output_folder)
                progress.advance(task)
        
        console.print(f"[green]Successfully prepared {len(subfolders)} folders in {output_folder}[/green]")
        
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        sys.exit(1)

if __name__ == "__main__":
    cli() 