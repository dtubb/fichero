"""
Folder Selector Component

UI component for selecting folders to add to the library.
Uses Toga's SelectFolderDialog for desktop platforms.
"""

import toga
from toga.style import Pack
from toga.constants import ROW
import logging
from typing import Optional, Callable, List
from pathlib import Path

# Use builtin _ function installed by translation.install()

logger = logging.getLogger(__name__)


class FolderSelector:
    """Folder selector component using Toga's native folder dialog"""
    
    def __init__(self, app: toga.App):
        """Initialize folder selector"""
        self.app = app
        self.on_folders_selected: Optional[Callable] = None
        self.selected_folders: List[Path] = []
    
    async def execute(self) -> List[Path]:
        """
        Execute folder selection using Toga's SelectFolderDialog.
        
        Returns:
            List[Path]: Selected folder paths, empty list if cancelled
        """
        try:
            logger.info("Opening folder selection dialog")
            
            dialog = toga.SelectFolderDialog(
                title=_("Select Folders to Add to Library"),
                multiple_select=True  # Allow multiple folder selection
            )
            
            # Show dialog and get result
            selected_folders = await self.app.main_window.dialog(dialog)
            
            if selected_folders:
                self.selected_folders = selected_folders if isinstance(selected_folders, list) else [selected_folders]
                logger.info(f"Selected {len(self.selected_folders)} folders")
                
                # Notify callback if registered
                if self.on_folders_selected:
                    self.on_folders_selected(self.selected_folders)
                
                return self.selected_folders
            else:
                logger.info("Folder selection cancelled")
                return []
                
        except Exception as e:
            logger.error(f"Failed to select folders: {e}")
            return []
    
    def create(self):
        """Create the folder selector UI (for legacy compatibility)"""
        container = toga.Box(
            style=Pack(
                direction=ROW,
                margin=(0, 0, 10, 0)
            )
        )
        
        # Select folders button
        select_button = toga.Button(
            _("Select Folders"),
            on_press=self._on_select_folders,
            style=Pack(flex=0, margin=(0, 10, 0, 0))
        )
        container.add(select_button)
        
        # Selected folders label
        self.folders_label = toga.Label(
            _("No folders selected"),
            style=Pack(flex=1)
        )
        container.add(self.folders_label)
        
        return container
    
    async def _on_select_folders(self, widget):
        """Handle folder selection button press (legacy compatibility)"""
        selected_folders = await self.execute()
        if selected_folders:
            count = len(selected_folders)
            if count == 1:
                self.folders_label.text = _("1 folder selected")
            else:
                self.folders_label.text = _("%(count)d folders selected") % {'count': count}
    
    def register_callback(self, callback: Callable):
        """Register callback for when folders are selected"""
        self.on_folders_selected = callback


# Use builtin _ function installed by translation.install()
