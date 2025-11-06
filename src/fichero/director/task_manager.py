"""
Task Manager for Document Processing

Coordinates task submission and monitoring with backends.
"""

import logging
import threading
import time
import uuid
from typing import Dict, List, Optional, Callable
from pathlib import Path

from fichero.director.backends.implementations.base import ProcessingBackend, FolderTask, ProcessingResult, ProcessingStatus, create_folder_task
from fichero.director.enums import TaskPriority

logger = logging.getLogger(__name__)


class TaskManager:
    """
    Simple task manager that coordinates with backends.
    
    Features:
    - Task submission and tracking
    - Progress callbacks
    - Simple statistics
    """
    
    def __init__(self, backend: ProcessingBackend):
        self.backend = backend
        self.active_tasks: Dict[str, FolderTask] = {}
        self.progress_callbacks: List[Callable] = []
        
        # Task statistics
        self.stats = {
            "total_submitted": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_cancelled": 0
        }
        
        self._lock = threading.Lock()
        
        # Set up backend progress callback
        self.backend.set_progress_callback(self._backend_progress_callback)
    
    def start(self):
        """Start the task manager"""
        logger.info("TaskManager started")
    
    def stop(self):
        """Stop the task manager"""
        logger.info("TaskManager stopped")
    
    def submit_task(self, folders, plan_config: Dict, workflow_name: str,
                   variables: Dict = None, priority: TaskPriority = TaskPriority.NORMAL,
                   document_context: Dict = None, skip_processing: bool = False) -> str:
        """
        Submit a new processing task

        Args:
            folders: List of prepared folder paths OR dicts with 'output_folder' and 'documents_folder'
            plan_config: Plan configuration
            workflow_name: Name of workflow to run
            variables: Additional variables for workflow
            priority: Task priority level (not used in simple version)
            document_context: Context from document window (optional)
            skip_processing: If True, create empty files instead of processing (default: False)

        Returns:
            Task ID string
        """
        if not folders:
            raise ValueError("No folders provided")

        # Create tasks for each prepared folder
        tasks = []
        for prepared_folder in folders:
            # Debug logging for document_id
            document_id = document_context.get('document_id') if document_context else None

            # Handle both dict format (new) and Path format (legacy)
            if isinstance(prepared_folder, dict):
                # New format: dict with output_folder and documents_folder
                output_folder = prepared_folder['output_folder']
                documents_folder = prepared_folder['documents_folder']
                logger.debug(f"TaskManager.submit_task: dict format - output={output_folder}, documents={documents_folder}, document_id={document_id}")
            else:
                # Legacy format: Path object (output folder with documents/ inside)
                output_folder = prepared_folder
                documents_folder = None  # Will default to output_folder/documents in FolderTask
                logger.debug(f"TaskManager.submit_task: Path format - folder={prepared_folder}, document_id={document_id}")

            # Extract display_name from document_context if provided (for single file processing)
            display_name = document_context.get('display_name') if document_context else None

            # Create task with both folders
            task = create_folder_task(
                folder_path=output_folder,
                output_path=output_folder,
                documents_folder=documents_folder,
                plan_config=plan_config,
                workflow_name=workflow_name,
                variables=variables or {},
                document_id=document_id,
                display_name=display_name
            )
            tasks.append(task)
            logger.info(f"Created task for output folder: {output_folder} (documents: {documents_folder or 'default'})")
        
        # Submit to backend
        results = self.backend.process_folders(tasks, skip_processing=skip_processing)
        
        # Track tasks
        with self._lock:
            for task in tasks:
                self.active_tasks[task.task_id] = task
                self.stats["total_submitted"] += 1
        
        # Note: Backend will automatically send progress updates with folder_name
        # No need for immediate progress updates since Python backend includes folder_name in all events
        
        # Return first task ID (for compatibility)
        first_task_id = tasks[0].task_id if tasks else None
        
        logger.info(f"Submitted {len(tasks)} tasks, first task ID: {first_task_id}")
        return first_task_id
    
    def get_task_status(self, task_id: str) -> Optional[ProcessingStatus]:
        """Get current status of a task"""
        return self.backend.get_status(task_id)
    
    def get_task_result(self, task_id: str) -> Optional[ProcessingResult]:
        """Get result of a completed task"""
        return self.backend.get_result(task_id)
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task"""
        success = self.backend.cancel_task(task_id)
        if success:
            with self._lock:
                self.stats["total_cancelled"] += 1
                self.active_tasks.pop(task_id, None)
        return success
    
    def list_active_tasks(self) -> List[str]:
        """List all currently active task IDs"""
        return self.backend.list_active_tasks()
    
    def get_stats(self) -> Dict:
        """Get task manager statistics"""
        with self._lock:
            return {
                **self.stats,
                "active_tasks": len(self.active_tasks),
                "backend_type": self.backend.backend_name
            }
    
    def register_progress_callback(self, callback: Callable):
        """Register callback for progress updates"""
        self.progress_callbacks.append(callback)
    
    def _backend_progress_callback(self, task_id: str, progress_data: Dict):
        """Handle progress updates from backend"""
        # Update statistics based on status
        status = progress_data.get('status')
        if status == 'completed':
            with self._lock:
                self.stats["total_completed"] += 1
                self.active_tasks.pop(task_id, None)
        elif status == 'failed':
            with self._lock:
                self.stats["total_failed"] += 1
                self.active_tasks.pop(task_id, None)
        elif status == 'cancelled':
            with self._lock:
                self.stats["total_cancelled"] += 1
                self.active_tasks.pop(task_id, None)
        
        # Notify all registered callbacks
        for callback in self.progress_callbacks:
            try:
                callback(task_id, progress_data)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}") 