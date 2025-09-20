"""
Add Window for Fichero - Desktop Window Implementation

Desktop window wrapper that uses the shared AddContentView component.
Follows the same pattern as AboutWindow, SettingsWindow, etc.
"""

import logging
from typing import Optional, Callable
import toga

# Use builtin _ function installed by translation.install()

logger = logging.getLogger(__name__)


class AddWindow:
    """Desktop add window that uses the shared AddContentView component"""
    
    def __init__(self, app: toga.App, on_content_added: Optional[Callable] = None, option_id: Optional[str] = None):
        """Initialize the add window"""
        self.app = app
        self.on_content_added = on_content_added
        self.option_id = option_id
        
        self.window = toga.Window(
            title=_("Add to Library") if _("Add to Library") != "Add to Library" else "Add to Library",
            size=(600, 700),
            resizable=True
        )
        
        # Import and create the shared add content view
        from fichero.windows.add.add_content import AddContentView
        self.add_content_view = AddContentView(app, on_content_added=self._handle_content_added, option_id=option_id)
        self.window.content = self.add_content_view.get_container()
        
        # Center the window
        self._center_window()
        
        logger.info("AddWindow initialized")
    
    def _center_window(self):
        """Center the window on screen"""
        try:
            # Get the primary screen dimensions
            screen = self.app.screens[0]  # Primary screen
            screen_width = screen.size.width
            screen_height = screen.size.height
            
            # Calculate center position
            window_width = self.window.size.width
            window_height = self.window.size.height
            
            center_x = (screen_width - window_width) // 2
            center_y = (screen_height - window_height) // 2
            
            # Set the position
            self.window.position = (center_x, center_y)
        except Exception:
            # If centering fails, just use default position
            pass
    
    def _handle_content_added(self, data):
        """Handle content selection from AddContentView"""
        try:
            option_id = data.get('option_id')
            if option_id:
                logger.info(f"Content added with option: {option_id}")
                
                # For desktop, navigate to specific add option view
                self._show_add_option_view(option_id)
            
            # Call original callback if provided
            if self.on_content_added:
                self.on_content_added(data)
                
        except Exception as e:
            logger.error(f"Failed to handle content added: {e}")
    
    def _show_add_option_view(self, option_id: str):
        """Show specific add option view in the window"""
        try:
            # Import the appropriate view based on option_id
            if option_id == 'file':
                from fichero.windows.add.views.file_view import FileAddView
                view = FileAddView(self.app, on_back=self._on_back_to_main, on_content_added=self._handle_final_content_added)
            elif option_id == 'folder':
                from fichero.windows.add.views.folder_view import FolderAddView
                view = FolderAddView(self.app, on_back=self._on_back_to_main, on_content_added=self._handle_final_content_added)
            elif option_id == 'url':
                from fichero.windows.add.views.url_view import URLAddView
                view = URLAddView(self.app, on_back=self._on_back_to_main, on_content_added=self._handle_final_content_added)
            elif option_id == 'website':
                from fichero.windows.add.views.website_view import WebsiteAddView
                view = WebsiteAddView(self.app, on_back=self._on_back_to_main, on_content_added=self._handle_final_content_added)
            elif option_id == 'camera':
                from fichero.windows.add.views.camera_view import CameraAddView
                view = CameraAddView(self.app, on_back=self._on_back_to_main, on_content_added=self._handle_final_content_added)
            else:
                logger.warning(f"Unknown add option: {option_id}")
                return
            
            # Replace window content with the specific view
            self.window.content = view.get_container()
            logger.info(f"Switched to {option_id} add view")
            
        except Exception as e:
            logger.error(f"Failed to show add option view {option_id}: {e}")
    
    def _on_back_to_main(self):
        """Handle back navigation to main add content"""
        try:
            # Restore the main add content
            self.window.content = self.add_content_view.get_container()
            logger.info("Returned to main add content")
        except Exception as e:
            logger.error(f"Failed to navigate back to main add content: {e}")
    
    def _handle_final_content_added(self, data):
        """Handle final content addition from specific views"""
        try:
            logger.info(f"Final content added: {data}")
            
            # Call original callback if provided
            if self.on_content_added:
                self.on_content_added(data)
            
            # Close the window after successful addition
            self.close()
            
        except Exception as e:
            logger.error(f"Failed to handle final content added: {e}")
    
    def show(self):
        """Show the add window"""
        self.window.show()
        logger.info("Add window shown")
    
    def hide(self):
        """Hide the add window"""
        self.window.hide()
        logger.info("Add window hidden")
    
    def close(self):
        """Close the add window"""
        if self.window:
            self.window.close()
            self.window = None
            logger.info("Add window closed")
