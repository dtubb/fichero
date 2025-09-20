"""
About Mobile View

Mobile-specific view for the about screen that can be used in the main window.
Uses the standard base view pattern with consistent toolbars.
"""

import logging
from fichero.shared.views.base_view import BaseView
from fichero.windows.about.about_content import AboutContent

logger = logging.getLogger(__name__)


class AboutMobileView(BaseView):
    """Mobile view for about content that can be embedded in main window"""
    
    def __init__(self, app):
        """Initialize the mobile about view"""
        # Create the about content BEFORE calling super().__init__()
                # because BaseView.__init__ calls _create_content() which needs this
        self.about_content = AboutContent(app=app)
        
        # Initialize BaseView first
        super().__init__(app, is_mobile=app.is_mobile)
        
        # Create toolbars after BaseView is initialized
        self._create_toolbars()
        
        logger.info("AboutMobileView initialized")
    
    def create(self):
        """Create the about mobile view UI - return the full view container"""
        return self.get_container()
    
    def _create_toolbars(self):
        """Create top and bottom toolbars for about view"""
        try:
            from fichero.shared.toolbars.simple_top_toolbar import SimpleTopToolbar
            from fichero.shared.toolbars.bottom_toolbar import BottomToolbar
            
            # Create simple top toolbar using automatic navigation (no manual on_back)
            self.top_toolbar = SimpleTopToolbar(
                app=self.app,
                title="About Fichero",
                is_mobile=self.is_mobile
            )
            
            # Bottom toolbar (empty for now, but consistent structure)
            class AboutBottomToolbar(BottomToolbar):
                def _create_toolbar(self):
                    super()._create_toolbar()
                    # About-specific actions could go here
            
            self.bottom_toolbar = AboutBottomToolbar(self.app, is_mobile=self.is_mobile)
            
            # Set toolbars on the view
            self.set_top_toolbar(self.top_toolbar)
            self.set_bottom_toolbar(self.bottom_toolbar)
            
            logger.info("About mobile view toolbars created with automatic navigation")
            
        except Exception as e:
            logger.error(f"Failed to create about toolbars: {e}")
    
    def _create_content(self):
        """Create the about content"""
        try:
            # Create content using the shared about content
            content = self.about_content.create()
            
            # Add to the content container
            if self.content_container and content:
                self.content_container.add(content)
                logger.info("About content added to view")
            
        except Exception as e:
            logger.error(f"Failed to create about content: {e}")
    
    def _on_back_pressed(self):
        """Handle back button press"""
        logger.debug("About back button pressed")
        # Use the app's window view manager to go back
        if hasattr(self.app, 'window_view_manager') and hasattr(self.app.window_view_manager, 'mobile_view_manager'):
            self.app.window_view_manager.mobile_view_manager.go_back()
    
    def show(self):
        """Show method for compatibility"""
        logger.info("About mobile view shown")
    
    def hide(self):
        """Hide method for compatibility"""
        logger.info("About mobile view hidden") 