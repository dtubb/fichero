"""
Tool Logger Utility

Provides a shared logging interface for all tools that automatically routes output
to the appropriate destination:
- Workflow logs when running under workflow executor  
- Console when running in CLI mode

This eliminates the need for complex output capture and provides consistent logging.
"""

import logging
import threading
from typing import Optional

# Thread-local storage for workflow logger
_local = threading.local()

class ToolLogger:
    """
    Shared logger utility for tools.
    
    Automatically detects execution context and routes output appropriately:
    - When workflow_logger is set: routes to workflow logs
    - When workflow_logger is None: routes to console (CLI mode)
    """
    
    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        self.python_logger = logging.getLogger(f'fichero.tools.{tool_name}')
    
    @property
    def workflow_logger(self):
        """Get the current workflow logger (if any)"""
        return getattr(_local, 'workflow_logger', None)
    
    @property
    def step_name(self):
        """Get the current step name (if any)"""
        return getattr(_local, 'step_name', None)
    
    def info(self, message: str):
        """Log an info message"""
        if self.workflow_logger and self.step_name:
            # Route to workflow log
            self.workflow_logger.log_step_message(self.step_name, f"INFO: {message}")
        else:
            # Route to console (CLI mode)
            self.python_logger.info(message)
    
    def warning(self, message: str):
        """Log a warning message"""
        if self.workflow_logger and self.step_name:
            # Route to workflow log
            self.workflow_logger.log_step_message(self.step_name, f"WARNING: {message}")
        else:
            # Route to console (CLI mode)
            self.python_logger.warning(message)
    
    def error(self, message: str):
        """Log an error message"""
        if self.workflow_logger and self.step_name:
            # Route to workflow log
            self.workflow_logger.log_step_message(self.step_name, f"ERROR: {message}")
        else:
            # Route to console (CLI mode)
            self.python_logger.error(message)
    
    def progress(self, message: str):
        """Log a progress message"""
        if self.workflow_logger and self.step_name:
            # Route to workflow log
            self.workflow_logger.log_step_message(self.step_name, f"PROGRESS: {message}")
        else:
            # Route to console (CLI mode) - use info level for progress
            self.python_logger.info(f"PROGRESS: {message}")
    
    def success(self, message: str):
        """Log a success message"""
        if self.workflow_logger and self.step_name:
            # Route to workflow log
            self.workflow_logger.log_step_message(self.step_name, f"SUCCESS: {message}")
        else:
            # Route to console (CLI mode) - use info level for success
            self.python_logger.info(f"SUCCESS: {message}")
    
    def debug(self, message: str):
        """Log a debug message"""
        if self.workflow_logger and self.step_name:
            # Route to workflow log
            self.workflow_logger.log_step_message(self.step_name, f"DEBUG: {message}")
        else:
            # Route to console (CLI mode)
            self.python_logger.debug(message)


def set_workflow_context(workflow_logger, step_name: str):
    """
    Set the workflow context for the current thread.
    Called by workflow executor to enable workflow logging mode.
    """
    _local.workflow_logger = workflow_logger
    _local.step_name = step_name


def clear_workflow_context():
    """
    Clear the workflow context for the current thread.
    Called by workflow executor to return to CLI logging mode.
    """
    _local.workflow_logger = None
    _local.step_name = None


def get_tool_logger(tool_name: str) -> ToolLogger:
    """
    Get a tool logger instance.
    
    Usage in tools:
        from .utils.tool_logger import get_tool_logger
        
        logger = get_tool_logger('crop')
        logger.info("Processing image...")
        logger.progress("Checking files to process...")
        logger.success("Processing completed!")
    """
    return ToolLogger(tool_name) 