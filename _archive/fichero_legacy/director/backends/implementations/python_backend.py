"""
Python Processing Backend

Simple Python-based processing backend for Fichero.
Uses ThreadPoolExecutor for concurrent processing.
"""

import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
import queue

# Conditional imports for iOS compatibility
try:
    import multiprocessing
    MULTIPROCESSING_AVAILABLE = True
except ImportError:
    MULTIPROCESSING_AVAILABLE = False
    # Create fallback for multiprocessing functionality
    class multiprocessing:
        @staticmethod
        def cpu_count():
            # Fallback to a reasonable default for iOS
            return 2

from fichero.director.backends.implementations.base import (
    ProcessingBackend, FolderTask, ProcessingResult, ProcessingStatus
)
from fichero.director.enums import TaskPriority
from fichero.director.folder_processor import FolderProcessor

logger = logging.getLogger(__name__)


class PythonProcessingBackend(ProcessingBackend):
    """
    Python backend using ThreadPoolExecutor for both CPU and IO tasks.
    
    Features:
    - ThreadPoolExecutor for CPU-intensive work (libraries release GIL)
    - ThreadPoolExecutor for IO-bound work (handles more concurrent tasks)
    - Intelligent task routing based on workflow characteristics
    - Progress tracking via callback
    - Safe for Mac GUI use with no subprocesses
    """
    
    def __init__(self, app=None, cpu_workers: int = None, io_workers: int = None):
        super().__init__(app)
        self.backend_name = "python"
        
        # Get worker configuration from app settings if available
        if app and (hasattr(app, 'settings') or isinstance(app, dict)):
            try:
                try:
                    from fichero.config.core.settings import get_app_settings
                except ImportError:
                    from fichero.config.core.settings import get_app_settings
                logger.info(f"Loading worker settings from app: {type(app)}")
                
                # Handle both app object and settings dict
                if isinstance(app, dict):
                    # App is already the settings dictionary
                    workers_config = app.get('workers', {})
                    cpu_from_settings = workers_config.get('cpu_workers', 4)
                    io_from_settings = workers_config.get('io_workers', 8)
                    logger.info(f"Direct settings returned: CPU={cpu_from_settings}, IO={io_from_settings}")
                else:
                    # App is an app object, get settings via get_app_settings
                    app_settings = get_app_settings(app)
                    if app_settings:
                        cpu_from_settings = app_settings.get_cpu_workers()
                        io_from_settings = app_settings.get_io_workers()
                        logger.info(f"App settings returned: CPU={cpu_from_settings}, IO={io_from_settings}")
                    else:
                        raise Exception("get_app_settings returned None")
                
                # Use settings from app configuration
                self.cpu_workers = cpu_workers or cpu_from_settings
                self.io_workers = io_workers or io_from_settings
                logger.info(f"Using worker configuration from app settings: {self.cpu_workers} CPU, {self.io_workers} IO")
            except Exception as e:
                logger.warning(f"Could not load worker settings from app: {e}")
                self._set_default_workers(cpu_workers, io_workers)
        else:
            logger.info(f"No app context (app={app}, has_settings={hasattr(app, 'settings') if app else False}), using defaults")
            # No app context, use calculated defaults
            self._set_default_workers(cpu_workers, io_workers)
        
        # ThreadPoolExecutor for both CPU and IO tasks (Mac app compatible)
        self.cpu_executor: Optional[ThreadPoolExecutor] = None  # Changed to ThreadPoolExecutor
        self.io_executor: Optional[ThreadPoolExecutor] = None
        
        # Task tracking
        self.active_tasks: Dict[str, ProcessingStatus] = {}
        self.task_results: Dict[str, ProcessingResult] = {}
        self.task_futures: Dict[str, any] = {}
        self.task_executor_types: Dict[str, str] = {}  # Track which executor type each task uses
        self.task_executors: Dict[str, any] = {}  # Track workflow executors for cancellation
        self.task_document_ids: Dict[str, str] = {}  # Track document_id for each task
        self.task_display_names: Dict[str, str] = {}  # Track display_name for each task (for Activity Monitor)
        self._lock = threading.Lock()
        
        self._initialized = False
        self._progress_callback = None
        logger.info(f"System has {multiprocessing.cpu_count()} CPU cores")
        logger.info(f"Configured with {self.cpu_workers} CPU workers (ThreadPool) and {self.io_workers} IO workers (ThreadPool)")
        logger.info(f"ThreadPool will use libraries that release GIL for CPU-intensive tasks")
    
    @property
    def is_initialized(self) -> bool:
        """Check if backend is initialized"""
        return self._initialized
    
    def initialize(self) -> bool:
        """Initialize the backend"""
        try:
            # Python backend is always ready - no external dependencies
            self._initialized = True
            logger.info("Python backend ready")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Python backend: {e}")
            return False
    
    def set_progress_callback(self, callback):
        """Set progress callback function"""
        self._progress_callback = callback
    
    def _notify_progress(self, task_id: str, progress_data: Dict):
        """Notify progress callback if set"""
        if self._progress_callback:
            try:
                self._progress_callback(task_id, progress_data)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")
    
    def _notify_progress_with_worker(self, task_id: str, progress_data: Dict, worker_id: str):
        """Notify progress callback with worker information"""
        if self._progress_callback:
            try:
                # Add worker information to progress data
                enhanced_data = {**progress_data, "worker": worker_id}
                self._progress_callback(task_id, enhanced_data)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")
    
    def _notify_progress_with_worker_and_document(self, task_id: str, progress_data: Dict, worker_id: str, document_id: str = None):
        """Notify progress callback with worker and document information"""
        if self._progress_callback:
            try:
                # Add worker and document information to progress data
                enhanced_data = {**progress_data, "worker": worker_id}
                if document_id:
                    enhanced_data["document_id"] = document_id
                self._progress_callback(task_id, enhanced_data)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")
    
    @property
    def supports_async(self) -> bool:
        return True  # We support submit + check status
    
    @property  
    def supports_multiple_instances(self) -> bool:
        return True  # Multiple CLI instances can use separate Python processes
    
    @property
    def requires_external_services(self) -> bool:
        return False  # Pure Python, no Redis/Celery needed
    
    def process_folders(self, tasks: List[FolderTask]) -> Dict[str, ProcessingResult]:
        """
        Process folders asynchronously and return immediately.
        Use get_status() and get_result() to check progress.

        Args:
            tasks: List of FolderTask objects to process
        """
        if not tasks:
            return {}
        
        # Start executors if needed
        if self.cpu_executor is None:
            # Use ThreadPoolExecutor for CPU-intensive work (libraries release GIL)
            self.cpu_executor = ThreadPoolExecutor(max_workers=self.cpu_workers, thread_name_prefix="fichero-cpu")
            logger.info(f"Created CPU executor (ThreadPool) with {self.cpu_workers} workers")
            logger.info(f"CPU executor object: {self.cpu_executor}")
        
        if self.io_executor is None:
            # Use ThreadPoolExecutor for IO-bound work (more efficient for waiting)
            self.io_executor = ThreadPoolExecutor(max_workers=self.io_workers, thread_name_prefix="fichero-io")
            logger.info(f"Created IO executor (ThreadPool) with {self.io_workers} workers")
            logger.info(f"IO executor object: {self.io_executor}")
            
            # Force creation of worker threads by submitting a dummy task
            logger.info("Pre-warming IO executor with dummy task...")
            dummy_future = self.io_executor.submit(lambda: None)
            dummy_future.result()  # Wait for completion
            logger.info("IO executor pre-warmed")
        
        results = {}
        
        with self._lock:
            for task in tasks:
                # Set initial status
                self.active_tasks[task.task_id] = ProcessingStatus.PENDING

                # Store document_id for later use in completion notifications
                if task.document_id:
                    self.task_document_ids[task.task_id] = task.document_id

                # Store display_name for Activity Monitor display
                if task.display_name:
                    self.task_display_names[task.task_id] = task.display_name

                # Determine which executor to use based on workflow characteristics
                executor, executor_type = self._get_executor_for_task(task)
                
                logger.info(f"Task {task.task_id} assigned to {executor_type} executor (workflow: {task.workflow_name})")
                
                # Submit to appropriate executor (both use ThreadPool now)
                # Use consistent execution method for both CPU and IO tasks
                future = executor.submit(self._execute_single_folder, task)
                    
                self.task_futures[task.task_id] = future
                self.task_executor_types[task.task_id] = executor_type  # Store executor type
                
                # Log executor status
                logger.info(f"Task {task.task_id} submitted to {executor_type} executor")
                logger.info(f"  Executor: {executor}")
                logger.info(f"  Max workers: {executor._max_workers}")
                
                # Notify progress with placeholder worker information
                progress_data = {
                    "status": "submitted",
                    "folder": str(task.folder_path),
                    "folder_name": task.display_name or task.folder_path.name,  # Use display_name if available, else folder name
                    "workflow": task.workflow_name,
                    "plan": task.plan_config.get('name', 'Unknown') if task.plan_config else 'Unknown',
                    "executor_type": executor_type,
                    "worker": f"{executor_type.upper()}-pending"
                }
                
                # Add document_id if available
                if task.document_id:
                    progress_data["document_id"] = task.document_id
                
                self._notify_progress(task.task_id, progress_data)
                
                logger.info(f"Submitted task {task.task_id} to {executor_type} executor for folder: {task.folder_path}")
        
        return results  # Empty for async backend
    
    def _get_executor_for_task(self, task: FolderTask) -> tuple[any, str]:
        """Determine which executor to use based on task characteristics"""
        try:
            # Analyze the workflow to determine predominant worker type
            workflows = task.plan_config.get('workflows', {})
            commands = {cmd['name']: cmd for cmd in task.plan_config.get('commands', [])}
            
            if task.workflow_name in workflows:
                workflow_steps = workflows[task.workflow_name]
                cpu_intensive_steps = 0
                io_bound_steps = 0
                
                logger.info(f"Analyzing workflow '{task.workflow_name}' with {len(workflow_steps)} steps")
                
                for step_name in workflow_steps:
                    if step_name in commands:
                        worker_type = commands[step_name].get('worker_type', 'cpu')
                        
                        # More intelligent classification based on step names and types
                        if (worker_type == 'cpu' or 
                            any(keyword in step_name.lower() for keyword in 
                                ['crop', 'enhance', 'rotate', 'split', 'remove_background', 'segment'])):
                            cpu_intensive_steps += 1
                        else:
                            io_bound_steps += 1
                            
                        logger.info(f"  Step '{step_name}' classified as {'cpu-intensive' if worker_type == 'cpu' else 'io-bound'} (cpu: {cpu_intensive_steps}, io: {io_bound_steps})")
                    else:
                        logger.warning(f"  Step '{step_name}' not found in commands, defaulting to io-bound")
                        io_bound_steps += 1
                
                # Use ThreadPool for CPU-intensive workflows, ThreadPool for IO-bound
                if cpu_intensive_steps > io_bound_steps:
                    logger.info(f"Workflow '{task.workflow_name}' classified as CPU-intensive ({cpu_intensive_steps} cpu vs {io_bound_steps} io steps) → ThreadPool")
                    return self.cpu_executor, "cpu"
                else:
                    logger.info(f"Workflow '{task.workflow_name}' classified as IO-bound ({io_bound_steps} io vs {cpu_intensive_steps} cpu steps) → ThreadPool")
                    return self.io_executor, "io"
            
            # Default to IO executor for unknown workflows (safer for app responsiveness)
            logger.info(f"Unknown workflow '{task.workflow_name}', defaulting to IO executor")
            return self.io_executor, "io"
            
        except Exception as e:
            logger.warning(f"Error determining executor for task {task.task_id}: {e}")
            return self.io_executor, "io"  # Safe default
    
    def _get_parallel_workers_for_task(self, task: FolderTask) -> int:
        """Determine how many parallel workers to allow for this task based on current load"""
        with self._lock:
            # Clean up completed tasks first to prevent stale entries affecting count
            # and to prevent unbounded dictionary growth
            completed_statuses = [ProcessingStatus.COMPLETED, ProcessingStatus.FAILED, ProcessingStatus.CANCELLED]
            stale_count = len([t for t, status in self.active_tasks.items() if status in completed_statuses])
            if stale_count > 0:
                self.active_tasks = {
                    task_id: status
                    for task_id, status in self.active_tasks.items()
                    if status not in completed_statuses
                }
                logger.debug(f"Cleaned up {stale_count} completed tasks from active_tasks")

            # Count currently active tasks (after cleanup, all should be PENDING or RUNNING)
            active_count = len(self.active_tasks)
            
            # Conservative parallelism strategy for ThreadPoolExecutor
            if active_count <= 1:
                # Single folder: Use full parallelism
                parallel_workers = min(4, self.cpu_workers)  # Cap at 4 for tool-level parallelism
                logger.info(f"Single folder processing, enabling full parallel tool processing for task {task.task_id} ({parallel_workers} workers)")
            elif active_count <= 3:
                # Few folders: Use moderate parallelism
                parallel_workers = min(2, self.cpu_workers // 2)
                logger.info(f"Low load ({active_count} folders), enabling moderate parallel tool processing for task {task.task_id} ({parallel_workers} workers)")
            elif active_count <= 6:
                # Medium load: Use minimal parallelism
                parallel_workers = 1
                logger.info(f"Medium load ({active_count} folders), using minimal parallel tool processing for task {task.task_id}")
            else:
                # High load: Use sequential processing
                parallel_workers = 1
                logger.info(f"High load ({active_count} folders), using sequential tool processing for task {task.task_id}")
            
            return parallel_workers
    
    def get_status(self, task_id: str) -> ProcessingStatus:
        """Get current status of a task"""
        with self._lock:
            # Check if task completed
            if task_id in self.task_results:
                result = self.task_results[task_id]
                return ProcessingStatus.COMPLETED if result.success else ProcessingStatus.FAILED
            
            # Check future status
            if task_id in self.task_futures:
                future = self.task_futures[task_id]
                if future.cancelled():
                    self.active_tasks[task_id] = ProcessingStatus.CANCELLED
                    return ProcessingStatus.CANCELLED
                elif future.running():
                    self.active_tasks[task_id] = ProcessingStatus.RUNNING
                    return ProcessingStatus.RUNNING
                elif future.done():
                    # Future completed, process result
                    try:
                        result = future.result()
                        self.task_results[task_id] = result
                        
                        # Get the executor type from our stored mapping
                        executor_type = self.task_executor_types.get(task_id, "unknown")
                        worker_type = executor_type.upper()
                        
                        # Clean up tracking
                        del self.task_futures[task_id]
                        if task_id in self.task_executor_types:
                            del self.task_executor_types[task_id]
                        if task_id in self.task_executors:
                            del self.task_executors[task_id]  # Clean up task executor tracking

                        # Get stored document_id and display_name if available
                        document_id = self.task_document_ids.get(task_id)
                        display_name = self.task_display_names.get(task_id)

                        # Notify completion for ThreadPool tasks (they don't have callbacks)
                        if result.success:
                            self.active_tasks[task_id] = ProcessingStatus.COMPLETED
                            worker_id = f"{worker_type}-completed"

                            logger.info(f"Detected completed {worker_type} task: {task_id}")

                            # Notify completion
                            completion_data = {
                                "event_type": "workflow_complete",  # ADDED: Trigger TaskMonitor.complete_task()
                                "success": True,
                                "status": "completed",
                                "folder": str(result.folder_path),
                                "folder_name": display_name or result.folder_path.name,  # Use display_name if available, else folder name
                                "plan": "Unknown",  # We don't have access to plan_config here
                                "worker": worker_id,
                                "execution_time": result.execution_time,
                                "executor_type": executor_type
                            }
                            
                            # Add document_id if available
                            if document_id:
                                completion_data["document_id"] = document_id
                            
                            self._notify_progress(task_id, completion_data)

                            # Clean up document_id and display_name tracking
                            if task_id in self.task_document_ids:
                                del self.task_document_ids[task_id]
                            if task_id in self.task_display_names:
                                del self.task_display_names[task_id]

                            return ProcessingStatus.COMPLETED
                        else:
                            self.active_tasks[task_id] = ProcessingStatus.FAILED
                            worker_id = f"{worker_type}-failed"
                            
                            logger.error(f"Detected failed {worker_type} task: {task_id}")
                            
                            # Notify failure
                            failure_data = {
                                "event_type": "workflow_complete",  # ADDED: Trigger TaskMonitor.complete_task()
                                "success": False,
                                "error": result.error_message,
                                "status": "failed",
                                "folder": str(result.folder_path),
                                "folder_name": display_name or result.folder_path.name,  # Use display_name if available, else folder name
                                "plan": "Unknown",
                                "worker": worker_id,
                                "executor_type": executor_type
                            }
                            
                            # Add document_id if available
                            if document_id:
                                failure_data["document_id"] = document_id
                            
                            self._notify_progress(task_id, failure_data)

                            # Clean up document_id and display_name tracking
                            if task_id in self.task_document_ids:
                                del self.task_document_ids[task_id]
                            if task_id in self.task_display_names:
                                del self.task_display_names[task_id]

                            return ProcessingStatus.FAILED
                    except Exception as e:
                        # Create error result
                        error_msg = f"Error getting result for task {task_id}: {e}"
                        error_result = ProcessingResult(
                            task_id=task_id,
                            success=False,
                            folder_path=Path("unknown"),
                            output_path=Path("unknown"),
                            error_message=error_msg,
                            execution_time=0.0
                        )
                        self.task_results[task_id] = error_result
                        self.active_tasks[task_id] = ProcessingStatus.FAILED
                        del self.task_futures[task_id]
                        if task_id in self.task_executor_types:
                            del self.task_executor_types[task_id]  # Clean up executor type tracking
                        if task_id in self.task_executors:
                            del self.task_executors[task_id]  # Clean up task executor tracking

                        # Get stored document_id if available
                        document_id = self.task_document_ids.get(task_id)
                        
                        # Notify failure
                        error_data = {
                            "status": "failed",
                            "folder": "unknown",
                            "plan": "Unknown",
                            "worker": "unknown",
                            "error": error_msg
                        }
                        
                        # Add document_id if available
                        if document_id:
                            error_data["document_id"] = document_id
                        
                        self._notify_progress(task_id, error_data)

                        # Clean up document_id and display_name tracking
                        if task_id in self.task_document_ids:
                            del self.task_document_ids[task_id]
                        if task_id in self.task_display_names:
                            del self.task_display_names[task_id]

                        return ProcessingStatus.FAILED

            return self.active_tasks.get(task_id, ProcessingStatus.PENDING)
    
    def get_result(self, task_id: str) -> Optional[ProcessingResult]:
        """Get result of completed task"""
        with self._lock:
            return self.task_results.get(task_id)
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel specific task with timeout"""
        try:
            with self._lock:
                # Try to cancel the workflow executor first
                if hasattr(self, 'task_executors') and task_id in self.task_executors:
                    try:
                        executor = self.task_executors[task_id]
                        logger.info(f"Cancelling workflow executor for task: {task_id}")
                        executor.cancel()
                        logger.info(f"Successfully cancelled workflow executor for task: {task_id}")
                    except Exception as e:
                        logger.warning(f"Error cancelling workflow executor for task {task_id}: {e}")
                
                # Then cancel the future with shorter timeout
                if task_id in self.task_futures:
                    try:
                        future = self.task_futures[task_id]
                        
                        # Try to cancel the future
                        cancelled = future.cancel()
                        if cancelled:
                            self.active_tasks[task_id] = ProcessingStatus.CANCELLED
                            del self.task_futures[task_id]
                            if task_id in self.task_executor_types:
                                del self.task_executor_types[task_id]  # Clean up executor type tracking
                            if task_id in self.task_executors:
                                del self.task_executors[task_id]  # Clean up task executor tracking
                            if task_id in self.task_document_ids:
                                del self.task_document_ids[task_id]  # Clean up document_id tracking
                            if task_id in self.task_display_names:
                                del self.task_display_names[task_id]  # Clean up display_name tracking
                            logger.info(f"Successfully cancelled future for task: {task_id}")
                            return True
                        else:
                            # Future couldn't be cancelled, try to get result with very short timeout
                            logger.warning(f"Could not cancel future for task: {task_id}, waiting briefly...")
                            try:
                                # Wait for a very short time for the task to complete
                                result = future.result(timeout=0.5)  # Reduced to 0.5 second timeout
                                logger.info(f"Task {task_id} completed during cancellation")
                                return True
                            except Exception as timeout_error:
                                logger.warning(f"Task {task_id} did not complete within timeout, forcing removal")
                                # Force remove the future even if it's still running
                                del self.task_futures[task_id]
                                if task_id in self.task_executor_types:
                                    del self.task_executor_types[task_id]  # Clean up executor type tracking
                                if task_id in self.task_executors:
                                    del self.task_executors[task_id]  # Clean up task executor tracking
                                if task_id in self.task_document_ids:
                                    del self.task_document_ids[task_id]  # Clean up document_id tracking
                                if task_id in self.task_display_names:
                                    del self.task_display_names[task_id]  # Clean up display_name tracking
                                return True
                    except Exception as e:
                        logger.error(f"Error cancelling future for task {task_id}: {e}")
                        # Force remove the future even if there's an error
                        if task_id in self.task_futures:
                            del self.task_futures[task_id]
                        if task_id in self.task_executor_types:
                            del self.task_executor_types[task_id]  # Clean up executor type tracking
                        if task_id in self.task_executors:
                            del self.task_executors[task_id]  # Clean up task executor tracking
                        if task_id in self.task_document_ids:
                            del self.task_document_ids[task_id]  # Clean up document_id tracking
                        if task_id in self.task_display_names:
                            del self.task_display_names[task_id]  # Clean up display_name tracking
                        return False
                else:
                    logger.info(f"No future found for task: {task_id}")
                    return True  # Consider it cancelled if no future exists
        except Exception as e:
            logger.error(f"Error in cancel_task for {task_id}: {e}")
            return False
    
    def cancel_all(self) -> bool:
        """Cancel all processing with timeout"""
        cancelled_count = 0
        logger.info("Starting task cancellation...")
        
        try:
            # Try to acquire lock with timeout to prevent hanging
            import threading
            import time
            
            lock_acquired = False
            try:
                # Try to acquire lock with 2 second timeout
                lock_acquired = self._lock.acquire(timeout=2.0)
                if not lock_acquired:
                    logger.warning("Could not acquire lock for cancellation, forcing cleanup")
                    # Force cleanup without lock
                    self._force_cleanup_without_lock()
                    return True
            except Exception as e:
                logger.warning(f"Error acquiring lock for cancellation: {e}")
                # Force cleanup without lock
                self._force_cleanup_without_lock()
                return True
            
            try:
                task_ids = list(self.task_futures.keys())
                logger.info(f"Found {len(task_ids)} tasks to cancel")
                
                for task_id in task_ids:
                    try:
                        logger.info(f"Cancelling task: {task_id}")
                        if self.cancel_task(task_id):
                            cancelled_count += 1
                            logger.info(f"Successfully cancelled task: {task_id}")
                        else:
                            logger.warning(f"Failed to cancel task: {task_id}")
                    except Exception as e:
                        logger.error(f"Error cancelling task {task_id}: {e}")
                        # Continue with other tasks even if one fails
            finally:
                if lock_acquired:
                    self._lock.release()
        
        except Exception as e:
            logger.error(f"Error during cancel_all: {e}")
            # Force cleanup even if there's an error
            self._force_cleanup_without_lock()
        
        logger.info(f"Cancelled {cancelled_count} tasks")
        return cancelled_count > 0
    
    def _force_cleanup_without_lock(self):
        """Force cleanup without acquiring locks"""
        logger.info("Performing forced cleanup without locks...")
        try:
            # Force cancel all futures
            for task_id, future in list(getattr(self, 'task_futures', {}).items()):
                try:
                    if not future.done():
                        future.cancel()
                        logger.info(f"Forced cancellation of future for task: {task_id}")
                except Exception as e:
                    logger.warning(f"Error forcing cancellation of future for task {task_id}: {e}")
            
            # Clear all tracking dictionaries
            getattr(self, 'active_tasks', {}).clear()
            getattr(self, 'task_results', {}).clear()
            getattr(self, 'task_futures', {}).clear()
            getattr(self, 'task_executor_types', {}).clear()  # Clear executor types tracking
            getattr(self, 'task_executors', {}).clear()  # Clear task executors tracking
            getattr(self, 'task_document_ids', {}).clear()  # Clear document_id tracking
            getattr(self, 'task_display_names', {}).clear()  # Clear display_name tracking

            logger.info("Forced cleanup completed")
        except Exception as e:
            logger.error(f"Error during forced cleanup: {e}")
    
    def shutdown(self) -> bool:
        """Clean shutdown - stops all processing with timeout"""
        logger.info("Shutting down Python backend...")
        
        try:
            # Cancel all tasks first with timeout
            logger.info("Cancelling all tasks...")
            cancelled = self.cancel_all()
            logger.info(f"Task cancellation completed: {cancelled}")
            
            # Shutdown executors - ThreadPool needs special handling
            if self.cpu_executor:
                logger.info("Shutting down CPU executor (ThreadPool)...")
                try:
                    # ThreadPoolExecutor cleanup
                    self.cpu_executor.shutdown(wait=False, cancel_futures=True)
                    self.cpu_executor = None
                    logger.info("CPU executor shutdown completed")
                except Exception as e:
                    logger.warning(f"Error shutting down CPU executor: {e}")
                    self.cpu_executor = None
            
            if self.io_executor:
                logger.info("Shutting down IO executor (ThreadPool)...")
                try:
                    # ThreadPoolExecutor cleanup
                    self.io_executor.shutdown(wait=False, cancel_futures=True)
                    self.io_executor = None
                    logger.info("IO executor shutdown completed")
                except Exception as e:
                    logger.warning(f"Error shutting down IO executor: {e}")
                    self.io_executor = None
            
            # Clear tracking immediately
            logger.info("Clearing task tracking...")
            self._force_cleanup_without_lock()
            
            logger.info("Python backend shutdown complete")
            return True
            
        except Exception as e:
            logger.error(f"Error during Python backend shutdown: {e}")
            # Force cleanup even if there's an error
            try:
                logger.info("Performing forced cleanup...")
                if self.cpu_executor:
                    self.cpu_executor.shutdown(wait=False, cancel_futures=True)
                    self.cpu_executor = None
                if self.io_executor:
                    self.io_executor.shutdown(wait=False, cancel_futures=True)
                    self.io_executor = None
                # Force clear all tracking
                self._force_cleanup_without_lock()
                logger.info("Forced cleanup completed")
            except Exception as cleanup_error:
                logger.error(f"Error during forced cleanup: {cleanup_error}")
            return False
    
    def list_active_tasks(self) -> List[str]:
        """List active task IDs"""
        with self._lock:
            return list(self.active_tasks.keys())
    
    def _execute_single_folder(self, task: FolderTask) -> ProcessingResult:
        """Execute workflow on a single folder using ThreadPool executor"""
        
        try:
            # Update status
            with self._lock:
                self.active_tasks[task.task_id] = ProcessingStatus.RUNNING
            
            logger.info(f"Processing folder (ThreadPool): {task.folder_path}")
            
            # Determine executor type for this task
            executor_type = self.task_executor_types.get(task.task_id, "unknown")
            
            # Get current thread info for worker identification
            current_thread = threading.current_thread()
            worker_id = f"{executor_type.upper()}-{current_thread.ident % 1000}"
            
            logger.info(f"Task {task.task_id} running on {executor_type.upper()} worker: {worker_id} (thread: {current_thread.name})")
            
            # Create workflow executor with progress callback
            from fichero.director.workflow_executor import WorkflowExecutor
            executor = WorkflowExecutor(progress_callback=lambda task_id, data: self._notify_progress_with_worker_and_document(task_id, data, worker_id, task.document_id))
            
            # Store executor for cancellation support
            with self._lock:
                self.task_executors = getattr(self, 'task_executors', {})
                self.task_executors[task.task_id] = executor
            
            # Determine parallel workers based on current load
            parallel_workers = self._get_parallel_workers_for_task(task)

            # Add documents_folder to variables for source file access
            workflow_variables = task.variables.copy()
            workflow_variables['documents_folder'] = str(task.documents_folder)

            # Control /documents prefix in batch processing
            # The BatchProcessor adds "documents/" prefix unless:
            # 1. add_documents_prefix=False (explicit override), OR
            # 2. "documents" is already in base_folder path
            #
            # For both copy and in-place modes, documents_folder IS the actual location
            # We never want to add /documents/ prefix, so always disable it
            workflow_variables['add_documents_prefix'] = False

            # Execute workflow with full integration (including library IDs for metadata routing)
            result = executor.execute_workflow(
                task_id=task.task_id,
                folder_path=task.folder_path,
                output_path=task.output_path,
                workflow_name=task.workflow_name,
                plan_config=task.plan_config,
                variables=workflow_variables,
                parallel_workers=parallel_workers,
                # Library integration - stored in workflow_manifest.json for proper metadata routing
                library_item_id=task.library_item_id,
                library_collection_id=task.library_collection_id,
                library_item_map=task.library_item_map
            )
            
            # Clean up executor reference
            with self._lock:
                if hasattr(self, 'task_executors') and task.task_id in self.task_executors:
                    del self.task_executors[task.task_id]
            
            # Store result and update status
            with self._lock:
                self.task_results[task.task_id] = result
                if result.success:
                    self.active_tasks[task.task_id] = ProcessingStatus.COMPLETED
                    logger.info(f"Successfully processed folder (ThreadPool): {task.folder_path} ({result.execution_time:.1f}s)")
                    # Notify completion
                    self._notify_progress(task.task_id, {
                        "event_type": "workflow_complete",  # ADDED: Trigger TaskMonitor.complete_task()
                        "success": True,
                        "status": "completed",
                        "folder": str(task.folder_path),
                        "folder_name": task.display_name or task.folder_path.name,  # Use display_name if available, else folder name
                        "plan": task.plan_config.get('name', 'Unknown') if task.plan_config else 'Unknown',
                        "worker": worker_id,
                        "execution_time": result.execution_time,
                        "document_id": task.document_id
                    })
                else:
                    self.active_tasks[task.task_id] = ProcessingStatus.FAILED
                    logger.error(f"Failed to process folder (ThreadPool): {task.folder_path} - {result.error_message}")
                    # Notify failure
                    self._notify_progress(task.task_id, {
                        "event_type": "workflow_complete",  # ADDED: Trigger TaskMonitor.complete_task()
                        "success": False,
                        "error": result.error_message,
                        "status": "failed",
                        "folder": str(task.folder_path),
                        "folder_name": task.display_name or task.folder_path.name,  # Use display_name if available, else folder name
                        "plan": task.plan_config.get('name', 'Unknown') if task.plan_config else 'Unknown',
                        "worker": worker_id,
                        "document_id": task.document_id
                    })
            
            return result
            
        except Exception as e:
            error_msg = f"ThreadPool execution error: {e}"
            logger.error(f"Error processing folder (ThreadPool): {task.folder_path} - {e}")
            logger.exception("Folder processing exception")
            
            # Clean up executor reference
            with self._lock:
                if hasattr(self, 'task_executors') and task.task_id in self.task_executors:
                    del self.task_executors[task.task_id]
            
            # Create and store error result
            error_result = ProcessingResult(
                task_id=task.task_id,
                success=False,
                folder_path=task.folder_path,
                output_path=task.output_path,
                error_message=error_msg,
                execution_time=0.0
            )
            
            # Store result and update status
            with self._lock:
                self.task_results[task.task_id] = error_result
                self.active_tasks[task.task_id] = ProcessingStatus.FAILED
            
            # Notify failure with consistent worker ID
            current_thread = threading.current_thread()
            worker_id = f"UNKNOWN-{current_thread.ident % 1000}"
            self._notify_progress(task.task_id, {
                "event_type": "workflow_complete",  # ADDED: Trigger TaskMonitor.complete_task()
                "success": False,
                "error": error_msg,
                "status": "failed",
                "folder": str(task.folder_path),
                "folder_name": task.display_name or task.folder_path.name,  # Use display_name if available, else folder name
                "plan": task.plan_config.get('name', 'Unknown') if task.plan_config else 'Unknown',
                "worker": worker_id,
                "document_id": task.document_id
            })
            
            return error_result
    
    def _set_default_workers(self, cpu_workers: int, io_workers: int):
        """Set default worker configuration"""
        self.cpu_workers = cpu_workers or max(2, multiprocessing.cpu_count() // 2)  # Half cores for CPU-intensive tasks
        self.io_workers = io_workers or multiprocessing.cpu_count()  # Use core count for IO workers (they're mostly waiting for API responses)
        logger.info(f"Using default worker configuration: {self.cpu_workers} CPU, {self.io_workers} IO")
    
 