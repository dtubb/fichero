"""
Mobile view for processing content that can be embedded in main window
"""

import toga
import logging
from fichero.shared.views.base_view import BaseView
from fichero.windows.processing.processing_content import ProcessingContent

logger = logging.getLogger(__name__)


class ProcessingMobileView(BaseView):
    """Mobile view for processing content that can be embedded in main window"""
    
    def __init__(self, app):
        """Initialize the mobile processing view"""
        # Create the processing content BEFORE calling super().__init__()
                # because BaseView.__init__ calls _create_content() which needs this
        self.processing_content = ProcessingContent(app=app)
        
        # Initialize BaseView first
        super().__init__(app, is_mobile=app.is_mobile)
        
        # Create toolbars after BaseView is initialized
        self._create_toolbars()
                
        logger.info("ProcessingMobileView initialized")
    
    def create(self):
        """Create the processing mobile view UI - return the full view container"""
        return self.get_container()
    
    def _create_toolbars(self):
        """Create top and bottom toolbars for processing view"""
        try:
            from fichero.shared.toolbars.simple_top_toolbar import SimpleTopToolbar
            from fichero.shared.toolbars.bottom_toolbar import BottomToolbar
            
            # Create simple top toolbar using automatic navigation (no manual on_back)
            self.top_toolbar = SimpleTopToolbar(
                app=self.app,
                title="Processing",
                is_mobile=self.is_mobile
            )
            
            # Bottom toolbar (empty for now, but consistent structure)
            class ProcessingBottomToolbar(BottomToolbar):
                def _create_toolbar(self):
                    super()._create_toolbar()
                    # Processing-specific actions could go here
            
            self.bottom_toolbar = ProcessingBottomToolbar(self.app, is_mobile=self.is_mobile)
            
            # Set toolbars in the view (mobile navigation will be connected automatically)
            self.set_top_toolbar(self.top_toolbar)
            self.set_bottom_toolbar(self.bottom_toolbar)
            
            logger.info("Processing mobile view toolbars created successfully")            
        except Exception as e:
            logger.error(f"Failed to create processing toolbars: {e}")
    
    def _create_content(self):
        """Create the processing content"""
        try:
            # Create content using the shared processing content
            content = self.processing_content.create()
            
            # Add to the content container
            if self.content_container and content:
                self.content_container.add(content)
                logger.info("Processing content added to view")
            
        except Exception as e:
            logger.error(f"Failed to create processing content: {e}")
    
    def show(self):
        """Show method for compatibility"""
        # Processing doesn't need special show logic like activity monitor
        logger.info("Processing mobile view shown")
    
    def hide(self):
        """Hide method for compatibility"""
        # Processing doesn't need special hide logic like activity monitor
        logger.info("Processing mobile view hidden")
    
    def _on_back_pressed(self):
        """Handle back button press"""
        logger.debug("Processing back button pressed")
        # Use the app's window view manager to go back
        if hasattr(self.app, 'window_view_manager') and hasattr(self.app.window_view_manager, 'mobile_view_manager'):
            self.app.window_view_manager.mobile_view_manager.go_back()
    
    def start_processing(self):
        """Start processing if available"""
        if hasattr(self.processing_content, 'start_processing'):
            self.processing_content.start_processing()
    
    def stop_processing(self):
        """Stop processing if available"""
        if hasattr(self.processing_content, 'stop_processing'):
            self.processing_content.stop_processing()
