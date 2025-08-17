"""
Processing Controller

Handles business logic and processing workflow for the processing window.
Coordinates between components and manages the actual processing operations.
"""

import toga
import asyncio
import logging
from pathlib import Path
from typing import Optional, Callable
import gettext

# Use the global _ function for translations (same as about_window.py)
try:
    _ = gettext.gettext
except:
    def _(text): return text

logger = logging.getLogger(__name__)


class ProcessingController:
    """Handles processing workflow and business logic"""
    
    def __init__(self, app):
        """Initialize processing controller"""
        self.app = app
        
        # Processing completion callbacks
        self._processing_complete_callbacks: list[Callable] = []
        self._processing_stopped_callbacks: list[Callable] = []
    
    def add_processing_complete_listener(self, callback: Callable):
        """Add callback for processing completion"""
        self._processing_complete_callbacks.append(callback)
    
    def add_processing_stopped_listener(self, callback: Callable):
        """Add callback for processing stopped"""
        self._processing_stopped_callbacks.append(callback)
    
    async def get_output_location(self, selected_folder: Path) -> Optional[Path]:
        """Get output location from user"""
        try:
            # Get desktop path cross-platform
            desktop_path = Path.home() / "Desktop"
            if not desktop_path.exists():
                desktop_path = Path.home()
            
            folder_name = selected_folder.name
            suggested_name = f"{folder_name}_processed"
            
            # Use SelectFolderDialog
            parent_path = await self.app.dialog(toga.SelectFolderDialog(
                title="Choose where to save processed results...",
                initial_directory=desktop_path
            ))
            
            if not parent_path:
                return None
            
            # Create output path
            output_path = Path(parent_path) / suggested_name
            
            # Confirm if folder exists
            if output_path.exists():
                continue_processing = await self.app.dialog(toga.ConfirmDialog(
                    _("document_continue_processing"),
                    _("document_output_exists").format(name=output_path.name)
                ))
                if not continue_processing:
                    return None
            
            return output_path
            
        except Exception as e:
            logger.error(f"Error getting output location: {e}")
            await self.app.dialog(toga.ErrorDialog("Error", f"Failed to get output location: {e}"))
            return None
    
    async def start_processing(self, progress_display, selected_folder: Path, output_path: Path, 
                             plan: str, workflow: str) -> bool:
        """Start the processing operation"""
        try:
            workflow_to_use = workflow or "default"
            success = progress_display.start_processing(
                selected_folder, output_path, plan, workflow_to_use
            )
            
            if not success:
                await self.app.dialog(toga.ErrorDialog("Error", "Failed to start processing"))
                return False
            
            logger.info(f"Processing started: {selected_folder} -> {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error starting processing: {e}")
            await self.app.dialog(toga.ErrorDialog("Error", f"Failed to start processing: {e}"))
            return False
    
    async def stop_processing(self, progress_display) -> bool:
        """Stop current processing with confirmation"""
        try:
            # Confirm stop
            confirm = await self.app.dialog(toga.ConfirmDialog(
                _("document_stop_processing"),
                _("document_stop_confirm")
            ))
            
            if confirm:
                # Stop processing
                completed, failed = progress_display.stop_processing()
                
                # Notify listeners
                for callback in self._processing_stopped_callbacks:
                    try:
                        callback()
                    except Exception as e:
                        logger.error(f"Error in processing stopped callback: {e}")
                
                logger.info(f"Processing stopped: {completed} completed, {failed} failed")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error stopping processing: {e}")
            await self.app.dialog(toga.ErrorDialog("Error", f"Failed to stop processing: {e}"))
            return False
    
    def on_processing_complete(self, completed_tasks: int, failed_tasks: int):
        """Handle processing completion"""
        logger.info(f"Processing completed: {completed_tasks} completed, {failed_tasks} failed")
        
        # Notify listeners
        for callback in self._processing_complete_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in processing complete callback: {e}")
    
    def on_processing_stopped(self):
        """Handle processing stopped"""
        logger.info("Processing was stopped by user")
        
        # Notify listeners  
        for callback in self._processing_stopped_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in processing stopped callback: {e}")
    
    async def show_completion_dialog(self, completed_tasks: int, failed_tasks: int):
        """Show processing completion dialog"""
        if failed_tasks == 0:
            message = f"Processing completed successfully!\n\n{completed_tasks} tasks completed."
            await self.app.dialog(toga.InfoDialog("Processing Complete", message))
        else:
            message = f"Processing completed with some errors.\n\n{completed_tasks} tasks completed, {failed_tasks} failed."
            await self.app.dialog(toga.InfoDialog("Processing Complete", message))
    
    def validate_processing_inputs(self, selected_folder: Optional[Path], plan: Optional[str]) -> tuple[bool, str]:
        """Validate inputs for processing"""
        if not selected_folder:
            return False, "Please select a folder to process"
        
        if not selected_folder.exists():
            return False, "Selected folder does not exist"
        
        if not plan:
            return False, "Please select a processing plan"
        
        return True, "" 