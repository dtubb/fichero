from rich.progress import Progress, TextColumn, BarColumn, SpinnerColumn, TimeElapsedColumn
from rich.console import Console
from pathlib import Path
from typing import Dict, Optional, Tuple, TYPE_CHECKING, Any, List
import os
import json
from scripts.utils.logging_utils import rich_log, should_show_progress
from scripts.utils.jsonl_manager import JSONLManager

console = Console()

def should_show_progress() -> bool:
    """Check if this process should show progress displays.
    Returns False if this is a child process or worker process."""
    return os.environ.get('FICHERO_CHILD_PROCESS') != '1' and os.environ.get('WORKER_ID') is None

class WorkflowProgress:
    """Tracks progress of workflow steps and overall completion."""
    
    def __init__(self, base_dir: str = "data"):
        """
        Initialize WorkflowProgress.
        
        Args:
            base_dir: Base directory for progress tracking
        """
        self.base_dir = Path(base_dir)
        self.progress_dir = self.base_dir / "progress"
        self.progress_file = self.progress_dir / "workflow_progress.jsonl"
        self.jsonl_manager = JSONLManager(str(self.progress_file))
        self._ensure_directories()

    def _ensure_directories(self):
        """Ensure required directories exist."""
        try:
            self.progress_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            rich_log("error", f"Error creating progress directory {self.progress_dir}: {str(e)}")
            raise

    def initialize_workflow(self, workflow_id: str, steps: List[str]) -> bool:
        """
        Initialize a new workflow with steps.
        
        Args:
            workflow_id: Unique identifier for the workflow
            steps: List of step names in the workflow
            
        Returns:
            bool: True if initialization was successful
        """
        try:
            workflow = {
                "workflow_id": workflow_id,
                "steps": steps,
                "current_step": steps[0] if steps else None,
                "status": "pending",
                "progress": {step: 0 for step in steps},
                "metadata": {}
            }
            return self.jsonl_manager.append_entry(workflow)
        except Exception as e:
            rich_log("error", f"Error initializing workflow {workflow_id}: {str(e)}")
            return False

    def get_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """
        Get workflow data by ID.
        
        Args:
            workflow_id: ID of the workflow
            
        Returns:
            Optional[Dict[str, Any]]: Workflow data or None if not found
        """
        try:
            return self.jsonl_manager.read_entry("workflow_id", workflow_id)
        except Exception as e:
            rich_log("error", f"Error getting workflow {workflow_id}: {str(e)}")
            return None

    def update_step_progress(self, workflow_id: str, step: str, progress: float, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Update progress for a specific step.
        
        Args:
            workflow_id: ID of the workflow
            step: Name of the step
            progress: Progress value (0-100)
            metadata: Additional metadata to update
            
        Returns:
            bool: True if update was successful
        """
        try:
            workflow = self.get_workflow(workflow_id)
            if not workflow:
                rich_log("warning", f"Workflow {workflow_id} not found")
                return False
                
            if step not in workflow["steps"]:
                rich_log("warning", f"Step {step} not found in workflow {workflow_id}")
                return False
                
            workflow["progress"][step] = min(max(progress, 0), 100)
            if metadata:
                workflow["metadata"].update(metadata)
                
            return self.jsonl_manager.update_entry("workflow_id", workflow_id, workflow)
        except Exception as e:
            rich_log("error", f"Error updating progress for workflow {workflow_id}, step {step}: {str(e)}")
            return False

    def complete_step(self, workflow_id: str, step: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Mark a step as completed and move to the next step.
        
        Args:
            workflow_id: ID of the workflow
            step: Name of the completed step
            metadata: Additional metadata to update
            
        Returns:
            bool: True if step was completed successfully
        """
        try:
            workflow = self.get_workflow(workflow_id)
            if not workflow:
                rich_log("warning", f"Workflow {workflow_id} not found")
                return False
                
            if step not in workflow["steps"]:
                rich_log("warning", f"Step {step} not found in workflow {workflow_id}")
                return False
                
            # Update progress to 100%
            workflow["progress"][step] = 100
            
            # Find next step
            current_index = workflow["steps"].index(step)
            if current_index < len(workflow["steps"]) - 1:
                workflow["current_step"] = workflow["steps"][current_index + 1]
            else:
                workflow["current_step"] = None
                workflow["status"] = "completed"
                
            if metadata:
                workflow["metadata"].update(metadata)
                
            return self.jsonl_manager.update_entry("workflow_id", workflow_id, workflow)
        except Exception as e:
            rich_log("error", f"Error completing step {step} in workflow {workflow_id}: {str(e)}")
            return False

    def fail_step(self, workflow_id: str, step: str, error: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Mark a step as failed.
        
        Args:
            workflow_id: ID of the workflow
            step: Name of the failed step
            error: Error message
            metadata: Additional metadata to update
            
        Returns:
            bool: True if step was marked as failed successfully
        """
        try:
            workflow = self.get_workflow(workflow_id)
            if not workflow:
                rich_log("warning", f"Workflow {workflow_id} not found")
                return False
                
            if step not in workflow["steps"]:
                rich_log("warning", f"Step {step} not found in workflow {workflow_id}")
                return False
                
            workflow["status"] = "failed"
            workflow["error"] = error
            workflow["failed_step"] = step
            
            if metadata:
                workflow["metadata"].update(metadata)
                
            return self.jsonl_manager.update_entry("workflow_id", workflow_id, workflow)
        except Exception as e:
            rich_log("error", f"Error marking step {step} as failed in workflow {workflow_id}: {str(e)}")
            return False

    def get_workflow_progress(self, workflow_id: str) -> Dict[str, Any]:
        """
        Get progress information for a workflow.
        
        Args:
            workflow_id: ID of the workflow
            
        Returns:
            Dict[str, Any]: Progress information
        """
        try:
            workflow = self.get_workflow(workflow_id)
            if not workflow:
                return {"error": f"Workflow {workflow_id} not found"}
                
            return {
                "workflow_id": workflow_id,
                "status": workflow["status"],
                "current_step": workflow["current_step"],
                "progress": workflow["progress"],
                "error": workflow.get("error"),
                "failed_step": workflow.get("failed_step")
            }
        except Exception as e:
            rich_log("error", f"Error getting progress for workflow {workflow_id}: {str(e)}")
            return {"error": str(e)}

    def get_all_workflows(self) -> List[Dict[str, Any]]:
        """
        Get all workflows.
        
        Returns:
            List[Dict[str, Any]]: List of all workflows
        """
        try:
            return self.jsonl_manager.read_all()
        except Exception as e:
            rich_log("error", f"Error getting all workflows: {str(e)}")
            return []

    def clear_workflow(self, workflow_id: str) -> bool:
        """
        Clear a workflow.
        
        Args:
            workflow_id: ID of the workflow to clear
            
        Returns:
            bool: True if workflow was cleared successfully
        """
        try:
            workflow = self.get_workflow(workflow_id)
            if not workflow:
                rich_log("warning", f"Workflow {workflow_id} not found")
                return False
                
            return self.jsonl_manager.delete_entry("workflow_id", workflow_id)
        except Exception as e:
            rich_log("error", f"Error clearing workflow {workflow_id}: {str(e)}")
            return False

    def clear_all_workflows(self) -> bool:
        """
        Clear all workflows.
        
        Returns:
            bool: True if all workflows were cleared successfully
        """
        try:
            return self.jsonl_manager.batch_update([])
        except Exception as e:
            rich_log("error", f"Error clearing all workflows: {str(e)}")
            return False

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
        self.progress.update(self.task, advance=1, processed=processed, total=self.progress.tasks[self.task].total, **fields)
        
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
        workflow_progress = WorkflowProgress()
        
    step_progress = StepProgress(total_files, step_name)
    
    return workflow_progress, step_progress 