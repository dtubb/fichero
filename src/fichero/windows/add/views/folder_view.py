"""
Folder Add View

BaseView for adding folders to the library using Toga's SelectFolderDialog.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW, CENTER
import logging
from typing import Optional, Callable, List
from pathlib import Path

from fichero.shared.views.base_view import BaseView
from fichero.shared.toolbars import TopToolbar, BottomToolbar

# Use builtin _ function installed by translation.install()

logger = logging.getLogger(__name__)


class FolderAddView(BaseView):
    """View for adding folders to the library"""
    
    def __init__(self, app: toga.App, on_content_added: Optional[Callable] = None):
        """Initialize folder add view"""
        self.on_content_added = on_content_added
        self.selected_folders: List[Path] = []

        # Initialize BaseView first
        super().__init__(app, is_mobile=app.is_mobile)
        
        # Create toolbars after BaseView is initialized
        self._create_toolbars()
        
        logger.info("Folder Add View initialized")
    
    def _create_toolbars(self):
        """Create top and bottom toolbars for folder add view"""
        try:
            # Create top toolbar without coordinator (no edit mode for modal views)
            self.top_toolbar = TopToolbar(
                app=self.app,
                title="Add Folders",
                auto_mobile_nav=True,
                is_mobile=self.is_mobile
            )

            # NavigationController integration is handled automatically by TopToolbar

            # Add centered title for desktop (preserving button alignment)
            if not self.is_mobile:
                self.top_toolbar.add_centered_title_only(
                    title_text="Add Folders",
                    on_title_click=None
                )

            # Create bottom toolbar without coordinator (no edit mode for modal views)
            self.bottom_toolbar = BottomToolbar(
                app=self.app,
                is_mobile=self.is_mobile
            )

            # Set toolbars on the view
            self.set_top_toolbar(self.top_toolbar)
            self.set_bottom_toolbar(self.bottom_toolbar)

            logger.info("Folder add view toolbars created successfully")
        except Exception as e:
            logger.error(f"Failed to create folder add toolbars: {e}")
    
    def _create_content(self):
        """Create the view content"""
        # Title
        title = toga.Label(
            _("Add Folders to Library"),
            style=Pack(
                font_size=20,
                font_weight="bold",
                text_align=CENTER,
                margin=20,
                color="#1a1a1a"
            )
        )
        self.content_container.add(title)
        
        # Description
        description = toga.Label(
            _("Select entire folders to add to your library. All files within the folders will be included."),
            style=Pack(
                font_size=14,
                text_align=CENTER,
                margin=20,
                color="#666666"
            )
        )
        self.content_container.add(description)
        
        # Select folders button
        self.select_button = toga.Button(
            _("Select Folders"),
            on_press=self._on_select_folders,
            style=Pack(margin=10)
        )
        self.content_container.add(self.select_button)
        
        # Selected folders display
        self.status_label = toga.Label(
            _("No folders selected"),
            style=Pack(margin=10)
        )
        self.content_container.add(self.status_label)
        
        # Folders list container
        self.folders_container = toga.Box(
            style=Pack(direction=COLUMN, margin=10)
        )
        self.content_container.add(self.folders_container)
        
        # Add to library button
        self.add_button = toga.Button(
            _("Add Selected Folders to Library"),
            on_press=self._on_add_to_library,
            enabled=False,
            style=Pack(margin=10)
        )
        self.content_container.add(self.add_button)
    
    async def _on_select_folders(self, widget):
        """Handle folder selection"""
        try:
            logger.info("Opening folder selection dialog")
            
            dialog = toga.SelectFolderDialog(
                title=_("Select Folders to Add to Library"),
                multiple_select=True  # Allow multiple folder selection
            )
            
            selected_folders = await self.app.main_window.dialog(dialog)
            
            if selected_folders:
                self.selected_folders = selected_folders if isinstance(selected_folders, list) else [selected_folders]
                self._update_folders_display()
                logger.info(f"Selected {len(self.selected_folders)} folders")
            else:
                self.status_label.text = _("Error selecting folders. Please try again.")
                
        except Exception as e:
            logger.error(f"Failed to select folders: {e}")
            self.status_label.text = _("No folders selected")
    
    def _update_folders_display(self):
        """Update the display of selected folders"""
        try:
            count = len(self.selected_folders)
            if count == 1:
                self.status_label.text = _("1 folder selected")
            else:
                self.status_label.text = _("%(count)d folders selected") % {'count': count}
            
            # Clear existing folders display
            self.folders_container.clear()
            
            # Show folder names (limit to first 10 for display)
            display_folders = self.selected_folders[:10]
            for folder_path in display_folders:
                folder_label = toga.Label(
                    str(folder_path.name),
                    style=Pack(margin=(0, 0, 5, 20))
                )
                self.folders_container.add(folder_label)
            
            # Show "and X more" if there are more folders
            if len(self.selected_folders) > 10:
                more_label = toga.Label(
                    _("... and %(count)d more folders") % {'count': len(self.selected_folders) - 10},
                    style=Pack(margin=(0, 0, 5, 20))
                )
                self.folders_container.add(more_label)
            
            # Enable add button
            self.add_button.enabled = True
            
        except Exception as e:
            logger.error(f"Failed to update folders display: {e}")
    
    async def _on_add_to_library(self, widget):
        """Add selected folders to library"""
        try:
            if not self.selected_folders:
                return
            
            self.status_label.text = _("Adding folders to library...")
            self.add_button.enabled = False
            
            # Call the callback with selected folders
            if self.on_content_added:
                await self.on_content_added({'option_id': 'folder', 'folders': self.selected_folders, 'action': 'added'})
                self.status_label.text = _("Folders added successfully!")
                logger.info(f"Successfully added {len(self.selected_folders)} folders to library")
            
        except Exception as e:
            logger.error(f"Failed to add folders to library: {e}")
            self.status_label.text = _("Error adding folders. Please try again.")
            self.add_button.enabled = True 