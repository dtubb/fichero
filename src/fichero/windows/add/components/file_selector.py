"""
File Selector Component

UI component for selecting files to add to the library.
Uses Toga's OpenFileDialog for desktop platforms.
"""

import toga
from toga.style import Pack
from toga.constants import ROW
import logging
from typing import Optional, Callable, List
from pathlib import Path

# Use builtin _ function installed by translation.install()

logger = logging.getLogger(__name__)


class FileSelector:
    """File selector component using Toga's native file dialog"""
    
    def __init__(self, app: toga.App):
        """Initialize file selector"""
        self.app = app
        self.on_files_selected: Optional[Callable] = None
        self.selected_files: List[Path] = []
    
    async def execute(self) -> List[Path]:
        """
        Execute file selection using Toga's OpenFileDialog.
        
        Returns:
            List[Path]: Selected file paths, empty list if cancelled
        """
        try:
            logger.info("Opening file selection dialog")
            
            # Create file dialog with common file types
            file_types = [
                'pdf', 'doc', 'docx', 'txt', 'rtf',  # Documents
                'jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff',  # Images
                'mp4', 'mov', 'avi', 'mkv',  # Videos
                'mp3', 'wav', 'aac', 'm4a',  # Audio
                'zip', 'rar', '7z'  # Archives
            ]
            
            dialog = toga.OpenFileDialog(
                title=_("Select Files to Add to Library"),
                file_types=file_types,
                multiple_select=True
            )
            
            # Show dialog and get result
            selected_files = await self.app.main_window.dialog(dialog)
            
            if selected_files:
                self.selected_files = selected_files if isinstance(selected_files, list) else [selected_files]
                logger.info(f"Selected {len(self.selected_files)} files")
                
                # Notify callback if registered
                if self.on_files_selected:
                    self.on_files_selected(self.selected_files)
                
                return self.selected_files
            else:
                logger.info("File selection cancelled")
                return []
                
        except Exception as e:
            logger.error(f"Failed to select files: {e}")
            return []
    
    def create(self):
        """Create the file selector UI (for legacy compatibility)"""
        container = toga.Box(
            style=Pack(
                direction=ROW,
                margin=(0, 0, 10, 0)
            )
        )
        
        # Select files button
        select_button = toga.Button(
            _("Select Files"),
            on_press=self._on_select_files,
            style=Pack(flex=0, margin=(0, 10, 0, 0))
        )
        container.add(select_button)
        
        # Selected files label
        self.files_label = toga.Label(
            _("No files selected"),
            style=Pack(flex=1)
        )
        container.add(self.files_label)
        
        return container
    
    async def _on_select_files(self, widget):
        """Handle file selection button press (legacy compatibility)"""
        selected_files = await self.execute()
        if selected_files:
            self.files_label.text = _("%(count)d files selected") % {'count': len(selected_files)}
    
    def register_callback(self, callback: Callable):
        """Register callback for when files are selected"""
        self.on_files_selected = callback


# Use builtin _ function installed by translation.install()
