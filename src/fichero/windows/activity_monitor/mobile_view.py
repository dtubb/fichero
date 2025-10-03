"""
Activity Monitor Mobile View

Mobile-specific view for the activity monitor that can be used in the main window.
Uses the standard base view pattern with consistent toolbars.
"""

import logging
from fichero.shared.views.base_view import BaseView
from fichero.windows.activity_monitor.activity_content import ActivityMonitorContent

logger = logging.getLogger(__name__)


class ActivityMonitorMobileView(BaseView):
    """Mobile view for activity monitor content that can be embedded in main window"""
    
    def __init__(self, app):
        """Initialize the mobile activity monitor view"""
        # Create the activity content BEFORE calling super().__init__()
                # because BaseView.__init__ calls _create_content() which needs this
        self.activity_content = ActivityMonitorContent(app=app)
        
        # Initialize BaseView first
        super().__init__(app, is_mobile=app.is_mobile)
        
        # Create toolbars after BaseView is initialized
        self._create_toolbars()
        
        logger.info("ActivityMonitorMobileView initialized")
    
    def create(self):
        """Create the activity monitor mobile view UI - return the full view container"""
        return self.get_container()
    
    def _create_toolbars(self):
        """Create top and bottom toolbars for activity monitor view"""
        try:
            from fichero.shared.toolbars import TopToolbar, BottomToolbar

            # Create top toolbar without coordinator (no edit mode for modal views)
            self.top_toolbar = TopToolbar(
                app=self.app,
                title="Activity Monitor",
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

            # Add activity-specific buttons using composition
            self._add_activity_toolbar_buttons()

            # Set toolbars on the view (mobile navigation will be connected automatically)
            self.set_top_toolbar(self.top_toolbar)
            self.set_bottom_toolbar(self.bottom_toolbar)

            logger.info("Activity monitor mobile view toolbars created successfully")
        except Exception as e:
            logger.error(f"Failed to create activity monitor toolbars: {e}")

    def _add_activity_toolbar_buttons(self):
        """Add activity-specific buttons using composition"""
        try:
            # Modal windows should have no toolbar buttons - only back button at top
            logger.debug("Activity monitor modal view - no toolbar buttons added")

        except Exception as e:
            logger.error(f"Failed to add activity toolbar buttons: {e}")

    def _on_pause_monitoring(self, widget):
        """Handle pause monitoring button"""
        try:
            logger.info("Pause monitoring requested")
            # Implementation would pause activity monitoring
        except Exception as e:
            logger.error(f"Failed to pause monitoring: {e}")

    def _on_clear_logs(self, widget=None):
        """Handle clear logs button press"""
        try:
            logger.info("Clear logs button pressed")
            # TODO: Implement clear logs functionality
            if hasattr(self.activity_content, 'clear_logs'):
                self.activity_content.clear_logs()

        except Exception as e:
            logger.error(f"Failed to clear logs: {e}")

    def _create_content(self):
        """Create the activity monitor content"""
        try:
            # Create content using the activity monitor content
            content = self.activity_content.create()
            
            # Add to the content container
            if self.content_container and content:
                self.content_container.add(content)
                logger.info("Activity monitor content added to view")
            
        except Exception as e:
            logger.error(f"Failed to create activity monitor content: {e}")
    
    
    def _on_back_pressed(self, widget=None):
        """Handle back button press - close modal"""
        try:
            logger.info("Activity monitor view back button pressed - closing modal")
            # Use the WindowViewManager to close the modal
            if hasattr(self.app, 'window_view_manager'):
                self.app.window_view_manager._close_modal_overlay()
            else:
                # Fallback: use NavigationController back navigation
                self.app.view_integration.navigation_controller.navigate_back()
        except Exception as e:
            logger.error(f"Failed to handle back navigation: {e}")

    def show(self):
        """Show method for compatibility - start monitoring"""
        self.activity_content.start_monitoring()
        logger.info("Activity monitor mobile view shown and monitoring started")

    def hide(self):
        """Hide method for compatibility - stop monitoring"""
        self.activity_content.stop_monitoring()
        logger.info("Activity monitor mobile view hidden and monitoring stopped")
    
    def start_monitoring(self):
        """Start monitoring tasks"""
        self.activity_content.start_monitoring()
    
    def stop_monitoring(self):
        """Stop monitoring tasks"""
        self.activity_content.stop_monitoring() 