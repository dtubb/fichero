"""
Document Manager for Director Service

Coordinates between document windows and the director service,
routing tasks and progress updates appropriately.
"""

import logging
from typing import Dict, Optional
from pathlib import Path

from fichero.director.enums import TaskPriority

logger = logging.getLogger(__name__)


class DocumentManager:
    """
    Manages coordination between document windows and the director service.
    
    Features:
    - Register/unregister document windows
    - Route tasks from documents to director
    - Route progress updates back to correct documents
    - Track document → task mapping
    """
    
    def __init__(self, director):
        self.director = director
        self.active_documents: Dict[str, any] = {}  # document_id -> document_window
        self.document_tasks: Dict[str, str] = {}    # document_id -> task_id
        self.task_documents: Dict[str, str] = {}    # task_id -> document_id
        
        # Register for director progress updates
        self.director.register_progress_callback(self._on_progress_update)
        
        logger.info("DocumentManager initialized")
    
    def register_document(self, document_id: str, document_window):
        """Register a document window with the manager"""
        self.active_documents[document_id] = document_window
        logger.info(f"Document registered: {document_id}")
    
    def unregister_document(self, document_id: str):
        """Unregister a document window"""
        if document_id in self.active_documents:
            del self.active_documents[document_id]
            
            # Cancel any active task for this document
            if document_id in self.document_tasks:
                task_id = self.document_tasks[document_id]
                self.director.cancel_task(task_id)
                
                # Clean up mappings
                del self.document_tasks[document_id]
                self.task_documents.pop(task_id, None)
            
            logger.info(f"Document unregistered: {document_id}")
    
    def submit_document_task(self, document_id: str, task_config: Dict) -> str:
        """
        Submit a task from a document window
        
        Args:
            document_id: ID of the document submitting the task
            task_config: Task configuration containing:
                - folders: List of folder paths
                - plan_name: Name of plan to use
                - workflow_name: Name of workflow
                - priority: Optional priority level
        
        Returns:
            Task ID string
        """
        if document_id not in self.active_documents:
            raise ValueError(f"Document not registered: {document_id}")
        
        # Extract task parameters
        folders = [Path(f) for f in task_config.get("folders", [])]
        plan_name = task_config.get("plan_name")
        workflow_name = task_config.get("workflow_name", "default")
        priority_name = task_config.get("priority", "NORMAL")
        
        # Convert priority
        try:
            priority = TaskPriority[priority_name.upper()]
        except KeyError:
            priority = TaskPriority.NORMAL
        
        # Add document context
        document_context = {
            "document_id": document_id,
            "document_type": "window",
            **task_config.get("document_context", {})
        }
        
        # Submit task to director
        task_id = self.director.process_folders(
            folders=folders,
            plan_name=plan_name,
            workflow_name=workflow_name,
            document_context=document_context
        )
        
        # Track mappings
        self.document_tasks[document_id] = task_id
        self.task_documents[task_id] = document_id
        
        logger.info(f"Task submitted for document {document_id}: {task_id}")
        return task_id
    
    def get_document_task_status(self, document_id: str):
        """Get status of the current task for a document"""
        if document_id not in self.document_tasks:
            return None
        
        task_id = self.document_tasks[document_id]
        return self.director.get_task_status(task_id)
    
    def cancel_document_task(self, document_id: str) -> bool:
        """Cancel the current task for a document"""
        if document_id not in self.document_tasks:
            return False
        
        task_id = self.document_tasks[document_id]
        success = self.director.cancel_task(task_id)
        
        if success:
            # Clean up mappings
            del self.document_tasks[document_id]
            self.task_documents.pop(task_id, None)
        
        return success
    
    def _on_progress_update(self, task_id: str, progress_data: Dict):
        """Handle progress updates from director and route to correct document"""
        # Find which document this task belongs to
        document_id = self.task_documents.get(task_id)
        
        if document_id and document_id in self.active_documents:
            document_window = self.active_documents[document_id]
            
            # Send progress update to document window
            try:
                if hasattr(document_window, 'on_progress_update'):
                    document_window.on_progress_update(task_id, progress_data)
                elif hasattr(document_window, '_log_message'):
                    # Fallback to logging for basic updates
                    status = progress_data.get('status', 'unknown')
                    if status == 'started':
                        document_window._log_message(f"🚀 Processing started for {progress_data.get('folder_count', 0)} folders")
                    elif status == 'completed':
                        document_window._log_message("✅ Processing completed successfully!")
                    elif status == 'failed':
                        error = progress_data.get('error', 'Unknown error')
                        document_window._log_message(f"❌ Processing failed: {error}")
                    elif status == 'cancelled':
                        document_window._log_message("⏹️ Processing cancelled")
            except Exception as e:
                logger.warning(f"Failed to send progress update to document {document_id}: {e}")
        
        # Clean up completed tasks
        if progress_data.get('status') in ['completed', 'failed', 'cancelled']:
            self._cleanup_completed_task(task_id, document_id)
    
    def _cleanup_completed_task(self, task_id: str, document_id: str):
        """Clean up mappings for completed tasks"""
        if document_id and document_id in self.document_tasks:
            if self.document_tasks[document_id] == task_id:
                del self.document_tasks[document_id]
        
        self.task_documents.pop(task_id, None)
    
    def get_stats(self) -> Dict:
        """Get document manager statistics"""
        return {
            "active_documents": len(self.active_documents),
            "active_document_tasks": len(self.document_tasks),
            "document_ids": list(self.active_documents.keys())
        } 