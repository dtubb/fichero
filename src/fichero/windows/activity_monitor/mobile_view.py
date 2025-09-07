"""
Activity Monitor Mobile View

Mobile-specific view for the activity monitor that can be used in the main window.
Uses the standard base view pattern with consistent toolbars.
"""

import logging
from fichero.windows.main.views.base_view import BaseView
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
            from fichero.shared.toolbars.simple_top_toolbar import SimpleTopToolbar
            from fichero.windows.main.toolbars.bottom_toolbar import BottomToolbar
            
            # Create simple top toolbar using the standardized class
            self.top_toolbar = SimpleTopToolbar(
                app=self.app,
                title="Activity Monitor",
                on_back=self._on_back_pressed,
                is_mobile=self.is_mobile
            )
            
            # Bottom toolbar (empty for now, but consistent structure)
            class ActivityBottomToolbar(BottomToolbar):
                def _create_toolbar(self):
                    super()._create_toolbar()
                    # Activity-specific actions could go here
            
            self.bottom_toolbar = ActivityBottomToolbar(self.app, is_mobile=self.is_mobile)
            
            # Set toolbars on the view
            self.set_top_toolbar(self.top_toolbar)
            self.set_bottom_toolbar(self.bottom_toolbar)
            
            logger.info("Activity monitor mobile view toolbars created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create activity monitor toolbars: {e}")
    
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
    
    def _on_back_pressed(self):
        """Handle back button press"""
        logger.debug("Activity monitor back button pressed")
        # Stop monitoring when going back
        self.stop_monitoring()
        # Use the app's window view manager to go back
        if hasattr(self.app, 'window_view_manager') and hasattr(self.app.window_view_manager, 'mobile_view_manager'):
            self.app.window_view_manager.mobile_view_manager.go_back()
    
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