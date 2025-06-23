"""
Simple Python Backend for Local Document Processing

Uses subprocess to run workflows directly on folders.
Perfect for Mac GUI - no errant threads, clean shutdown.
"""

import json
import logging
import sys
import time
import multiprocessing
from typing import Dict, List, Optional
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from .base import ProcessingBackend, FolderTask, ProcessingResult, ProcessingStatus

logger = logging.getLogger(__name__)


class PythonProcessingBackend(ProcessingBackend):
    """
    Simple Python backend using subprocess for workflow execution.
    
    Features:
    - Direct subprocess execution (no worker pools)
    - Optional parallel processing with ThreadPoolExecutor
    - Clean shutdown (no errant processes)
    - Progress tracking via callback
    - Safe for GUI use
    """
    
    def __init__(self, app=None, cpu_workers: int = None, io_workers: int = None):
        super().__init__(app)
        self.backend_name = "python"
        
        # Get worker configuration from app settings if available
        if app and hasattr(app, 'settings'):
            try:
                from ...config.core.settings import get_app_settings
                logger.info(f"Loading worker settings from app: {type(app)}")
                app_settings = get_app_settings(app)
                if app_settings:
                    # Get worker values from settings
                    cpu_from_settings = app_settings.get_cpu_workers()
                    io_from_settings = app_settings.get_io_workers()
                    logger.info(f"App settings returned: CPU={cpu_from_settings}, IO={io_from_settings}")
                    
                    # Use settings from app configuration
                    self.cpu_workers = cpu_workers or cpu_from_settings
                    self.io_workers = io_workers or io_from_settings
                    logger.info(f"Using worker configuration from app settings: {self.cpu_workers} CPU, {self.io_workers} IO")
                else:
                    logger.warning("get_app_settings returned None, using defaults")
                    # Fallback to calculated defaults
                    self._set_default_workers(cpu_workers, io_workers)
            except Exception as e:
                logger.warning(f"Could not load worker settings from app: {e}")
                self._set_default_workers(cpu_workers, io_workers)
        else:
            logger.info(f"No app context (app={app}, has_settings={hasattr(app, 'settings') if app else False}), using defaults")
            # No app context, use calculated defaults
            self._set_default_workers(cpu_workers, io_workers)
        
        self.cpu_executor: Optional[ThreadPoolExecutor] = None
        self.io_executor: Optional[ThreadPoolExecutor] = None
        
        # Task tracking
        self.active_tasks: Dict[str, ProcessingStatus] = {}
        self.task_results: Dict[str, ProcessingResult] = {}
        self.task_futures: Dict[str, any] = {}
        self._lock = threading.Lock()
        
        self._initialized = False
        self._progress_callback = None
        logger.info(f"System has {multiprocessing.cpu_count()} CPU cores")
        logger.info(f"Configured with {self.cpu_workers} CPU workers and {self.io_workers} IO workers")
        logger.info(f"IO workers are not resource-intensive (mostly waiting for API responses), so we can use many more")
    
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
        """
        if not tasks:
            return {}
        
        # Start executors if needed
        if self.cpu_executor is None:
            self.cpu_executor = ThreadPoolExecutor(max_workers=self.cpu_workers, thread_name_prefix="fichero-cpu")
            logger.info(f"Created CPU executor with {self.cpu_workers} workers")
            logger.info(f"CPU executor object: {self.cpu_executor}")
        
        if self.io_executor is None:
            self.io_executor = ThreadPoolExecutor(max_workers=self.io_workers, thread_name_prefix="fichero-io")
            logger.info(f"Created IO executor with {self.io_workers} workers")
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
                
                # Determine which executor to use based on workflow characteristics
                executor = self._get_executor_for_task(task)
                executor_type = "cpu" if executor == self.cpu_executor else "io"
                
                logger.info(f"Task {task.task_id} assigned to {executor_type} executor (workflow: {task.workflow_name})")
                
                # Submit to appropriate thread pool
                future = executor.submit(self._execute_single_folder, task)
                self.task_futures[task.task_id] = future
                
                # Log executor status
                logger.info(f"Task {task.task_id} submitted to {executor_type} executor")
                logger.info(f"  Executor: {executor}")
                logger.info(f"  Max workers: {executor._max_workers}")
                logger.info(f"  Active threads: {len(executor._threads) if hasattr(executor, '_threads') else 'unknown'}")
                
                # Notify progress with placeholder worker information (will be updated by actual worker)
                self._notify_progress(task.task_id, {
                    "status": "submitted",
                    "folder": str(task.folder_path),
                    "workflow": task.workflow_name,
                    "plan": task.plan_config.get('name', 'Unknown'),
                    "executor_type": executor_type,
                    "worker": f"{executor_type.upper()}-pending"  # Placeholder, will be updated by worker
                })
                
                logger.info(f"Submitted task {task.task_id} to {executor_type} executor for folder: {task.folder_path}")
        
        return results  # Empty for async backend
    
    def _get_executor_for_task(self, task: FolderTask) -> ThreadPoolExecutor:
        """Determine which executor to use based on task characteristics"""
        try:
            # Analyze the workflow to determine predominant worker type
            workflows = task.plan_config.get('workflows', {})
            commands = {cmd['name']: cmd for cmd in task.plan_config.get('commands', [])}
            
            if task.workflow_name in workflows:
                workflow_steps = workflows[task.workflow_name]
                cpu_steps = 0
                io_steps = 0
                
                logger.info(f"Analyzing workflow '{task.workflow_name}' with {len(workflow_steps)} steps")
                
                for step_name in workflow_steps:
                    if step_name in commands:
                        worker_type = commands[step_name].get('worker_type', 'cpu')
                        if worker_type == 'cpu':
                            cpu_steps += 1
                        else:
                            io_steps += 1
                        logger.info(f"  Step '{step_name}' classified as {worker_type} (cpu: {cpu_steps}, io: {io_steps})")
                    else:
                        logger.warning(f"  Step '{step_name}' not found in commands, defaulting to cpu")
                        cpu_steps += 1
                
                # Use the executor type that has more steps
                if cpu_steps > io_steps:
                    logger.info(f"Workflow '{task.workflow_name}' classified as CPU-bound ({cpu_steps} cpu steps vs {io_steps} io steps)")
                    return self.cpu_executor
                else:
                    logger.info(f"Workflow '{task.workflow_name}' classified as IO-bound ({io_steps} io steps vs {cpu_steps} cpu steps)")
                    return self.io_executor
            
            # Default to IO executor for unknown workflows (transcription tasks are typically IO-bound)
            logger.info(f"Unknown workflow '{task.workflow_name}', defaulting to IO executor")
            return self.io_executor
            
        except Exception as e:
            logger.warning(f"Error determining executor for task {task.task_id}: {e}")
            return self.io_executor  # Safe default for transcription tasks
    
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
                    return ProcessingStatus.CANCELLED
                elif future.running():
                    return ProcessingStatus.RUNNING
                elif future.done():
                    # Future completed, process result
                    try:
                        result = future.result()
                        self.task_results[task_id] = result
                        del self.task_futures[task_id]
                        return ProcessingStatus.COMPLETED if result.success else ProcessingStatus.FAILED
                    except Exception as e:
                        # Create error result
                        result = ProcessingResult(
                            task_id=task_id,
                            success=False,
                            folder_path=Path("unknown"),
                            output_path=Path("unknown"),
                            error_message=str(e)
                        )
                        self.task_results[task_id] = result
                        del self.task_futures[task_id]
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
                                return True
                    except Exception as e:
                        logger.error(f"Error cancelling future for task {task_id}: {e}")
                        # Force remove the future even if there's an error
                        if task_id in self.task_futures:
                            del self.task_futures[task_id]
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
            if hasattr(self, 'task_executors'):
                self.task_executors.clear()
            
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
            
            # Shutdown executors without waiting (prevents hanging)
            if self.cpu_executor:
                logger.info("Shutting down CPU executor...")
                self.cpu_executor.shutdown(wait=False, cancel_futures=True)
                self.cpu_executor = None
                logger.info("CPU executor shutdown completed")
            
            if self.io_executor:
                logger.info("Shutting down IO executor...")
                self.io_executor.shutdown(wait=False, cancel_futures=True)
                self.io_executor = None
                logger.info("IO executor shutdown completed")
            
            # Clear tracking immediately - use forced cleanup to avoid lock issues
            logger.info("Clearing task tracking...")
            self._force_cleanup_without_lock()
            
            # Clean up asyncio resources
            try:
                import asyncio
                import gc
                
                # Get the current event loop if it exists
                try:
                    loop = asyncio.get_running_loop()
                    logger.info("Found running event loop in backend, cleaning up...")
                    
                    # Cancel all pending tasks
                    pending_tasks = asyncio.all_tasks(loop)
                    if pending_tasks:
                        logger.info(f"Cancelling {len(pending_tasks)} pending backend tasks...")
                        for task in pending_tasks:
                            if not task.done():
                                task.cancel()
                        
                        # Wait briefly for tasks to cancel
                        try:
                            loop.run_until_complete(asyncio.wait(pending_tasks, timeout=1.0))
                        except Exception as e:
                            logger.warning(f"Error waiting for backend task cancellation: {e}")
                    
                    # Close all transports in the loop
                    try:
                        # Get all transports from the loop's selector
                        if hasattr(loop, '_selector') and hasattr(loop._selector, '_fd_to_key'):
                            for fd, key in list(loop._selector._fd_to_key.items()):
                                if hasattr(key, 'fileobj') and hasattr(key.fileobj, 'close'):
                                    try:
                                        key.fileobj.close()
                                        logger.info(f"Closed backend transport fd={fd}")
                                    except Exception as e:
                                        logger.warning(f"Error closing backend transport fd={fd}: {e}")
                    except Exception as e:
                        logger.warning(f"Error closing backend transports: {e}")
                    
                except RuntimeError:
                    # No running event loop
                    logger.info("No running event loop found in backend")
                
                # Force garbage collection to clean up any remaining resources
                gc.collect()
                logger.info("Backend asyncio cleanup completed")
                
            except Exception as e:
                logger.warning(f"Error during backend asyncio cleanup: {e}")
            
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
        """Execute workflow on a single folder using integrated executor"""
        
        try:
            # Update status
            with self._lock:
                self.active_tasks[task.task_id] = ProcessingStatus.RUNNING
            
            logger.info(f"Processing folder: {task.folder_path}")
            
            # Get current thread info for worker identification
            current_thread = threading.current_thread()
            executor_type = "cpu" if "cpu" in current_thread.name.lower() else "io"
            worker_id = f"{executor_type.upper()}-{current_thread.ident % 1000}"
            
            logger.info(f"Task {task.task_id} running on worker: {worker_id} (thread: {current_thread.name}, id: {current_thread.ident})")
            
            # Log active workers for debugging
            if hasattr(self, 'cpu_executor') and self.cpu_executor:
                logger.info(f"CPU executor has {self.cpu_executor._max_workers} max workers")
            if hasattr(self, 'io_executor') and self.io_executor:
                logger.info(f"IO executor has {self.io_executor._max_workers} max workers")
            
            # Create workflow executor with progress callback that includes worker info and document_id
            from ...workflow_executor import WorkflowExecutor
            executor = WorkflowExecutor(progress_callback=lambda task_id, data: self._notify_progress_with_worker_and_document(task_id, data, worker_id, task.document_id))
            
            # Store executor for cancellation support
            with self._lock:
                self.task_executors = getattr(self, 'task_executors', {})
                self.task_executors[task.task_id] = executor
            
            # Execute workflow with full integration
            result = executor.execute_workflow(
                task_id=task.task_id,
                folder_path=task.folder_path,
                output_path=task.output_path,
                workflow_name=task.workflow_name,
                plan_config=task.plan_config,
                variables=task.variables
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
                    logger.info(f"Successfully processed folder: {task.folder_path} ({result.execution_time:.1f}s)")
                    # Notify completion
                    self._notify_progress(task.task_id, {
                        "status": "completed",
                        "folder": str(task.folder_path),
                        "plan": task.plan_config.get('name', 'Unknown'),
                        "worker": worker_id,
                        "execution_time": result.execution_time,
                        "document_id": task.document_id
                    })
                else:
                    self.active_tasks[task.task_id] = ProcessingStatus.FAILED
                    logger.error(f"Failed to process folder: {task.folder_path} - {result.error_message}")
                    # Notify failure
                    self._notify_progress(task.task_id, {
                        "status": "failed",
                        "folder": str(task.folder_path),
                        "plan": task.plan_config.get('name', 'Unknown'),
                        "worker": worker_id,
                        "error": result.error_message,
                        "document_id": task.document_id
                    })
            
            return result
            
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.error(f"Error processing folder: {task.folder_path} - {e}")
            logger.exception("Folder processing exception")
            
            # Get worker info for error reporting
            current_thread = threading.current_thread()
            executor_type = "cpu" if "cpu" in current_thread.name.lower() else "io"
            worker_id = f"{executor_type.upper()}-{current_thread.ident % 1000}"
            
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
            
            # Notify failure
            self._notify_progress(task.task_id, {
                "status": "failed",
                "folder": str(task.folder_path),
                "plan": task.plan_config.get('name', 'Unknown'),
                "worker": worker_id,
                "error": error_msg,
                "document_id": task.document_id
            })
            
            return error_result
    
    def _set_default_workers(self, cpu_workers: int, io_workers: int):
        """Set default worker configuration"""
        self.cpu_workers = cpu_workers or max(2, multiprocessing.cpu_count() // 2)  # Half cores for CPU-intensive tasks
        self.io_workers = io_workers or multiprocessing.cpu_count()  # Use core count for IO workers (they're mostly waiting for API responses)
        logger.info(f"Using default worker configuration: {self.cpu_workers} CPU, {self.io_workers} IO")
    
 