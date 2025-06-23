"""
Enhanced Workflow Logger

Logs workflow execution to a text file with improved formatting.
Features clear step separators, better whitespace, and organized output.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)


class WorkflowLogger:
    """Enhanced workflow logger with improved formatting and readability"""
    
    def __init__(self, output_path: Path, workflow_name: str, task_id: str):
        self.workflow_name = workflow_name
        self.task_id = task_id
        
        # Create logs directory
        logs_dir = output_path / "logs"
        logs_dir.mkdir(exist_ok=True)
        
        # Create timestamped log file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_workflow_name = workflow_name.replace(" ", "_").replace("/", "_")
        self.log_file = logs_dir / f"workflow_{safe_workflow_name}_{timestamp}.log"
        
        # Log workflow start with enhanced formatting
        self._write_separator("WORKFLOW START")
        self._write_log(f"Workflow: {workflow_name}")
        self._write_log(f"Task ID: {task_id}")
        self._write_log(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._write_separator("WORKFLOW START")
        self._write_log("")  # Empty line for spacing
    
    def log_step_start(self, step_name: str, function_path: str, args: Dict[str, Any]):
        """Log step start with enhanced formatting"""
        self._write_separator(f"STEP START: {step_name}")
        self._write_log(f"Step: {step_name}")
        self._write_log(f"Function: {function_path}")
        self._write_log("Arguments:")
        
        # Format arguments with indentation
        for key, value in args.items():
            # Truncate long values for readability
            if isinstance(value, str) and len(str(value)) > 80:
                display_value = str(value)[:80] + "..."
            else:
                display_value = str(value)
            self._write_log(f"  {key}: {display_value}")
        
        self._write_log("")  # Empty line for spacing
    
    def log_step_complete(self, step_name: str, result: Dict[str, Any], execution_time: float):
        """Log step completion with enhanced formatting"""
        self._write_separator(f"STEP COMPLETE: {step_name}")
        self._write_log(f"Step: {step_name}")
        self._write_log(f"Duration: {execution_time:.2f} seconds")
        
        if result:
            self._write_log("Results:")
            # Format results with indentation
            for key, value in result.items():
                # Truncate long values for readability
                if isinstance(value, str) and len(str(value)) > 80:
                    display_value = str(value)[:80] + "..."
                else:
                    display_value = str(value)
                self._write_log(f"  {key}: {display_value}")
        
        self._write_separator(f"STEP COMPLETE: {step_name}")
        self._write_log("")  # Empty line for spacing
    
    def log_step_error(self, step_name: str, error_message: str, execution_time: float):
        """Log step error with enhanced formatting"""
        self._write_separator(f"STEP ERROR: {step_name}")
        self._write_log(f"Step: {step_name}")
        self._write_log(f"Duration: {execution_time:.2f} seconds")
        self._write_log(f"Error: {error_message}")
        self._write_separator(f"STEP ERROR: {step_name}")
        self._write_log("")  # Empty line for spacing
    
    def log_step_message(self, step_name: str, message: str):
        """Log a message from a step with enhanced formatting"""
        self._write_log(f"[{step_name}] {message}")
    
    def log_workflow_complete(self, success: bool, total_duration: float):
        """Log workflow completion with enhanced formatting"""
        self._write_separator("WORKFLOW COMPLETE")
        self._write_log(f"Workflow: {self.workflow_name}")
        self._write_log(f"Status: {'SUCCESS' if success else 'FAILED'}")
        self._write_log(f"Total Duration: {total_duration:.2f} seconds")
        self._write_log(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._write_separator("WORKFLOW COMPLETE")
    
    def _write_separator(self, title: str = ""):
        """Write a separator line with optional title"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        if title:
            separator = f"[{timestamp}] {'=' * 20} {title} {'=' * 20}"
        else:
            separator = f"[{timestamp}] {'=' * 60}"
        
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(separator + "\n")
        except Exception as e:
            logger.warning(f"Failed to write separator: {e}")
    
    def _write_log(self, message: str):
        """Write message to log file with timestamp"""
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] {message}\n")
        except Exception as e:
            logger.warning(f"Failed to write log: {e}") 