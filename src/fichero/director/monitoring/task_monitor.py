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

logger = logging.getLogger(__name__)


@dataclass
class StepInfo:
    """Information about a workflow step"""
    step_name: str
    status: str = "pending"           # pending, running, completed, failed
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
        """Get status icon for step"""
        icons = {
            "pending": "○",
            "running": "·",  # Will be animated by spinner if needed
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
    instance_id: str = "unknown"            # "gui_app", "cli_session_x"
    source: str = "unknown"                 # "gui", "cli", "standalone"
    
    # Processing Details
    plan_name: str = "unknown"
    workflow_name: str = "unknown"
    input_folder: str = ""
    output_folder: str = ""
    folder_name: str = "unknown"            # Just the folder name for display
    worker: str = "unknown"                 # Worker ID processing this task
    executor_type: str = "unknown"          # Type of executor (cpu, io, celery)
    
    # Progress - Task Level
    current_step: str = ""
    total_steps: int = 1
    completed_steps: int = 0
    overall_progress: float = 0.0           # 0-100 overall
    
    # Progress - Step Level
    steps: Dict[str, StepInfo] = field(default_factory=dict)
    step_names: List[str] = field(default_factory=list)  # Ordered list of step names
    
    # Status
    status: str = "pending"                 # pending, running, completed, failed, cancelled
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
        """Get status icon for display"""
        icons = {
            "pending": "○",
            "running": "·",  # Will be animated by spinner
            "completed": "●",
            "failed": "✗",
            "cancelled": "⏹"
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
    
    def complete_task(self, task_id: str, success: bool = True, error_message: str = ""):
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
            
            # For successful tasks, move to completed history immediately
            if success:
                completed_task = self.tasks.pop(task_id)
                self.completed_tasks.append(completed_task)
                
                # Limit history size
                if len(self.completed_tasks) > self.max_completed_history:
                    self.completed_tasks = self.completed_tasks[-self.max_completed_history:]
                
                self._notify_callbacks('task_completed', completed_task)
                logger.info(f"Task completed: {task_id}")
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
        with self._task_lock:
            all_tasks = dict(self.tasks)
            for task in self.completed_tasks:
                all_tasks[task.task_id] = task
            return all_tasks
    
    def get_tasks_by_document(self, document_id: str) -> Dict[str, TaskInfo]:
        """Get tasks for specific document"""
        with self._task_lock:
            return {
                tid: task for tid, task in self.tasks.items() 
                if task.document_id == document_id
            }
    
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
        with self._task_lock:
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
            # Debug logging
            logger.debug(f"Progress update for task {task_id}: {progress_data}")
            
            # Create task if it doesn't exist
            if task_id not in self.tasks:
                self.create_task(
                    task_id=task_id,
                    folder_name=progress_data.get("folder", "Unknown"),
                    workflow_name=progress_data.get("workflow", "Unknown"),
                    plan_name=progress_data.get("plan", "Unknown"),
                    source=progress_data.get("source", "unknown"),
                    worker=progress_data.get("worker", "unknown"),
                    executor_type=progress_data.get("executor_type", "unknown"),
                    start_time=datetime.now(),
                    document_id=progress_data.get("document_id")  # Extract document_id from progress data
                )
                
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
                self.complete_task(task_id, success, error_msg)
            
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
                        logger.debug(f"Completing task {task_id} via generic status update")
                        self.complete_task(task_id, success, error_msg)
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