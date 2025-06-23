"""
Fichero Director Service

Simple director service that coordinates document processing.
Implements singleton pattern for application-wide coordination.
"""

import logging
from typing import Dict, List, Optional, Callable, Any
from pathlib import Path

from .task_manager import TaskPriority
from .backends.implementations.base import ProcessingStatus
from .cleanup import cleanup_all_resources

logger = logging.getLogger(__name__)


class FicheroDirector:
    """
    Simple director service for Fichero document processing.
    
    Features:
    - Singleton pattern ensures one service per application
    - Backend-agnostic processing (Python or Celery)
    - Simple task submission and monitoring
    - Progress callbacks for UI updates
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls, settings=None, app=None):
        """Singleton implementation"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, settings=None, app=None):
        """Initialize director service"""
        if FicheroDirector._initialized:
            return
        
        # Import specialized components first
        from .variable_generator import VariableGenerator
        from .interfaces.cli_helper import CLIDisplayHelper
        from .backends.backend_manager import BackendManager
        from .backends.backend_initializer import BackendInitializer
        from .config.manager import ConfigurationManager
        
        # Initialize configuration manager first
        self.configuration_manager = ConfigurationManager(self)
        
        # Process settings and app
        self.settings, self.app = self.configuration_manager.process_settings(settings, app)
        self.instance_id = self.configuration_manager.generate_instance_id()
        
        # Initialize core components
        self.backend = None
        self.task_manager = None
        
        # Initialize other specialized components
        self.variable_generator = VariableGenerator()
        self.cli_display_helper = CLIDisplayHelper(self)
        self.backend_manager = BackendManager(self)
        self.backend_initializer = BackendInitializer(self)
        # Task operations integrated directly (TaskOperations wrapper removed)
        
        # Processing coordinator will be initialized after task_manager
        self.processing_coordinator = None
        
        # Callbacks for UI updates
        self.progress_callbacks: List[Callable] = []
        
        # Initialize task monitoring AFTER everything else is ready
        from .monitoring import TaskMonitor
        self.task_monitor = TaskMonitor.get_instance(self, "director")
        
        # Mark as initialized
        self._initialized = True
        FicheroDirector._initialized = True
        logger.info(f"FicheroDirector initialized with instance ID: {self.instance_id}")
    
    @classmethod
    def get_instance(cls, settings=None, app=None) -> 'FicheroDirector':
        """Get or create the singleton director instance"""
        if cls._instance is None:
            cls._instance = cls(settings, app)
        return cls._instance
    
    @classmethod
    def is_initialized(cls) -> bool:
        """Check if director service is initialized"""
        return cls._instance is not None and cls._initialized
    
    def initialize_backend(self) -> bool:
        """Initialize the processing backend based on settings"""
        success = self.backend_initializer.initialize_backend()
        if success:
            # Register TaskMonitor to receive progress updates
            self._register_task_monitor()
        return success
    
    def _register_task_monitor(self):
        """Register TaskMonitor to receive progress updates from task manager"""
        if self.task_monitor and self.task_manager:
            self.task_manager.register_progress_callback(self.task_monitor._on_progress_update)
            logger.info("TaskMonitor registered to receive progress updates")
    
    def shutdown(self):
        """Shutdown the director service with timeout"""
        logger.info("Shutting down FicheroDirector...")
        
        # Call comprehensive cleanup FIRST to prevent ResourceWarnings
        cleanup_all_resources()
        
        try:
            # Shutdown task manager first
            if self.task_manager:
                logger.info("Shutting down task manager...")
                self.task_manager.stop()
                logger.info("Task manager shutdown completed")
            
            # Shutdown backend with shorter timeout
            if self.backend:
                logger.info("Shutting down backend...")
                # Add a shorter timeout to prevent hanging
                import threading
                import time
                
                shutdown_complete = threading.Event()
                shutdown_success = [False]
                
                def shutdown_backend():
                    try:
                        shutdown_success[0] = self.backend.shutdown()
                    except Exception as e:
                        logger.error(f"Error during backend shutdown: {e}")
                        shutdown_success[0] = False
                    finally:
                        shutdown_complete.set()
                
                # Start shutdown in a separate thread
                shutdown_thread = threading.Thread(target=shutdown_backend, daemon=True)
                shutdown_thread.start()
                
                # Wait for shutdown with 3 second timeout (reduced from 5)
                if shutdown_complete.wait(timeout=3.0):
                    logger.info(f"Backend shutdown completed: {shutdown_success[0]}")
                else:
                    logger.warning("Backend shutdown timed out, forcing cleanup")
                    # Force cleanup even if shutdown didn't complete
                    try:
                        if hasattr(self.backend, '_force_cleanup_without_lock'):
                            self.backend._force_cleanup_without_lock()
                        logger.info("Forced backend cleanup completed")
                    except Exception as e:
                        logger.error(f"Error during forced cleanup: {e}")
            
            logger.info("FicheroDirector shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during FicheroDirector shutdown: {e}")
            # Force cleanup even if there's an error
            try:
                if self.backend and hasattr(self.backend, '_force_cleanup_without_lock'):
                    self.backend._force_cleanup_without_lock()
                logger.info("Emergency cleanup completed")
            except Exception as cleanup_error:
                logger.error(f"Error during emergency cleanup: {cleanup_error}")
        finally:
            # Call comprehensive cleanup AGAIN to ensure everything is closed
            cleanup_all_resources()
            
            # Reset singleton
            FicheroDirector._instance = None
            FicheroDirector._initialized = False
    
    def _cleanup_all_resources(self):
        """Comprehensive cleanup of all resources including network connections"""
        try:
            import asyncio
            import gc
            import socket
            import threading
            import warnings
            
            logger.info("Starting comprehensive resource cleanup...")
            
            # Temporarily suppress ResourceWarnings during cleanup
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                
                # Clean up asyncio resources
                try:
                    # Try multiple approaches to get and close event loops
                    loops_to_close = []
                    
                    # Approach 1: Get running loop
                    try:
                        loop = asyncio.get_running_loop()
                        loops_to_close.append(("running", loop))
                        logger.info("Found running event loop")
                    except RuntimeError:
                        logger.info("No running event loop found")
                    
                    # Approach 2: Get current loop
                    try:
                        loop = asyncio.get_event_loop()
                        if loop and not loop.is_closed():
                            loops_to_close.append(("current", loop))
                            logger.info("Found current event loop")
                    except RuntimeError:
                        logger.info("No current event loop found")
                    
                    # Approach 3: Get from policy
                    try:
                        policy = asyncio.get_event_loop_policy()
                        if hasattr(policy, '_local') and hasattr(policy._local, '_loop'):
                            cached_loop = policy._local._loop
                            if cached_loop and not cached_loop.is_closed():
                                loops_to_close.append(("cached", cached_loop))
                                logger.info("Found cached event loop")
                    except Exception as e:
                        logger.warning(f"Error getting policy loop: {e}")
                    
                    # Close all found loops
                    for loop_type, loop in loops_to_close:
                        try:
                            logger.info(f"Cleaning up {loop_type} event loop...")
                            
                            # Cancel all pending tasks
                            pending_tasks = asyncio.all_tasks(loop)
                            if pending_tasks:
                                logger.info(f"Cancelling {len(pending_tasks)} pending asyncio tasks...")
                                for task in pending_tasks:
                                    if not task.done():
                                        task.cancel()
                                
                                # Wait briefly for tasks to cancel
                                try:
                                    loop.run_until_complete(asyncio.wait(pending_tasks, timeout=1.0))
                                except Exception as e:
                                    logger.warning(f"Error waiting for task cancellation: {e}")
                            
                            # Close all transports in the loop
                            try:
                                # Get all transports from the loop's selector
                                if hasattr(loop, '_selector') and hasattr(loop._selector, '_fd_to_key'):
                                    for fd, key in list(loop._selector._fd_to_key.items()):
                                        if hasattr(key, 'fileobj') and hasattr(key.fileobj, 'close'):
                                            try:
                                                key.fileobj.close()
                                                logger.info(f"Closed transport fd={fd}")
                                            except Exception as e:
                                                logger.warning(f"Error closing transport fd={fd}: {e}")
                            except Exception as e:
                                logger.warning(f"Error closing transports: {e}")
                            
                            # Close the loop
                            if not loop.is_closed():
                                logger.info(f"Closing {loop_type} event loop...")
                                loop.close()
                                logger.info(f"Successfully closed {loop_type} event loop")
                            else:
                                logger.info(f"{loop_type} event loop was already closed")
                                
                        except Exception as e:
                            logger.warning(f"Error cleaning up {loop_type} event loop: {e}")
                    
                except Exception as e:
                    logger.warning(f"Error during asyncio cleanup: {e}")
                
                # Clean up any remaining network connections
                try:
                    # Force close any remaining socket connections
                    for thread in threading.enumerate():
                        if hasattr(thread, '_local') and hasattr(thread._local, '__dict__'):
                            for attr_name, attr_value in list(thread._local.__dict__.items()):
                                if hasattr(attr_value, 'close') and callable(attr_value.close):
                                    try:
                                        attr_value.close()
                                        logger.info(f"Closed resource in thread {thread.name}: {attr_name}")
                                    except Exception:
                                        pass
                except Exception as e:
                    logger.warning(f"Error during thread cleanup: {e}")
                
                # Force garbage collection to clean up any remaining resources
                gc.collect()
                logger.info("Comprehensive resource cleanup completed")
                
        except Exception as e:
            logger.warning(f"Error during comprehensive cleanup: {e}")
    
    # Core task operations - direct delegation to task_manager
    def submit_task(self, folders: List[Path], plan_config: Dict, workflow_name: str = "default",
                   variables: Dict = None, priority: TaskPriority = TaskPriority.NORMAL,
                   document_context: Dict = None) -> str:
        """Submit a processing task"""
        if not self.task_manager:
            raise RuntimeError("Director service not initialized. Call initialize_backend() first.")
        return self.task_manager.submit_task(folders, plan_config, workflow_name, variables, priority, document_context)
    
    def get_task_status(self, task_id: str) -> Optional[ProcessingStatus]:
        """Get current status of a task"""
        if not self.task_manager:
            return None
        return self.task_manager.get_task_status(task_id)
    
    def get_task_result(self, task_id: str):
        """Get result of a completed task"""
        if not self.task_manager:
            return None
        return self.task_manager.get_task_result(task_id)
    
    def get_task_monitor(self):
        """Get the task monitor for displays"""
        return self.task_monitor
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task"""
        if not self.task_manager:
            return False
        return self.task_manager.cancel_task(task_id)
    
    def list_active_tasks(self) -> List[str]:
        """List all currently active task IDs"""
        if not self.task_manager:
            return []
        return self.task_manager.list_active_tasks()
    
    def get_stats(self) -> Dict:
        """Get director service statistics"""
        stats = {
            "instance_id": self.instance_id,
            "backend_type": self.backend.backend_name if self.backend else "none",
            "is_initialized": (hasattr(self.backend, 'is_initialized') and 
                             self.backend.is_initialized if self.backend else False)
        }
        
        if self.task_manager:
            stats.update(self.task_manager.get_stats())
        
        return stats
    
    def register_progress_callback(self, callback: Callable):
        """Register callback for progress updates"""
        self.progress_callbacks.append(callback)
        
        # Register TaskMonitor to receive progress updates directly (only if TaskMonitor exists)
        if hasattr(self, 'task_monitor') and self.task_monitor and hasattr(self, 'task_manager') and self.task_manager:
            self.task_manager.register_progress_callback(self.task_monitor._on_progress_update)
        
        if hasattr(self, 'task_manager') and self.task_manager:
            self.task_manager.register_progress_callback(callback)
    
    def _load_plan_config(self, plan_name: str) -> Dict:
        """Load plan configuration by name"""
        return self.configuration_manager.load_plan_config(plan_name)
    

    
    # Convenience methods for common use cases
    def process_folders(self, folders: List[Path], plan_name: str, 
                       workflow_name: str = "default", 
                       output_path: Path = None,
                       document_context: Dict = None) -> str:
        """
        Convenience method to process folders using a plan name
        
        Args:
            folders: List of folder paths to process
            plan_name: Name of the plan to use
            workflow_name: Name of workflow within the plan
            output_path: Base output directory
            document_context: Context from document window (optional)
        
        Returns:
            Task ID string
        """
        if not self.processing_coordinator:
            raise RuntimeError("Director service not fully initialized. Call initialize_backend() first.")
        
        return self.processing_coordinator.process_folders(
            folders=folders,
            plan_name=plan_name,
            workflow_name=workflow_name,
            output_path=output_path,
            document_context=document_context
        )
    
    def process_with_auto_detection(self, input_path: Path, output_path: Path, 
                                   plan_name: str, workflow_name: str = "default",
                                   document_context: Dict = None) -> List[str]:
        """
        Auto-detect subfolders and process each as separate task
        
        Args:
            input_path: Input folder path to check for subfolders
            output_path: Base output directory
            plan_name: Name of the plan to use
            workflow_name: Name of workflow within the plan
            document_context: Context from document window (optional)
        
        Returns:
            List of task IDs for each folder being processed
        """
        if not self.processing_coordinator:
            raise RuntimeError("Director service not fully initialized. Call initialize_backend() first.")
        
        return self.processing_coordinator.process_with_auto_detection(
            input_path=input_path,
            output_path=output_path,
            plan_name=plan_name,
            workflow_name=workflow_name,
            document_context=document_context
        )
    
    # CLI convenience methods
    # NOTE: process_with_rich_display removed - this was mixing responsibilities!
    # Use process_with_auto_detection() for processing + monitoring/displays/cli_display.py for rich displays
    
    def display_status(self, console):
        """Display current status for CLI"""
        return self.cli_display_helper.display_status(console)
    
    def configure_settings(self, console, show_defaults: bool = False, 
                          backend: str = None, cpu_workers: int = None,
                          io_workers: int = None, memory_per_worker: int = None,
                          plan: str = None, workflow: str = None):
        """Configure settings for CLI"""
        return self.cli_display_helper.configure_settings(
            console, show_defaults, backend, cpu_workers, 
            io_workers, memory_per_worker, plan, workflow
        )
    
    def display_available_plans(self, console):
        """Display available plans for CLI"""
        return self.cli_display_helper.display_available_plans(console)
    
    def display_system_info(self, console):
        """Display system information for CLI"""
        return self.cli_display_helper.display_system_info(console)
    
    def get_backend_info(self) -> Dict[str, Any]:
        """Get comprehensive backend information including availability"""
        return self.backend_manager.get_backend_info()
    
    # Backend management methods - delegate to backend_manager
    def start_backend_workers(self, cpu_workers: int = None, io_workers: int = None) -> bool:
        """Start backend workers - unified method"""
        return self.backend_manager.start_backend_workers(cpu_workers, io_workers)
    
    def stop_backend_workers(self) -> bool:
        """Stop backend workers - unified method"""
        return self.backend_manager.stop_backend_workers()
    
    def restart_backend_workers(self, cpu_workers: int = None, io_workers: int = None) -> bool:
        """Restart backend workers - unified method"""
        return self.backend_manager.restart_backend_workers(cpu_workers, io_workers)
    
    def get_backend_worker_status(self) -> Dict:
        """Get backend worker status - unified method"""
        return self.backend_manager.get_backend_worker_status()
    
    def check_backend_health(self) -> Dict:
        """Check backend health - unified method"""
        return self.backend_manager.check_backend_health()
    
    def purge_backend_tasks(self) -> bool:
        """Purge backend tasks - unified method"""
        return self.backend_manager.purge_backend_tasks()
    
    def get_task_monitor(self):
        """Get the task monitor for displays"""
        return self.task_monitor
    
    def get_task_status(self, task_id: str) -> Optional[ProcessingStatus]:
        """Get current status of a task"""
        if not self.task_manager:
            return None
        return self.task_manager.get_task_status(task_id)
    

    
    # Backend management methods - delegate to backend_manager
    def start_backend_workers(self, cpu_workers: int = None, io_workers: int = None) -> bool:
        """Start backend workers - unified method"""
        return self.backend_manager.start_backend_workers(cpu_workers, io_workers)
    
    def stop_backend_workers(self) -> bool:
        """Stop backend workers - unified method"""
        return self.backend_manager.stop_backend_workers()
    
    def restart_backend_workers(self, cpu_workers: int = None, io_workers: int = None) -> bool:
        """Restart backend workers - unified method"""
        return self.backend_manager.restart_backend_workers(cpu_workers, io_workers)
    
    def get_backend_worker_status(self) -> Dict:
        """Get backend worker status - unified method"""
        return self.backend_manager.get_backend_worker_status()
    
    def check_backend_health(self) -> Dict:
        """Check backend health - unified method"""
        return self.backend_manager.check_backend_health()
    
    def purge_backend_tasks(self) -> bool:
        """Purge backend tasks - unified method"""
        return self.backend_manager.purge_backend_tasks() 