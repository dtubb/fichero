"""
Unified Task Monitor

Single system for tracking all tasks with rich metadata.
Replaces both ProgressTracker and GlobalActivityMonitor.
"""

import threading
import time
import logging
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from pathlib import Path

# Import text spinner utilities
from ...utils.text_spinner import get_spinner_frame

# Import translations
from ...ui.i18n import _

logger = logging.getLogger(__name__)


# Shared utility functions for formatting
def format_duration(duration: timedelta) -> str:
    """
    Format a timedelta into a human-readable string.
    
    Args:
        duration: The timedelta to format
        
    Returns:
        Formatted duration string (e.g., "2m 15s", "1h 5m", "45s")
    """
    total_seconds = int(duration.total_seconds())
    
    if total_seconds < 1:
        return "0s"
    
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 and hours == 0:  # Only show seconds if less than an hour
        parts.append(f"{seconds}s")
    
    return " ".join(parts)


def format_worker_name(worker: Optional[str]) -> str:
    """Format worker name for display"""
    if not worker or worker == _("task_worker_unknown").lower():
        return _("task_worker_unknown")
        
    if worker.startswith("CPU-"):
        return _("task_worker_cpu").format(id=worker[4:])
    elif worker.startswith("IO-"):
        return _("task_worker_io").format(id=worker[3:])
    elif worker.startswith("celery"):
        return _("task_worker_celery").format(id=worker[7:])
        
    return worker


def get_status_text(status: str) -> str:
    """Get human readable status text"""
    status_map = {
        "running_cpu": _("task_status_running"),
        "running_io": _("task_status_running"),
        "running": _("task_status_running"),
        "waiting_cpu": _("task_status_waiting"),
        "waiting_io": _("task_status_waiting"),
        "waiting": _("task_status_waiting"),
        "completed": _("task_status_completed"),
        "failed": _("task_status_failed"),
        "cancelled": _("task_status_cancelled"),
        "pending": _("task_status_pending")
    }
    return status_map.get(status, status)


def get_step_verb(step_name: str, status: str) -> str:
    """Get verb describing what the step is doing"""
    step_verbs = {
        "transcribe_audio": _("task_step_transcribe"),
        "transcribe_qwen": _("task_step_transcribe"),
        "extract_text": _("task_step_extract"),
        "ocr_text": _("task_step_ocr"),
        "process_images": _("task_step_process_images"),
        "convert_format": _("task_step_convert"),
        "organize_files": _("task_step_organize"),
        "backup_files": _("task_step_backup"),
        "compress_files": _("task_step_compress"),
        "upload_files": _("task_step_upload")
    }
    
    base_verb = step_verbs.get(step_name, _("task_step_generic"))
    
    # Handle completed status
    if status == "completed":
        step_done_map = {
            _("task_step_transcribe"): _("task_step_transcribe_done"),
            _("task_step_extract"): _("task_step_extract_done"),
            _("task_step_ocr"): _("task_step_ocr_done"),
            _("task_step_process_images"): _("task_step_process_images_done"),
            _("task_step_convert"): _("task_step_convert_done"),
            _("task_step_organize"): _("task_step_organize_done"),
            _("task_step_backup"): _("task_step_backup_done"),
            _("task_step_compress"): _("task_step_compress_done"),
            _("task_step_upload"): _("task_step_upload_done"),
            _("task_step_generic"): _("task_step_generic_done")
        }
        return step_done_map.get(base_verb, base_verb)
        
    # Handle running status
    elif status in ["running", "running_cpu", "running_io"]:
        return base_verb
        
    # Handle waiting status
    elif status in ["waiting", "waiting_cpu", "waiting_io"]:
        return _("task_step_waiting").format(action=base_verb.lower())
        
    # Handle failed status
    elif status == "failed":
        return _("task_step_failed").format(action=base_verb.lower())
        
    return base_verb


@dataclass
class StepInfo:
    """Information about a workflow step"""
    step_name: str
    status: str = _("task_status_pending").lower()           # pending, running, completed, failed
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error_message: str = ""
    result: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration(self) -> timedelta:
        """Get step duration"""
        if not self.start_time:
            return timedelta(0)
        end = self.end_time or datetime.now()
        return end - self.start_time
    
    @property
    def status_icon(self) -> str:
        """Get status icon for step (animated for running steps)"""
        if self.status == "running":
            return get_spinner_frame('circle')  # Use circle spinner for steps
        
        icons = {
            "pending": "○",
            "completed": "●", 
            "failed": "✗"
        }
        return icons.get(self.status, "○")


