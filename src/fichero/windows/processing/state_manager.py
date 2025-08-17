"""
Processing State Manager

Centralized state management for the processing window.
Handles state transitions, validation, and coordination between components.
"""

import logging
from pathlib import Path
from typing import Optional, List, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class ProcessingState(Enum):
    """Processing window states"""
    FOLDER_SELECTION = "folder_selection"
    READY_TO_PROCESS = "ready_to_process" 
    PROCESSING = "processing"
    COMPLETED = "completed"


class ProcessingStateManager:
    """Manages processing window state and transitions"""
    
    def __init__(self):
        """Initialize state manager"""
        self.state = ProcessingState.FOLDER_SELECTION
        self.selected_folder: Optional[Path] = None
        self.current_plan: Optional[str] = None
        self.current_plan_filename: Optional[str] = None
        self.current_workflow: Optional[str] = None
        self.output_path: Optional[Path] = None
        
        # Event callbacks
        self._state_change_callbacks: List[Callable[[ProcessingState], None]] = []
        
    def add_state_change_listener(self, callback: Callable[[ProcessingState], None]):
        """Add a callback for state changes"""
        self._state_change_callbacks.append(callback)
        
    def remove_state_change_listener(self, callback: Callable[[ProcessingState], None]):
        """Remove a state change callback"""
        if callback in self._state_change_callbacks:
            self._state_change_callbacks.remove(callback)
    
    def _notify_state_change(self):
        """Notify listeners of state change"""
        for callback in self._state_change_callbacks:
            try:
                callback(self.state)
            except Exception as e:
                logger.error(f"Error in state change callback: {e}")
    
    def set_folder(self, folder_path: Optional[Path]):
        """Set selected folder and update state"""
        self.selected_folder = folder_path
        
        if folder_path is None:
            self.state = ProcessingState.FOLDER_SELECTION
        elif self.current_plan:
            self.state = ProcessingState.READY_TO_PROCESS
        else:
            # Stay in folder selection if no plan selected yet
            pass
            
        self._notify_state_change()
        logger.info(f"Folder set to: {folder_path}, State: {self.state}")
    
    def set_plan(self, plan_name: Optional[str], plan_filename: Optional[str] = None, workflow: Optional[str] = None):
        """Set selected plan and update state"""
        self.current_plan = plan_name
        self.current_plan_filename = plan_filename
        self.current_workflow = workflow
        
        if self.selected_folder and plan_name:
            self.state = ProcessingState.READY_TO_PROCESS
        
        self._notify_state_change()
        logger.info(f"Plan set to: {plan_name}, State: {self.state}")
    
    def start_processing(self, output_path: Path):
        """Start processing with given output path"""
        if not self.can_start_processing():
            raise ValueError("Cannot start processing in current state")
            
        self.output_path = output_path
        self.state = ProcessingState.PROCESSING
        self._notify_state_change()
        logger.info(f"Processing started, output: {output_path}")
    
    def complete_processing(self):
        """Mark processing as completed"""
        self.state = ProcessingState.COMPLETED
        self._notify_state_change()
        logger.info("Processing completed")
    
    def reset(self):
        """Reset to initial state"""
        self.state = ProcessingState.FOLDER_SELECTION
        self.selected_folder = None
        self.current_plan = None
        self.current_plan_filename = None
        self.current_workflow = None
        self.output_path = None
        self._notify_state_change()
        logger.info("State reset to folder selection")
    
    def can_start_processing(self) -> bool:
        """Check if processing can be started"""
        return (
            self.state == ProcessingState.READY_TO_PROCESS and
            self.selected_folder is not None and
            self.current_plan is not None
        )
    
    def is_processing(self) -> bool:
        """Check if currently processing"""
        return self.state == ProcessingState.PROCESSING
    
    def is_completed(self) -> bool:
        """Check if processing is completed"""
        return self.state == ProcessingState.COMPLETED
    
    def get_state_info(self) -> dict:
        """Get current state information"""
        return {
            'state': self.state,
            'folder': str(self.selected_folder) if self.selected_folder else None,
            'plan': self.current_plan,
            'plan_file': self.current_plan_filename,
            'workflow': self.current_workflow,
            'output': str(self.output_path) if self.output_path else None,
            'can_process': self.can_start_processing()
        } 