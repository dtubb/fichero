"""
File Add View

BaseView for adding files to the library using Toga's OpenFileDialog.
Follows established navigation patterns and integrates with library system.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import logging
from typing import Optional, Callable, List
from pathlib import Path

from fichero.shared.views.base_view import BaseView
from fichero.shared.toolbars import TopToolbar, BottomToolbar

# Use builtin _ function installed by translation.install()

logger = logging.getLogger(__name__)


class FileAddView(BaseView):
    """View for adding files to the library"""
    
    def __init__(self, app: toga.App, on_content_added: Optional[Callable] = None):
        """Initialize file add view"""
        self.on_content_added = on_content_added
        self.selected_files = []

        # Initialize BaseView first
        super().__init__(app, is_mobile=app.is_mobile)
        
        # Create toolbars after BaseView is initialized
        self._create_toolbars()
        
        logger.info("File Add View initialized")
    
    def _create_toolbars(self):
        """Create top and bottom toolbars for file add view"""
        try:
            # Create top toolbar without coordinator (no edit mode for modal views)
            self.top_toolbar = TopToolbar(
                app=self.app,
                title="Add Files",
                auto_mobile_nav=True,
                is_mobile=self.is_mobile
            )

            # NavigationController integration is handled automatically by TopToolbar

            # Add centered title for desktop (preserving button alignment)
            if not self.is_mobile:
                self.top_toolbar.add_centered_title_only(
                    title_text="Add Files",
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

            logger.info("File add view toolbars created successfully")
        except Exception as e:
            logger.error(f"Failed to create file add toolbars: {e}")
    
    def _create_content(self):
        """Create the file selection interface"""
        # Main instructions
        instructions_label = toga.Label(
            _("Add Files to Library"),
            style=Pack(margin=10)
        )
        self.content_container.add(instructions_label)
        
        # Description
        description_label = toga.Label(
            _("Select files from your computer to add to your library. Multiple files can be selected at once."),
            style=Pack(margin=(0, 10, 10, 10))
        )
        self.content_container.add(description_label)
        
        # Supported formats info
        formats_label = toga.Label(
            _("Supported formats: PDF, DOC, DOCX, TXT, JPG, PNG, MP4, MP3, ZIP, and more"),
            style=Pack(margin=(0, 10, 20, 10))
        )
        self.content_container.add(formats_label)
        
        # Select files button
        self.select_button = toga.Button(
            _("Select Files"),
            on_press=self._on_select_files,
            style=Pack(margin=10)
        )
        self.content_container.add(self.select_button)
        
        # Selected files display
        self.status_label = toga.Label(
            _("No files selected"),
            style=Pack(margin=10)
        )
        self.content_container.add(self.status_label)
        
        # Files list container
        self.files_container = toga.Box(
            style=Pack(direction=COLUMN, margin=10)
        )
        self.content_container.add(self.files_container)
        
        # Add to library button
        self.add_button = toga.Button(
            _("Add Selected Files to Library"),
            on_press=self._on_add_to_library,
            enabled=False,
            style=Pack(margin=10)
        )
        self.content_container.add(self.add_button)
        
        # Instructions section
        instructions_container = toga.Box(
            style=Pack(direction=COLUMN, margin=20)
        )
        
        instructions_title = toga.Label(
            _("Instructions:"),
            style=Pack(margin=(0, 0, 10, 0))
        )
        instructions_container.add(instructions_title)
        
        steps = [
            _("1. Click 'Select Files' to open the file browser"),
            _("2. Choose one or more files to add"),
            _("3. Review your selection"),
            _("4. Click 'Add to Library' to complete")
        ]
        
        for step in steps:
            step_label = toga.Label(step, style=Pack(margin=(0, 0, 5, 20)))
            instructions_container.add(step_label)
        
        self.content_container.add(instructions_container)
    
    async def _on_select_files(self, widget):
        """Handle file selection"""
        try:
            logger.info("Opening file selection dialog")
            
            # Supported file types
            file_types = ['pdf', 'doc', 'docx', 'txt', 'rtf', 'jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 
                         'mp4', 'mov', 'avi', 'mkv', 'mp3', 'wav', 'aac', 'm4a', 'zip', 'rar', '7z']
            
            # Open file dialog
            dialog = toga.OpenFileDialog(
                title=_("Select Files to Add to Library"),
                file_types=file_types,
                multiple_select=True
            )
            
            selected_files = await self.app.main_window.dialog(dialog)
            
            if selected_files:
                self.selected_files = selected_files if isinstance(selected_files, list) else [selected_files]
                self._update_files_display()
                logger.info(f"Selected {len(self.selected_files)} files")
            else:
                self.status_label.text = _("Error selecting files. Please try again.")
                
        except Exception as e:
            logger.error(f"Failed to select files: {e}")
            self.status_label.text = _("No files selected")
    
    def _update_files_display(self):
        """Update the display of selected files"""
        try:
            count = len(self.selected_files)
            if count == 1:
                self.status_label.text = _("1 file selected")
            else:
                self.status_label.text = _("%(count)d files selected") % {'count': count}
            
            # Clear existing files display
            self.files_container.clear()
            
            # Show file names (limit to first 10 for display)
            display_files = self.selected_files[:10]
            for file_path in display_files:
                file_label = toga.Label(
                    str(file_path.name),
                    style=Pack(margin=(0, 0, 5, 20))
                )
                self.files_container.add(file_label)
            
            # Show "and X more" if there are more files
            if len(self.selected_files) > 10:
                more_label = toga.Label(
                    _("... and %(count)d more files") % {'count': len(self.selected_files) - 10},
                    style=Pack(margin=(0, 0, 5, 20))
                )
                self.files_container.add(more_label)
            
            # Enable add button
            self.add_button.enabled = True
            
        except Exception as e:
            logger.error(f"Failed to update files display: {e}")
    
    async def _on_add_to_library(self, widget):
        """Add selected files to library"""
        try:
            if not self.selected_files:
                return
            
            self.status_label.text = _("Adding files to library...")
            self.add_button.enabled = False
            
            # Call the callback with selected files
            if self.on_content_added:
                await self.on_content_added({'option_id': 'file', 'files': self.selected_files, 'action': 'added'})
                self.status_label.text = _("Files added successfully!")
                logger.info(f"Successfully added {len(self.selected_files)} files to library")
            
        except Exception as e:
            logger.error(f"Failed to add files to library: {e}")
            self.status_label.text = _("Error adding files. Please try again.")
            self.add_button.enabled = True 