@dataclass
class TaskInfo:
    """Complete task information"""
    # Identity
    task_id: str
    created_at: datetime = field(default_factory=datetime.now)
    
    # Context
    document_id: Optional[str] = None       # "doc_window_1", None for CLI
    instance_id: str = _("task_worker_unknown").lower()
    source: str = _("task_worker_unknown").lower()
    
    # Processing Details
    plan_name: str = _("task_worker_unknown").lower()
    workflow_name: str = _("task_worker_unknown").lower()
    input_folder: str = ""
    output_folder: str = ""
    folder_name: str = _("task_worker_unknown").lower()            # Just the folder name for display
    worker: str = _("task_worker_unknown").lower()                 # Worker ID processing this task
    executor_type: str = _("task_worker_unknown").lower()          # Type of executor (cpu, io, celery)
    
    # Progress - Task Level
    current_step: str = ""
    total_steps: int = 1
    completed_steps: int = 0
    overall_progress: float = 0.0           # 0-100 overall
    
    # Progress - Step Level
    steps: Dict[str, StepInfo] = field(default_factory=dict)
    step_names: List[str] = field(default_factory=list)  # Ordered list of step names
    
    # Status
    status: str = _("task_status_pending").lower()                 # pending, running, completed, failed, cancelled
    error_message: str = ""
    warnings: List[str] = field(default_factory=list)
    
    # Timing
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @property
    def duration(self) -> timedelta:
        """Get task duration"""
        if not self.start_time:
            return timedelta(0)
        end = self.end_time or datetime.now()
        return end - self.start_time
    
    @property
    def status_icon(self) -> str:
        """Get status icon for display (animated for running tasks)"""
        if self.status == "running":
            return get_spinner_frame('circle')  # Use circle spinner for main tasks
        
        icons = {
            "pending": "○",
            "completed": "●",
            "failed": "✗",
            "cancelled": "■"
        }
        return icons.get(self.status, "○")
    
    @property
    def is_active(self) -> bool:
        """Check if task is currently active"""
        return self.status in ["pending", "running", "failed"]
    
    @property
    def is_finished(self) -> bool:
        """Check if task is finished"""
        return self.status in ["completed", "failed", "cancelled"]
    
    def set_step_names(self, step_names: List[str]):
        """Initialize steps for the workflow"""
        self.step_names = step_names
        self.total_steps = len(step_names)
        self.steps = {name: StepInfo(step_name=name) for name in step_names}
    
    def start_step(self, step_name: str):
        """Mark a step as started"""
        if step_name not in self.steps:
            self.steps[step_name] = StepInfo(step_name=step_name)
        
        self.steps[step_name].status = "running"
        self.steps[step_name].start_time = datetime.now()
        self.current_step = step_name
        
        # Update completed steps count
        if step_name in self.step_names:
            self.completed_steps = self.step_names.index(step_name)
    
    def complete_step(self, step_name: str, success: bool = True, result: Dict = None, error_message: str = ""):
        """Mark a step as completed"""
        if step_name not in self.steps:
            return
        
        step = self.steps[step_name]
        step.status = "completed" if success else "failed"
        step.end_time = datetime.now()
        step.result = result or {}
        if error_message:
            step.error_message = error_message
        
        # Update completed steps count
        if success and step_name in self.step_names:
            step_index = self.step_names.index(step_name)
            self.completed_steps = max(self.completed_steps, step_index + 1)
        
        # Calculate overall progress
        if self.total_steps > 0:
            self.overall_progress = (self.completed_steps / self.total_steps) * 100
    
    def get_step_summary(self) -> Dict[str, Any]:
        """Get summary of all steps"""
        return {
            "total": len(self.steps),
            "completed": len([s for s in self.steps.values() if s.status == "completed"]),
            "failed": len([s for s in self.steps.values() if s.status == "failed"]),
            "running": len([s for s in self.steps.values() if s.status == "running"]),
            "pending": len([s for s in self.steps.values() if s.status == "pending"])
        }


