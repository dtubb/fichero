"""
Celery Backend for Document Processing

Distributed processing backend using Celery and Redis.
Supports multiple instances and HPC environments.
"""

import logging
import time
import json
from typing import Dict, List, Optional
from pathlib import Path
import threading

from fichero.base import ProcessingBackend, FolderTask, ProcessingResult, ProcessingStatus

logger = logging.getLogger(__name__)

# Try to import Celery with graceful fallback
try:
    from celery import Celery
    from celery.result import AsyncResult
    import redis
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    logger.warning("Celery not available - CeleryBackend will not function")


class CeleryBackend(ProcessingBackend):
    """
    Celery-based distributed processing backend.
    
    Features:
    - Distributed task execution across multiple workers
    - Redis-based coordination
    - Multiple instance support
    - HPC environment compatibility
    """
    
    def __init__(self, app=None, broker_url: str = None, result_backend: str = None):
        super().__init__(app)
        
        if not CELERY_AVAILABLE:
            raise ImportError("Celery backend requires 'celery' and 'redis' packages")
        
        self.backend_name = "celery"
        
        # Configuration
        self.broker_url = broker_url or 'redis://localhost:6379/0'
        self.result_backend = result_backend or 'redis://localhost:6379/0'
        
        # Initialize Celery app
        self.celery_app = None
        self.active_tasks: Dict[str, AsyncResult] = {}
        self._lock = threading.Lock()
        self._progress_callback = None
        self._initialized = False
        
        self._initialize_celery()
    
    @property
    def supports_async(self) -> bool:
        return True  # Celery is async by nature
    
    @property  
    def supports_multiple_instances(self) -> bool:
        return True  # Multiple CLI instances can share Celery workers
    
    @property
    def requires_external_services(self) -> bool:
        return True  # Requires Redis and Celery workers
    
    @property
    def is_initialized(self) -> bool:
        """Check if backend is initialized"""
        return self._initialized
    
    def initialize(self) -> bool:
        """Initialize the backend and test connections"""
        try:
            # Test Redis connection
            if not self._test_redis_connection():
                logger.warning("Redis connection failed")
                return False
            
            # Test if Celery workers are available
            worker_count = self.get_worker_count()
            if worker_count == 0:
                logger.warning("No Celery workers found")
                return False
            
            self._initialized = True
            logger.info(f"Celery backend initialized with {worker_count} workers")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Celery backend: {e}")
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
    
    def _initialize_celery(self):
        """Initialize Celery application"""
        try:
            self.celery_app = Celery(
                'fichero_director',
                broker=self.broker_url,
                backend=self.result_backend
            )
            
            # Configure Celery
            self.celery_app.conf.update(
                task_serializer='json',
                accept_content=['json'],
                result_serializer='json',
                timezone='UTC',
                enable_utc=True,
                task_track_started=True,
                worker_prefetch_multiplier=1,
                task_acks_late=True
            )
            
            # Register task
            self._register_task()
            
            logger.info(f"Initialized Celery backend with broker: {self.broker_url}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Celery: {e}")
            raise
    
    def _register_task(self):
        """Register Celery task for folder processing"""
        
        @self.celery_app.task(bind=True, name='fichero.process_folder')
        def process_folder_task(self, folder_path: str, output_path: str, 
                               workflow_name: str, plan_config: Dict, variables: Dict, 
                               parallel_workers: int = 1) -> Dict:
            """Celery task for processing a single folder"""
            try:
                # Update task state
                self.update_state(
                    state='PROGRESS',
                    meta={'status': 'starting', 'folder': folder_path}
                )
                
                # Execute workflow using integrated executor
                from fichero.workflow_executor import WorkflowExecutor
                
                executor = WorkflowExecutor(progress_callback=lambda task_id, data: self.update_state(
                    state='PROGRESS',
                    meta=data
                ))
                
                result = executor.execute_workflow(
                    task_id=self.request.id,
                    folder_path=Path(folder_path),
                    output_path=Path(output_path),
                    workflow_name=workflow_name,
                    plan_config=plan_config,
                    variables=variables,
                    parallel_workers=parallel_workers
                )
                
                # Return result
                return {
                    'success': result.success,
                    'folder_path': str(result.folder_path),
                    'output_path': str(result.output_path),
                    'error_message': result.error_message,
                    'execution_time': result.execution_time,
                    'files_processed': result.files_processed
                }
                
            except Exception as e:
                return {
                    'success': False,
                    'folder_path': folder_path,
                    'output_path': output_path,
                    'error_message': str(e)
                }
        
        # Store task reference
        self.process_folder_task = process_folder_task
    
    def process_folders(self, tasks: List[FolderTask]) -> Dict[str, ProcessingResult]:
        """Submit folders for processing and return immediately"""
        if not tasks:
            return {}
        
        with self._lock:
            for task in tasks:
                # Determine which queue to use based on task characteristics
                queue_name = self._get_queue_for_task(task)
                
                # Determine parallel workers based on current load
                parallel_workers = self._get_parallel_workers_for_task(task)
                
                # Submit to Celery with specific queue
                async_result = self.process_folder_task.apply_async(
                    args=[
                        str(task.folder_path),
                        str(task.output_path),
                        task.workflow_name,
                        task.plan_config,
                        task.variables,
                        parallel_workers
                    ],
                    task_id=task.task_id,
                    queue=queue_name
                )
                
                # Store task reference
                self.active_tasks[task.task_id] = async_result
                
                # Notify progress
                self._notify_progress(task.task_id, {
                    "status": "submitted",
                    "folder": str(task.folder_path),
                    "workflow": task.workflow_name,
                    "queue": queue_name
                })
                
                logger.info(f"Submitted task {task.task_id} to Celery queue '{queue_name}' for folder: {task.folder_path}")
        
        return {}  # Empty for async backend
    
    def _get_queue_for_task(self, task: FolderTask) -> str:
        """Determine which Celery queue to use based on task characteristics"""
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
                
                # Use the queue type that has more steps
                if cpu_steps > io_steps:
                    logger.info(f"Workflow '{task.workflow_name}' classified as CPU-bound ({cpu_steps} cpu steps vs {io_steps} io steps)")
                    return 'cpu_intensive'
                else:
                    logger.info(f"Workflow '{task.workflow_name}' classified as IO-bound ({io_steps} io steps vs {cpu_steps} cpu steps)")
                    return 'io_intensive'
            
            # Default to IO queue for unknown workflows (transcription tasks are typically IO-bound)
            logger.info(f"Unknown workflow '{task.workflow_name}', defaulting to IO queue")
            return 'io_intensive'
            
        except Exception as e:
            logger.warning(f"Error determining queue for task {task.task_id}: {e}")
            return 'io_intensive'  # Safe default for transcription tasks
    
    def _get_parallel_workers_for_task(self, task: FolderTask) -> int:
        """Determine how many parallel workers to allow for this task based on current load"""
        with self._lock:
            # Count currently active tasks
            active_count = len(self.active_tasks)
            
            # Simple logic: Multiple folders = sequential tools, Single folder = parallel tools
            # More conservative for Celery since we don't know cluster configuration
            if active_count > 1:
                logger.info(f"Multiple tasks active in cluster ({active_count}), using sequential tool processing for task {task.task_id}")
                return 1  # Multiple folders: tools run sequentially to avoid overwhelming cluster
            else:
                logger.info(f"Single task processing, enabling parallel tool processing for task {task.task_id} (3 workers)")
                return 3  # Single folder: tools can use parallel processing (conservative for distributed environment)
    
    def get_status(self, task_id: str) -> ProcessingStatus:
        """Get current status of a task"""
        with self._lock:
            if task_id not in self.active_tasks:
                return ProcessingStatus.PENDING
            
            async_result = self.active_tasks[task_id]
            
            try:
                if async_result.state == 'PENDING':
                    return ProcessingStatus.PENDING
                elif async_result.state == 'PROGRESS':
                    return ProcessingStatus.RUNNING
                elif async_result.state == 'SUCCESS':
                    return ProcessingStatus.COMPLETED
                elif async_result.state == 'FAILURE':
                    return ProcessingStatus.FAILED
                elif async_result.state == 'REVOKED':
                    return ProcessingStatus.CANCELLED
                else:
                    return ProcessingStatus.PENDING
                    
            except Exception as e:
                logger.error(f"Failed to get status for task {task_id}: {e}")
                return ProcessingStatus.PENDING
    
    def get_result(self, task_id: str) -> Optional[ProcessingResult]:
        """Get result of completed task"""
        with self._lock:
            if task_id not in self.active_tasks:
                return None
            
            async_result = self.active_tasks[task_id]
            
            try:
                if not async_result.ready():
                    return None
                
                # Get result data
                result_data = async_result.get()
                
                # Convert to ProcessingResult
                processing_result = ProcessingResult(
                    task_id=task_id,
                    success=result_data.get('success', False),
                    folder_path=Path(result_data.get('folder_path', '')),
                    output_path=Path(result_data.get('output_path', '')),
                    error_message=result_data.get('error_message', ''),
                    execution_time=result_data.get('execution_time', 0.0),
                    files_processed=result_data.get('files_processed', [])
                )
                
                # Clean up completed task
                del self.active_tasks[task_id]
                
                # Notify completion
                if processing_result.success:
                    self._notify_progress(task_id, {
                        "status": "completed",
                        "folder": str(processing_result.folder_path),
                        "execution_time": processing_result.execution_time
                    })
                else:
                    self._notify_progress(task_id, {
                        "status": "failed",
                        "folder": str(processing_result.folder_path),
                        "error": processing_result.error_message
                    })
                
                return processing_result
                
            except Exception as e:
                logger.error(f"Failed to get result for task {task_id}: {e}")
                
                # Create error result
                error_result = ProcessingResult(
                    task_id=task_id,
                    success=False,
                    folder_path=Path("unknown"),
                    output_path=Path("unknown"),
                    error_message=str(e)
                )
                
                # Clean up failed task
                del self.active_tasks[task_id]
                
                # Notify failure
                self._notify_progress(task_id, {
                    "status": "failed",
                    "folder": "unknown",
                    "error": str(e)
                })
                
                return error_result
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a specific task"""
        with self._lock:
            if task_id not in self.active_tasks:
                return False
            
            async_result = self.active_tasks[task_id]
            
            try:
                # Revoke the task
                self.celery_app.control.revoke(task_id, terminate=True)
                
                # Remove from active tasks
                del self.active_tasks[task_id]
                
                logger.info(f"Cancelled task: {task_id}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to cancel task {task_id}: {e}")
                return False
    
    def cancel_all(self) -> bool:
        """Cancel all processing"""
        cancelled_count = 0
        with self._lock:
            for task_id in list(self.active_tasks.keys()):
                if self.cancel_task(task_id):
                    cancelled_count += 1
        
        logger.info(f"Cancelled {cancelled_count} Celery tasks")
        return cancelled_count > 0
    
    def shutdown(self) -> bool:
        """Clean shutdown of backend"""
        try:
            # Cancel all active tasks
            self.cancel_all()
            
            # Close Celery app
            if self.celery_app:
                self.celery_app.close()
            
            logger.info("Celery backend shutdown completed")
            return True
            
        except Exception as e:
            logger.error(f"Error during Celery backend shutdown: {e}")
            return False
    
    def list_active_tasks(self) -> List[str]:
        """List all currently active task IDs"""
        with self._lock:
            return list(self.active_tasks.keys())
    
    def _test_redis_connection(self) -> bool:
        """Test Redis connection"""
        try:
            r = redis.Redis.from_url(self.broker_url)
            r.ping()
            return True
        except Exception:
            return False
    

    
    # Additional Celery-specific methods for infrastructure management
    def flush_redis(self) -> bool:
        """Flush Redis database"""
        try:
            r = redis.Redis.from_url(self.broker_url)
            r.flushdb()
            logger.info("Redis database flushed successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to flush Redis database: {e}")
            return False
    
    def get_worker_count(self) -> int:
        """Get number of active Celery workers"""
        try:
            inspect = self.celery_app.control.inspect(timeout=2.0)
            stats = inspect.stats()
            return len(stats) if stats else 0
        except Exception:
            return 0
    
    def get_queue_lengths(self) -> Dict[str, int]:
        """Get lengths of task queues"""
        try:
            r = redis.Redis.from_url(self.broker_url)
            return {
                'default': r.llen('celery'),
                'cpu_intensive': r.llen('cpu_intensive'),
                'io_intensive': r.llen('io_intensive')
            }
        except Exception:
            return {}
    
    # Backend capability overrides
    def supports_worker_management(self) -> bool:
        """Celery supports worker management"""
        return True
    
    def supports_worker_status(self) -> bool:
        """Celery supports worker status monitoring"""
        return True
    
    def supports_health_check(self) -> bool:
        """Celery supports health checks"""
        return True
    
    def supports_task_purging(self) -> bool:
        """Celery supports purging pending tasks"""
        return True
    
    def supports_database_flush(self) -> bool:
        """Celery supports flushing Redis database"""
        return True 