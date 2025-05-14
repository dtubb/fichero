from rich.progress import Progress, TextColumn, BarColumn, SpinnerColumn, TimeElapsedColumn
from rich.console import Console
from pathlib import Path
from typing import Dict, Optional, Tuple, TYPE_CHECKING
import logging
import os

logger = logging.getLogger(__name__)
console = Console()

def should_show_progress() -> bool:
    """Check if this process should show progress displays.
    Returns False if this is a child process or worker process."""
    return os.environ.get('FICHERO_CHILD_PROCESS') != '1' and os.environ.get('WORKER_ID') is None

class WorkflowProgress:
    """Handles workflow-level progress tracking"""
    
    def __init__(self, total_steps: int):
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console
        )
        self.total_steps = total_steps
        self.current_step = 0
        self.step_task = self.progress.add_task(
            "[cyan]Workflow Progress",
            total=total_steps
        )
        
    def start_step(self, step_name: str) -> None:
        """Start a new step in the workflow."""
        self.current_step += 1
        self.progress.update(
            self.step_task,
            description=f"[cyan]Step {self.current_step}/{self.total_steps}: {step_name}",
            advance=1
        )
        
    def __enter__(self):
        return self.progress.__enter__()
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        return self.progress.__exit__(exc_type, exc_val, exc_tb)

class StepProgress:
    """Handles step-level progress tracking"""
    
    def __init__(self, total_files: int, step_name: str):
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[progress.files]{task.fields[processed]}/{task.fields[total]} files"),
            TimeElapsedColumn(),
            console=console
        )
        self.task = self.progress.add_task(
            f"[green]{step_name}",
            total=total_files,
            processed=0
        )
        
    def update(self, processed: int, **fields) -> None:
        """Update progress with processed files count."""
        self.progress.update(self.task, advance=1, processed=processed, **fields)
        
    def __enter__(self):
        return self.progress.__enter__()
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        return self.progress.__exit__(exc_type, exc_val, exc_tb)

def create_progress_tracker(
    total_files: int,
    step_name: str,
    show_workflow: bool = False,
    total_steps: Optional[int] = None
) -> Tuple[Optional[WorkflowProgress], Optional[StepProgress]]:
    """Create progress trackers for workflow and step level.
    Returns None for both if this is a child/worker process."""
    if not should_show_progress():
        return None, None
        
    workflow_progress = None
    if show_workflow and total_steps:
        workflow_progress = WorkflowProgress(total_steps)
        
    step_progress = StepProgress(total_files, step_name)
    
    return workflow_progress, step_progress 