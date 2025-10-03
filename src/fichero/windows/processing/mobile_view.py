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
            from fichero.shared.toolbars import TopToolbar, BottomToolbar

            # Create top toolbar without coordinator (no edit mode for modal views)
            self.top_toolbar = TopToolbar(
                app=self.app,
                title="Processing",
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

            # Add processing-specific buttons using composition
            self._add_processing_toolbar_buttons()

            # Set toolbars in the view (mobile navigation will be connected automatically)
            self.set_top_toolbar(self.top_toolbar)
            self.set_bottom_toolbar(self.bottom_toolbar)

            logger.info("Processing mobile view toolbars created successfully")
        except Exception as e:
            logger.error(f"Failed to create processing toolbars: {e}")
    
    def _add_processing_toolbar_buttons(self):
        """Add processing-specific buttons using composition"""
        try:
            # Modal windows should have no toolbar buttons - only back button at top
            logger.debug("Processing modal view - no toolbar buttons added")

            logger.debug("Processing toolbar buttons configured")

        except Exception as e:
            logger.error(f"Failed to add processing toolbar buttons: {e}")

    def _on_start_processing(self, widget=None):
        """Handle start processing button press"""
        try:
            logger.info("Start processing button pressed")
            # TODO: Implement start processing functionality
            if hasattr(self.processing_content, 'start_processing'):
                self.processing_content.start_processing()

        except Exception as e:
            logger.error(f"Failed to start processing: {e}")

    def _on_monitor_processing(self, widget=None):
        """Handle monitor processing button press"""
        try:
            logger.info("Monitor processing button pressed")
            # TODO: Implement processing monitoring functionality
            if hasattr(self.processing_content, 'monitor_processing'):
                self.processing_content.monitor_processing()

        except Exception as e:
            logger.error(f"Failed to monitor processing: {e}")

    def _on_back_pressed(self, widget=None):
        """Handle back button press - close modal"""
        try:
            logger.info("Processing view back button pressed - closing modal")
            # Use the WindowViewManager to close the modal
            if hasattr(self.app, 'window_view_manager'):
                self.app.window_view_manager._close_modal_overlay()
            else:
                # Fallback: use NavigationController back navigation
                self.app.view_integration.navigation_controller.navigate_back()
        except Exception as e:
            logger.error(f"Failed to handle back navigation: {e}")

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
    
    
    def start_processing(self):
        """Start processing if available"""
        if hasattr(self.processing_content, 'start_processing'):
            self.processing_content.start_processing()
    
    def stop_processing(self):
        """Stop processing if available"""
        if hasattr(self.processing_content, 'stop_processing'):
            self.processing_content.stop_processing()
