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
            from fichero.shared.toolbars import TopToolbar, BottomToolbar

            # Create top toolbar without coordinator (no edit mode for modal views)
            self.top_toolbar = TopToolbar(
                app=self.app,
                title="About",
                auto_mobile_nav=True,
                is_mobile=self.is_mobile
            )

            # Set up modal-specific back navigation
            self.top_toolbar.on_back = self._on_back_pressed

            # Create bottom toolbar without coordinator (no edit mode for modal views)
            self.bottom_toolbar = BottomToolbar(
                app=self.app,
                is_mobile=self.is_mobile
            )

            # About view doesn't need additional toolbar buttons

            # Set toolbars on the view
            self.set_top_toolbar(self.top_toolbar)
            self.set_bottom_toolbar(self.bottom_toolbar)

            logger.info("About mobile view toolbars created without edit mode")

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
    
    
    def _on_back_pressed(self, widget=None):
        """Handle back button press - close modal"""
        try:
            logger.info("About view back button pressed - closing modal")
            # Use the WindowViewManager to close the modal
            if hasattr(self.app, 'window_view_manager'):
                self.app.window_view_manager._close_modal_overlay()
            else:
                # Fallback: use NavigationController back navigation
                self.app.view_integration.navigation_controller.navigate_back()
        except Exception as e:
            logger.error(f"Failed to handle back navigation: {e}")

    def show(self):
        """Show method for compatibility"""
        logger.info("About mobile view shown")

    def hide(self):
        """Hide method for compatibility"""
        logger.info("About mobile view hidden") 