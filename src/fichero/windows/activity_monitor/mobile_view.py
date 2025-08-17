"""
Activity Monitor Mobile View

Mobile-specific view for the activity monitor that can be used in the main window.
"""

from fichero.windows.activity_monitor.activity_content import ActivityMonitorContent


class ActivityMonitorMobileView:
    """Mobile view for activity monitor content that can be embedded in main window"""
    
    def __init__(self, app):
        """Initialize the mobile activity monitor view"""
        self.app = app
        
        # Create the shared content (toolbar handles navigation)
        self.activity_content = ActivityMonitorContent(app=app)
    
    def create(self):
        """Create the mobile activity monitor view UI"""
        return self.activity_content.create()
    
    def show(self):
        """Show method for compatibility - start monitoring"""
        self.activity_content.start_monitoring()
    
    def hide(self):
        """Hide method for compatibility - stop monitoring"""
        self.activity_content.stop_monitoring()
    
    def start_monitoring(self):
        """Start monitoring tasks"""
        self.activity_content.start_monitoring()
    
    def stop_monitoring(self):
        """Stop monitoring tasks"""
        self.activity_content.stop_monitoring() 