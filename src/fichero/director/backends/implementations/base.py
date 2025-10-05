"""
Backend System for Document Processing

Simplified system focusedo on: Run workflows on folders, show progress, clean shutdown.
Supports both GUI (multiple document windows) and CLI (multiple instances).
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Callable
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
import uuid
import time


class ProcessingStatus(Enum):
    """Processing status"""
    PENDING = "pending"
    RUNNING = "running" 
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class FolderTask:
    """A folder processing task"""
    task_id: str
    folder_path: Path
    plan_config: Dict
    workflow_name: str
    output_path: Path
    documents_folder: Path = None  # Source folder with documents (for in-place processing)
    variables: Dict = None
    document_id: str = None  # For GUI: which document window owns this

    def __post_init__(self):
        if self.variables is None:
            self.variables = {}
        # If documents_folder not specified, assume it's in output_path/documents
        if self.documents_folder is None:
            self.documents_folder = self.output_path / "documents"


@dataclass 
class ProcessingResult:
    """Result of folder processing"""
    task_id: str
    success: bool
    folder_path: Path
    output_path: Path
    error_message: str = ""
    execution_time: float = 0.0
    files_processed: List[str] = None
    
    def __post_init__(self):
        if self.files_processed is None:
            self.files_processed = []





class ProcessingBackend(ABC):
    """Backend interface for processing folders"""
    
    def __init__(self, app=None):
        self.app = app
        self.backend_name = "base"
        self.progress_callback: Optional[Callable] = None
        
    @abstractmethod
    def process_folders(self, tasks: List[FolderTask]) -> Dict[str, ProcessingResult]:
        """
        Process multiple folders and return results.
        
        For sync backends: Block until all complete, return results
        For async backends: Submit tasks, return empty dict, use get_result() later
        """
        pass
    
    @abstractmethod
    def get_status(self, task_id: str) -> ProcessingStatus:
        """Get status of a specific task"""
        pass
    
    @abstractmethod
    def get_result(self, task_id: str) -> Optional[ProcessingResult]:
        """Get result of completed task (None if not ready)"""
        pass
    
    @abstractmethod
    def cancel_task(self, task_id: str) -> bool:
        """Cancel specific task"""
        pass
    
    @abstractmethod
    def cancel_all(self) -> bool:
        """Cancel all processing"""
        pass
    
    @abstractmethod
    def shutdown(self) -> bool:
        """Clean shutdown - MUST stop all processing and cleanup"""
        pass
    
    @abstractmethod
    def initialize(self) -> bool:
        """Initialize the backend and test any required connections/services"""
        pass
    
    @property
    @abstractmethod
    def is_initialized(self) -> bool:
        """Check if backend is properly initialized"""
        pass
    
    # Optional features
    def set_progress_callback(self, callback: Callable[[str, Dict], None]):
        """Set callback for progress updates: callback(task_id, progress_data)"""
        self.progress_callback = callback
    
    def _notify_progress(self, task_id: str, progress_data: Dict):
        """Notify progress if callback is set"""
        if self.progress_callback:
            try:
                self.progress_callback(task_id, progress_data)
            except Exception:
                pass  # Don't let callback errors break processing
    
    @property
    def supports_async(self) -> bool:
        """True if backend supports async processing (submit + check status)"""
        return False
    
    @property  
    def supports_multiple_instances(self) -> bool:
        """True if multiple CLI instances can safely use this backend"""
        return False
    
    @property
    def requires_external_services(self) -> bool:
        """True if backend needs Redis, Celery, etc."""
        return False
    
    def list_active_tasks(self) -> List[str]:
        """List active task IDs (optional)"""
        return []
    
    # Backend capability methods
    def supports_worker_management(self) -> bool:
        """True if backend supports start/stop/restart worker commands"""
        return False
    
    def supports_worker_status(self) -> bool:
        """True if backend supports worker status monitoring"""
        return False
    
    def supports_health_check(self) -> bool:
        """True if backend supports health checks"""
        return False
    
    def supports_task_purging(self) -> bool:
        """True if backend supports purging pending tasks"""
        return False
    
    def supports_database_flush(self) -> bool:
        """True if backend supports flushing database (Redis)"""
        return False
    
    def get_supported_commands(self) -> List[str]:
        """Get list of supported backend commands for this backend"""
        commands = ["select", "info"]  # These are always supported
        
        if self.supports_worker_management():
            commands.extend(["start", "stop", "restart"])
        
        if self.supports_worker_status():
            commands.append("status")
        
        if self.supports_health_check():
            commands.append("health")
        
        if self.supports_task_purging():
            commands.append("purge")
        
        if self.supports_database_flush():
            commands.append("flush")
        
        # Activity monitor is always supported (shows task status)
        commands.append("activity-monitor")
        
        return commands


def create_folder_task(folder_path: Path, output_path: Path, plan_config: Dict,
                      workflow_name: str = "default", variables: Dict = None,
                      document_id: str = None, documents_folder: Path = None) -> FolderTask:
    """Helper to create a folder task"""
    return FolderTask(
        task_id=str(uuid.uuid4()),
        folder_path=folder_path,
        plan_config=plan_config,
        workflow_name=workflow_name,
        output_path=output_path,
        documents_folder=documents_folder,
        variables=variables or {},
        document_id=document_id
    ) 