"""
Add Mobile View

Mobile-specific view for adding content that integrates with the main window's view manager.
Uses AddContentView which follows the BaseView pattern like LibraryView.
"""

import logging

logger = logging.getLogger(__name__)


class MobileAddView:
    """Mobile view wrapper for add content that integrates with main window view manager"""
    
    def __init__(self, app, on_content_added=None, option_id=None):
        """Initialize the mobile add view"""
        from fichero.windows.add.add_content import AddContentView
        
        # Create the AddContentView which handles everything (BaseView, toolbars, etc.)
        self.add_content_view = AddContentView(app, on_content_added=self._handle_content_added, option_id=option_id)
        self.on_content_added = on_content_added
        
        logger.info("MobileAddView initialized using AddContentView")
    
    def create(self):
        """Create the add mobile view UI - return the AddContentView container"""
        return self.add_content_view.get_container()
    
    def get_container(self):
        """Get the container for this view"""
        return self.add_content_view.get_container()
    
    def _handle_content_added(self, data):
        """Handle content selection from AddContentView"""
        try:
            option_id = data.get('option_id')
            if option_id:
                logger.info(f"Mobile add option selected: {option_id}")
                
                # For mobile, navigate to specific add option view using the app's window/view manager
                self._show_mobile_add_option_view(option_id)
            
            # Call original callback if provided
            if self.on_content_added:
                self.on_content_added(data)
                
        except Exception as e:
            logger.error(f"Failed to handle content added in mobile view: {e}")
    
    def _show_mobile_add_option_view(self, option_id: str):
        """Show specific add option view using the mobile view manager"""
        try:
            # Use the app's window view manager to show specific add views
            if hasattr(self.add_content_view.app, 'window_view_manager') and hasattr(self.add_content_view.app.window_view_manager, 'mobile_view_manager'):
                mobile_view_manager = self.add_content_view.app.window_view_manager.mobile_view_manager
                
                # Create the appropriate view based on option_id
                view = self._create_add_option_view(option_id)
                if view:
                    # Show the view using the mobile view manager
                    mobile_view_manager.show_view(view)
                    logger.info(f"Navigated to {option_id} add view on mobile")
                else:
                    logger.error(f"Failed to create view for option: {option_id}")
            else:
                logger.error("Mobile view manager not available")
                
        except Exception as e:
            logger.error(f"Failed to show mobile add option view {option_id}: {e}")
    
    def _create_add_option_view(self, option_id: str):
        """Create the appropriate add option view"""
        try:
            # Import and create the appropriate view based on option_id
            if option_id == 'file':
                from fichero.windows.add.views.file_view import FileAddView
                return FileAddView(self.add_content_view.app, on_back=self._on_back_from_option, on_content_added=self._handle_final_content_added)
            elif option_id == 'folder':
                from fichero.windows.add.views.folder_view import FolderAddView
                return FolderAddView(self.add_content_view.app, on_back=self._on_back_from_option, on_content_added=self._handle_final_content_added)
            elif option_id == 'url':
                from fichero.windows.add.views.url_view import URLAddView
                return URLAddView(self.add_content_view.app, on_back=self._on_back_from_option, on_content_added=self._handle_final_content_added)
            elif option_id == 'website':
                from fichero.windows.add.views.website_view import WebsiteAddView
                return WebsiteAddView(self.add_content_view.app, on_back=self._on_back_from_option, on_content_added=self._handle_final_content_added)
            elif option_id == 'camera':
                from fichero.windows.add.views.camera_view import CameraAddView
                return CameraAddView(self.add_content_view.app, on_back=self._on_back_from_option, on_content_added=self._handle_final_content_added)
            else:
                logger.warning(f"Unknown add option: {option_id}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to create add option view for {option_id}: {e}")
            return None
    
    def _on_back_from_option(self):
        """Handle back navigation from specific add option views"""
        try:
            # Use the mobile view manager to go back
            if hasattr(self.add_content_view.app, 'window_view_manager') and hasattr(self.add_content_view.app.window_view_manager, 'mobile_view_manager'):
                mobile_view_manager = self.add_content_view.app.window_view_manager.mobile_view_manager
                result = mobile_view_manager.go_back()
                logger.info(f"Back navigation from add option view: {result}")
            else:
                logger.error("Mobile view manager not available for back navigation")
                
        except Exception as e:
            logger.error(f"Failed to navigate back from add option view: {e}")
    
    def _handle_final_content_added(self, data):
        """Handle final content addition from specific views"""
        try:
            logger.info(f"Final content added on mobile: {data}")
            
            # Call original callback if provided
            if self.on_content_added:
                self.on_content_added(data)
            
            # Navigate back to main library view
            if hasattr(self.add_content_view.app, 'window_view_manager') and hasattr(self.add_content_view.app.window_view_manager, 'mobile_view_manager'):
                mobile_view_manager = self.add_content_view.app.window_view_manager.mobile_view_manager
                # Go back twice: once from the specific add view, once from the main add view
                mobile_view_manager.go_back()  # Back to main add view
                mobile_view_manager.go_back()  # Back to library view
                logger.info("Navigated back to library after content addition")
            
        except Exception as e:
            logger.error(f"Failed to handle final content added: {e}")
    
    def show(self):
        """Show method for compatibility"""
        if hasattr(self.add_content_view, 'show'):
            self.add_content_view.show()
        logger.info("Add mobile view shown")
    
    def hide(self):
        """Hide method for compatibility"""
        if hasattr(self.add_content_view, 'hide'):
            self.add_content_view.hide()
        logger.info("Add mobile view hidden")
