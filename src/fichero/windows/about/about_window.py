"""
About window for Fichero application - Desktop Window Implementation

This is the desktop window wrapper that uses the shared AboutContent component.
"""

import toga
from toga.style import Pack

# Use builtin _ function installed by translation.install()


class AboutWindow:
    """Desktop about window that uses the shared AboutContent component"""
    
    def __init__(self, app):
        """Initialize the about window"""
        self.app = app
        self.window = toga.Window(
            title=_("about_window_title") if _("about_window_title") != "about_window_title" else "About Fichero",
            size=(306, 470),
            resizable=False
        )
        
        # Import and create the shared about content
        from fichero.windows.about.about_content import AboutContent
        self.about_content = AboutContent(app)
        self.window.content = self.about_content.create()
        
        # Center the window
        self._center_window()
    
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
    
    def show(self):
        """Show the window"""
        self.window.show()
    
    def hide(self):
        """Hide the window"""  
        self.window.hide() 
    
    def close(self):
        """Close the window"""
        if self.window:
            self.window.close()
            self.window = None 