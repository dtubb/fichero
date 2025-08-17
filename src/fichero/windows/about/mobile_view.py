"""
About Mobile View

Mobile-specific view for the about screen that can be used in the main window.
"""

from fichero.windows.about.about_content import AboutContent


class AboutMobileView:
    """Mobile view for about content that can be embedded in main window"""
    
    def __init__(self, app):
        """Initialize the mobile about view"""
        self.app = app
        
        # Create the shared content (toolbar handles navigation)
        self.about_content = AboutContent(app=app)
    
    def create(self):
        """Create the mobile about view UI"""
        return self.about_content.create()
    
    def show(self):
        """Show method for compatibility"""
        pass
    
    def hide(self):
        """Hide method for compatibility"""
        pass 