class TaskMonitor:
    """
    Unified task monitoring system.
    
    Single source of truth for all task tracking and control.
    Used by GUI windows, CLI displays, and activity monitors.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __init__(self, director, instance_id: str = "unknown"):
        # Store references
        self.director = director
        self.instance_id = instance_id
        
        # Initialize task tracking
        self.tasks: Dict[str, TaskInfo] = {}
        self.completed_tasks: List[TaskInfo] = []
        self.callbacks: List[Callable] = []
        self.max_completed_history = 100
        
        # Thread safety
        self._task_lock = threading.Lock()
        
        # Cross-instance visibility (only with Celery)
        self._redis_client = None
        if director and hasattr(director.backend, 'redis_client'):
            self._redis_client = director.backend.redis_client
        
        # Register with director for progress updates
        if director:
            director.register_progress_callback(self._on_progress_update)
        
        # Clear old history on initialization (older than 1 hour)
        self.clear_old_history(max_age_hours=1)
        
        logger.info(f"TaskMonitor initialized for instance: {instance_id}")
    
    @classmethod
    def get_instance(cls, director=None, instance_id: str = "unknown"):
        """Get singleton instance"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(director, instance_id)
        return cls._instance
    
    # Task Management
    
    def create_task(self, task_id: str, **kwargs) -> TaskInfo:
        """Create a new task"""
        with self._task_lock:
            task_info = TaskInfo(
                task_id=task_id,
                instance_id=self.instance_id,
                **kwargs
            )
            self.tasks[task_id] = task_info
            self._notify_callbacks('task_created', task_info)
            
            logger.info(f"Created task: {task_id} ({task_info.folder_name})")
            return task_info
    
    def update_task(self, task_id: str, **updates):
        """Update task information"""
        with self._task_lock:
            if task_id not in self.tasks:
                logger.warning(f"Task not found: {task_id}")
                return
            
            task = self.tasks[task_id]
            old_status = task.status
            
            # Protect folder_name from being overwritten with generic values
            if 'folder_name' in updates:
                new_folder_name = updates['folder_name']
                # Allow updating from temporary names to real names, but protect real names
                if (task.folder_name and 
                    not task.folder_name.startswith("Task-") and 
                    task.folder_name not in ["unknown", "Processing..."] and
                    (new_folder_name == task_id or new_folder_name.startswith("Task-") or new_folder_name == "Processing...")):
                    del updates['folder_name']
                elif (task.folder_name.startswith("Task-") or task.folder_name in ["unknown", "Processing..."]) and new_folder_name and new_folder_name != task_id:
                    pass  # Allow the update
            
            for key, value in updates.items():
                if hasattr(task, key):
                    setattr(task, key, value)
            
            # Log status changes
            if 'status' in updates and updates['status'] != old_status:
                logger.info(f"Task {task_id} status changed: {old_status} -> {updates['status']}")
            
            # Auto-calculate overall progress if step-related fields were updated
            if task.total_steps > 0 and any(key in updates for key in ['completed_steps', 'total_steps']):
                task.overall_progress = (task.completed_steps / task.total_steps) * 100
            
            self._notify_callbacks('task_updated', task)
    
    def complete_task(self, task_id: str, success: bool = True, error_message: str = "", folder_name: str = ""):
        """Mark task as completed"""
        with self._task_lock:
            if task_id not in self.tasks:
                logger.warning(f"Task not found: {task_id}")
                return
            
            task = self.tasks[task_id]
            task.end_time = datetime.now()
            task.status = "completed" if success else "failed"
            task.overall_progress = 100.0 if success else task.overall_progress
            if error_message:
                task.error_message = error_message
            
            # Last chance to update folder name if provided
            if folder_name and folder_name != task_id:
                if task.folder_name.startswith("Task-") or task.folder_name in ["unknown", "Processing..."]:
                    task.folder_name = folder_name
            
            # For successful tasks, move to completed history immediately
            if success:
                completed_task = self.tasks.pop(task_id)
                logger.debug(f"Moving completed task {task_id} with folder_name '{completed_task.folder_name}' to history")
                self.completed_tasks.append(completed_task)
                
                # Limit history size
                if len(self.completed_tasks) > self.max_completed_history:
                    self.completed_tasks = self.completed_tasks[-self.max_completed_history:]
                
                self._notify_callbacks('task_completed', completed_task)
                logger.info(f"Task completed: {task_id} (folder: {completed_task.folder_name})")
            else:
                # For failed tasks, keep them visible for a while
                # They will be moved to completed history after a delay
                self._notify_callbacks('task_completed', task)
                logger.info(f"Task failed: {task_id} - {error_message}")
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task"""
        try:
            # Cancel via director
            if self.director:
                success = self.director.cancel_task(task_id)
                if success:
                    self.update_task(task_id, status="cancelled", end_time=datetime.now())
                    logger.info(f"Cancelled task: {task_id}")
                return success
            return False
        except Exception as e:
            logger.error(f"Failed to cancel task {task_id}: {e}")
            return False
    
    def cancel_all_tasks(self) -> int:
        """Cancel all active tasks"""
        active_task_ids = list(self.get_active_tasks().keys())
        cancelled_count = 0
        
        for task_id in active_task_ids:
            if self.cancel_task(task_id):
                cancelled_count += 1
        
        logger.info(f"Cancelled {cancelled_count} tasks")
        return cancelled_count
    
    # Data Access
    
    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """Get specific task"""
        with self._task_lock:
            return self.tasks.get(task_id)
    
    def get_active_tasks(self) -> Dict[str, TaskInfo]:
        """Get all active tasks"""
        with self._task_lock:
            return {tid: task for tid, task in self.tasks.items() if task.is_active}
    
    def get_all_tasks(self) -> Dict[str, TaskInfo]:
        """Get all tasks (active + completed)"""
        # Note: This method assumes the caller already has the lock
        all_tasks = dict(self.tasks)
        for task in self.completed_tasks:
            all_tasks[task.task_id] = task
        return all_tasks
    
    def get_tasks_by_document(self, document_id: str) -> Dict[str, TaskInfo]:
        """Get tasks for specific document"""
        # Note: This method assumes the caller already has the lock
        # Include both active and completed tasks for document windows
        tasks = {
            tid: task for tid, task in self.tasks.items() 
            if task.document_id == document_id
        }
        
        # Also include completed tasks for this document
        for task in self.completed_tasks:
            if task.document_id == document_id:
                tasks[task.task_id] = task
        
        return tasks
    
    def get_tasks_by_status(self, status: str) -> Dict[str, TaskInfo]:
        """Get tasks by status"""
        with self._task_lock:
            return {
                tid: task for tid, task in self.tasks.items() 
                if task.status == status
            }
    
    def get_failed_tasks(self) -> List[TaskInfo]:
        """Get failed tasks with error details"""
        failed_active = [t for t in self.tasks.values() if t.status == "failed"]
        failed_completed = [t for t in self.completed_tasks if t.status == "failed"]
        return failed_active + failed_completed
    
    # Statistics
    
    def get_stats(self) -> Dict[str, Any]:
        """Get system statistics"""
        # Note: This method assumes the caller already has the lock
        active_count = len([t for t in self.tasks.values() if t.is_active])
        
        # Count failed tasks from both active and completed lists
        failed_active = len([t for t in self.tasks.values() if t.status == "failed"])
        failed_completed = len([t for t in self.completed_tasks if t.status == "failed"])
        total_failed = failed_active + failed_completed
        
        # Count successfully completed tasks
        completed_active = len([t for t in self.tasks.values() if t.status == "completed"])
        completed_completed = len([t for t in self.completed_tasks if t.status == "completed"])
        total_completed = completed_active + completed_completed
        
        # Performance metrics
        recent_completed = [t for t in self.completed_tasks[-20:] if t.status == "completed"]
        avg_duration = 0
        if recent_completed:
            durations = [t.duration.total_seconds() for t in recent_completed]
            avg_duration = sum(durations) / len(durations)
        
        return {
            "active_tasks": active_count,
            "total_tasks": len(self.tasks) + len(self.completed_tasks),
            "completed_tasks": total_completed,
            "failed_tasks": total_failed,
            "average_duration": avg_duration,
            "last_updated": datetime.now()
        }
    
    # Backend Management
    
    def flush_backend(self) -> bool:
        """Flush backend queues"""
        if not self.director:
            return False
        
        try:
            if hasattr(self.director.backend, 'flush_redis'):
                return self.director.backend.flush_redis()
            elif hasattr(self.director.backend, 'cancel_all'):
                return self.director.backend.cancel_all()
            return False
        except Exception as e:
            logger.error(f"Failed to flush backend: {e}")
            return False
    
    def restart_backend(self) -> bool:
        """Restart backend"""
        if not self.director:
            return False
        
        try:
            self.director.backend.shutdown()
            return self.director.initialize_backend()
        except Exception as e:
            logger.error(f"Failed to restart backend: {e}")
            return False
    
    def get_backend_info(self) -> Dict[str, Any]:
        """Get backend status information"""
        if not self.director:
            return {"status": "unavailable", "error": "No director"}
        
        try:
            backend = self.director.backend
            return {
                "backend_name": backend.backend_name,
                "is_initialized": backend.is_initialized,
                "status": "healthy" if backend.is_initialized else "unhealthy",
                "timestamp": datetime.now()
            }
        except Exception as e:
            logger.error(f"Failed to get backend info: {e}")
            return {"status": "error", "error": str(e)}
    
    # Callbacks
    
    def register_callback(self, callback: Callable):
        """Register callback for task updates"""
        self.callbacks.append(callback)
    
    def unregister_callback(self, callback: Callable):
        """Unregister callback"""
        if callback in self.callbacks:
            self.callbacks.remove(callback)
    
    def _notify_callbacks(self, event_type: str, task: TaskInfo):
        """Notify all callbacks"""
        for callback in self.callbacks:
            try:
                callback(event_type, task)
            except Exception as e:
                logger.warning(f"Callback failed: {e}")
    
    def update_step(self, task_id: str, step_name: str, **updates):
        """Update specific step information"""
        with self._task_lock:
            if task_id not in self.tasks:
                logger.warning(f"Task not found for step update: {task_id}")
                return
            
            task = self.tasks[task_id]
            if step_name not in task.steps:
                task.steps[step_name] = StepInfo(step_name=step_name)
            
            step = task.steps[step_name]
            for key, value in updates.items():
                if hasattr(step, key):
                    setattr(step, key, value)
            
            self._notify_callbacks('step_updated', task)
    
    def start_step(self, task_id: str, step_name: str):
        """Mark a step as started"""
        with self._task_lock:
            if task_id in self.tasks:
                self.tasks[task_id].start_step(step_name)
                self._notify_callbacks('step_started', self.tasks[task_id])
    
    def complete_step(self, task_id: str, step_name: str, success: bool = True, 
                     result: Dict = None, error_message: str = ""):
        """Mark a step as completed"""
        with self._task_lock:
            if task_id in self.tasks:
                self.tasks[task_id].complete_step(step_name, success, result, error_message)
                self._notify_callbacks('step_completed', self.tasks[task_id])
    
    def set_workflow_steps(self, task_id: str, step_names: List[str]):
        """Initialize workflow steps for a task"""
        with self._task_lock:
            if task_id in self.tasks:
                self.tasks[task_id].set_step_names(step_names)
                self._notify_callbacks('workflow_initialized', self.tasks[task_id])

    def _on_progress_update(self, task_id: str, progress_data: Dict):
        """Handle progress updates from director"""
        try:
            # Enhanced debug logging to trace folder name issues
            logger.info(f"=== Progress update for task {task_id} ===")
            logger.info(f"Progress data keys: {list(progress_data.keys())}")
            if 'folder' in progress_data:
                logger.info(f"Folder in progress_data: '{progress_data['folder']}'")
            if 'input_folder' in progress_data:
                logger.info(f"Input_folder in progress_data: '{progress_data['input_folder']}'")
            
            # Create task if it doesn't exist AND is not already completed
            if task_id not in self.tasks:
                # Check if task already exists in completed history
                existing_completed = next((t for t in self.completed_tasks if t.task_id == task_id), None)
                if existing_completed:
                    # Task already completed, ignore further updates
                    logger.debug(f"Ignoring progress update for already completed task: {task_id}")
                    return
                
                document_id = progress_data.get("document_id")
                logger.debug(f"TaskMonitor._on_progress_update: creating task {task_id} with document_id={document_id}")
                
                # Extract folder name from multiple possible keys
                # Try 'folder_name' first (from folder_processor), then 'folder', then 'input_folder'
                if "folder_name" in progress_data and progress_data["folder_name"]:
                    folder_name = progress_data["folder_name"]
                else:
                    folder_path = progress_data.get("folder", progress_data.get("input_folder", ""))
                    if folder_path:
                        folder_name = folder_path.split("/")[-1] if "/" in folder_path else folder_path
                    else:
                        # Use task_id as last resort
                        folder_name = f"Task-{task_id[-8:]}"
                
                logger.debug(f"Creating task {task_id} with folder_name: {folder_name}")
                
                self.create_task(
                    task_id=task_id,
                    folder_name=folder_name,
                    workflow_name=progress_data.get("workflow", "Unknown"),
                    plan_name=progress_data.get("plan", "Unknown"),
                    source=progress_data.get("source", "unknown"),
                    worker=progress_data.get("worker", "unknown"),
                    executor_type=progress_data.get("executor_type", "unknown"),
                    start_time=datetime.now(),
                    document_id=document_id  # Extract document_id from progress data
                )
            else:
                # Task already exists - DON'T overwrite folder_name
                existing_task = self.tasks[task_id]
                logger.debug(f"Task {task_id} already exists with folder_name: {existing_task.folder_name}")
                
                # Initialize workflow steps if provided
                if "workflow_steps" in progress_data:
                    self.set_workflow_steps(task_id, progress_data["workflow_steps"])
            
            # Handle different types of progress events
            event_type = progress_data.get("event_type", "task_update")
            
            if event_type == "workflow_start":
                logger.debug(f"Setting task {task_id} status to 'running'")
                self.update_task(task_id, status="running", start_time=datetime.now())
                if "workflow_steps" in progress_data:
                    self.set_workflow_steps(task_id, progress_data["workflow_steps"])
            
            elif event_type == "step_start":
                step_name = progress_data.get("step")
                if step_name:
                    self.start_step(task_id, step_name)
            
            elif event_type == "step_complete":
                step_name = progress_data.get("step")
                success = progress_data.get("success", True)
                result = progress_data.get("result", {})
                error = progress_data.get("error", "")
                if step_name:
                    self.complete_step(task_id, step_name, success, result, error)
            
            elif event_type == "workflow_complete":
                success = progress_data.get("success", True)
                error_msg = progress_data.get("error", "")
                folder_name = progress_data.get("folder_name", "")
                self.complete_task(task_id, success, error_msg, folder_name)
            
            else:
                # Generic task update (backward compatibility) - but don't override workflow events
                updates = {}
                if "progress" in progress_data:
                    updates["overall_progress"] = progress_data["progress"]
                if "current_step" in progress_data:
                    updates["current_step"] = progress_data["current_step"]
                if "total_steps" in progress_data:
                    updates["total_steps"] = progress_data["total_steps"]
                if "completed_steps" in progress_data:
                    updates["completed_steps"] = progress_data["completed_steps"]
                if "error" in progress_data:
                    updates["error_message"] = progress_data["error"]
                if "worker" in progress_data:
                    updates["worker"] = progress_data["worker"]
                if "executor_type" in progress_data:
                    updates["executor_type"] = progress_data["executor_type"]
                
                # Try to update folder name if we have better information
                if task_id in self.tasks:
                    current_task = self.tasks[task_id]
                    if current_task.folder_name.startswith("Task-") or current_task.folder_name in ["unknown", "Processing..."]:
                        # Check for folder_name first (from folder_processor)
                        if "folder_name" in progress_data and progress_data["folder_name"]:
                            new_folder_name = progress_data["folder_name"]
                            updates["folder_name"] = new_folder_name
                        else:
                            # Fall back to extracting from folder path
                            folder_path = progress_data.get("folder", progress_data.get("input_folder", ""))
                            if folder_path:
                                new_folder_name = folder_path.split("/")[-1] if "/" in folder_path else folder_path
                                updates["folder_name"] = new_folder_name
                
                # Only update status if we haven't received workflow events yet
                # This prevents generic status updates from overriding workflow events
                if "status" in progress_data:
                    current_task = self.tasks.get(task_id)
                    if current_task and current_task.status in ["pending", "submitted"]:
                        logger.debug(f"Updating task {task_id} status to '{progress_data['status']}' (no workflow events yet)")
                        updates["status"] = progress_data["status"]
                    else:
                        logger.debug(f"Ignoring generic status update '{progress_data['status']}' for task {task_id} (workflow events in progress)")
                
                if updates:
                    self.update_task(task_id, **updates)
                
                # Only complete task if we haven't received workflow events
                if progress_data.get("status") in ["completed", "failed", "cancelled"]:
                    current_task = self.tasks.get(task_id)
                    if current_task and current_task.status in ["pending", "submitted"]:
                        success = progress_data.get("status") == "completed"
                        error_msg = progress_data.get("error", "")
                        folder_name = progress_data.get("folder_name", "")
                        logger.debug(f"Completing task {task_id} via generic status update")
                        self.complete_task(task_id, success, error_msg, folder_name)
                    else:
                        logger.debug(f"Ignoring generic completion for task {task_id} (workflow events in progress)")
                
        except Exception as e:
            logger.warning(f"Failed to process progress update: {e}")

    def cleanup_old_failed_tasks(self, max_age_minutes: int = 10):
        """Move old failed tasks to completed history"""
        with self._task_lock:
            cutoff_time = datetime.now() - timedelta(minutes=max_age_minutes)
            failed_tasks = [tid for tid, task in self.tasks.items() if task.status == "failed"]
            
            for task_id in failed_tasks:
                task = self.tasks[task_id]
                if task.end_time and task.end_time < cutoff_time:
                    # Move to completed history
                    completed_task = self.tasks.pop(task_id)
                    self.completed_tasks.append(completed_task)
                    logger.info(f"Moved old failed task to history: {task_id}")
            
            # Limit history size
            if len(self.completed_tasks) > self.max_completed_history:
                self.completed_tasks = self.completed_tasks[-self.max_completed_history:]

    def clear_old_history(self, max_age_hours: int = 1):
        """Clear old completed tasks from history"""
        with self._task_lock:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            old_tasks = [t for t in self.completed_tasks if t.end_time and t.end_time < cutoff_time]
            
            for task in old_tasks:
                self.completed_tasks.remove(task)
            
            if old_tasks:
                logger.info(f"Cleared {len(old_tasks)} old tasks from history")
    
    def clear_all_history(self):
        """Clear all completed task history"""
        with self._task_lock:
            count = len(self.completed_tasks)
            self.completed_tasks.clear()
            logger.info(f"Cleared all {count} completed tasks from history")
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics for current session only (last hour)"""
        with self._task_lock:
            # Only count tasks from the last hour
            cutoff_time = datetime.now() - timedelta(hours=1)
            
            # Current active tasks
            active_count = len([t for t in self.tasks.values() if t.is_active])
            
            # Recent completed tasks (last hour)
            recent_completed = [
                t for t in self.completed_tasks 
                if t.end_time and t.end_time > cutoff_time and t.status == "completed"
            ]
            
            # Recent failed tasks (last hour)
            recent_failed = [
                t for t in self.completed_tasks 
                if t.end_time and t.end_time > cutoff_time and t.status == "failed"
            ]
            
            # Current session tasks (active + recent)
            session_tasks = [t for t in self.tasks.values()] + recent_completed + recent_failed
            
            # Performance metrics for recent tasks
            avg_duration = 0
            if recent_completed:
                durations = [t.duration.total_seconds() for t in recent_completed]
                avg_duration = sum(durations) / len(durations)
            
            return {
                "active_tasks": active_count,
                "session_tasks": len(session_tasks),
                "completed_tasks": len(recent_completed),
                "failed_tasks": len(recent_failed),
                "average_duration": avg_duration,
                "last_updated": datetime.now()
            }
    
    def create_display_data(self, document_id: Optional[str] = None) -> List[Dict[str, str]]:
        """Create simple display data for both CLI and GUI with nice formatting"""
        # Use timeout to prevent deadlocks
        if not self._task_lock.acquire(timeout=0.5):
            logger.warning("Timeout acquiring task lock for display data")
            return []
        
        try:
            if document_id:
                tasks = self.get_tasks_by_document(document_id)
            else:
                tasks = self.get_all_tasks()
            
            display_data = []
            for task in tasks.values():
                # Determine worker type suffix
                if task.executor_type == "io":
                    worker_suffix = " " + _("task_worker_efficiency")
                elif task.executor_type == "cpu":
                    worker_suffix = ""  # Performance Worker is default for Python
                elif task.executor_type == "celery":
                    worker_suffix = " " + _("task_worker_celery")
                elif task.executor_type == "celery_io":
                    worker_suffix = " " + _("task_worker_celery_efficiency")
                else:  # Unknown
                    worker_suffix = ""
                
                # Create clean status messages with duration
                duration_str = format_duration(task.duration)
                
                if task.status == "running":
                    spinner = get_spinner_frame('circle')
                    if task.current_step:
                        action_verb = get_step_verb(task.current_step, task.status)
                        step_name = task.current_step.replace("_", " ").title()
                        status_text = f"{spinner} {action_verb} {step_name}{worker_suffix} ({duration_str})"
                    else:
                        status_text = f"{spinner} {_('task_status_processing_duration').format(duration=duration_str)}"
                        
                elif task.status in ["pending", "submitted"]:
                    if task.executor_type == "io":
                        status_text = "○ " + _("task_status_waiting_efficiency")
                    elif task.executor_type == "cpu":
                        status_text = "○ " + _("task_status_waiting_performance")  # Performance Worker is default
                    elif task.executor_type == "celery":
                        status_text = "○ " + _("task_status_waiting_celery")
                    elif task.executor_type == "celery_io":
                        status_text = "○ " + _("task_status_waiting_celery_efficiency")
                    else:  # Unknown
                        status_text = "○ " + _("task_status_waiting")
                        
                elif task.status == "completed":
                    status_text = f"✓ {_('task_status_completed_duration').format(duration=duration_str)}"
                        
                elif task.status == "failed":
                    status_text = f"✗ {_('task_status_failed_duration').format(duration=duration_str)}"
                        
                elif task.status == "cancelled":
                    status_text = f"■ {_('task_status_cancelled_duration').format(duration=duration_str)}"
                    
                else:
                    status_text = f"○ {get_status_text(task.status)}"
                
                display_data.append({
                    "folder": task.folder_name,
                    "status": status_text,
                    "task_id": task.task_id
                })
            
            # Sort by status priority first, then by creation order (processing order)
            def sort_key(item):
                task = tasks[item["task_id"]]
                # Status priority: running=0, pending=1, failed=2, completed=3, cancelled=4
                status_priority = {
                    "running": 0,
                    "pending": 1, 
                    "submitted": 1,
                    "failed": 2,
                    "completed": 3,
                    "cancelled": 4
                }.get(task.status, 5)
                
                # Within same status, sort by creation time (processing order)
                return (status_priority, task.created_at)
            
            display_data.sort(key=sort_key)
            return display_data
        finally:
            self._task_lock.release()
    
    def get_status_summary(self, document_id: Optional[str] = None) -> str:
        """Get simple status summary with icons"""
        # Use timeout to prevent deadlocks
        if not self._task_lock.acquire(timeout=0.5):
            logger.warning("Timeout acquiring task lock for status summary")
            return _("task_table_error")
        
        try:
            if document_id:
                tasks = self.get_tasks_by_document(document_id)
            else:
                tasks = self.get_all_tasks()
            
            if not tasks:
                return _("task_table_no_active")
            
            stats = self.get_stats()
            parts = []
            
            if stats["active_tasks"] > 0:
                parts.append(f"● {_('task_table_active_count').format(count=stats['active_tasks'])}")
            if stats["completed_tasks"] > 0:
                parts.append(f"✓ {_('task_table_completed_count').format(count=stats['completed_tasks'])}")
            if stats["failed_tasks"] > 0:
                parts.append(f"✗ {_('task_table_failed_count').format(count=stats['failed_tasks'])}")
            
            if not parts:
                parts.append(_("task_table_ready"))
            
            return _("task_status_summary_separator").join(parts)
        finally:
            self._task_lock.release()
    
    def get_all_tasks_completion_status(self, document_id: Optional[str] = None) -> tuple[bool, int]:
        """
        Check if all tasks are completed and return completion count.
        
        Args:
            document_id: Optional document ID to filter tasks
            
        Returns:
            Tuple of (all_completed, completed_count)
        """
        # Use timeout to prevent deadlocks
        if not self._task_lock.acquire(timeout=0.5):
            logger.warning("Timeout acquiring task lock for completion status")
            return True, 0
        
        try:
            if document_id:
                tasks = self.get_tasks_by_document(document_id)
            else:
                tasks = self.get_all_tasks()
            
            if not tasks:
                return True, 0  # No tasks means all completed
            
            completed_count = 0
            total_count = len(tasks)
            
            for task in tasks.values():
                if task.status in ["completed", "failed", "cancelled"]:
                    completed_count += 1
            
            all_completed = completed_count == total_count
            return all_completed, completed_count
        finally:
            self._task_lock.release()
    
    def reset(self):
        """Reset the task monitor - clear all tasks and history"""
        with self._task_lock:
            self.tasks.clear()
            self.completed_tasks.clear()
            logger.info("TaskMonitor reset - cleared all tasks and history")

    def get_backend_info(self) -> Dict[str, Any]:
        """Get backend status information"""
        if not self.director:
            return {"status": "unavailable", "error": "No director"}
        
        try:
            backend = self.director.backend
            return {
                "backend_name": backend.backend_name,
                "is_initialized": backend.is_initialized,
                "status": "healthy" if backend.is_initialized else "unhealthy",
                "timestamp": datetime.now()
            }
        except Exception as e:
            logger.error(f"Failed to get backend info: {e}")
            return {"status": "error", "error": str(e)} 