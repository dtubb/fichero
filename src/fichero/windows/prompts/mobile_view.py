"""
Prompts Mobile View

Mobile-specific view for prompts that can be used in the main window.
Uses the standard base view pattern with consistent toolbars.
"""

import logging
from fichero.shared.views.base_view import BaseView
from fichero.windows.prompts.prompts_content import PromptsContent

logger = logging.getLogger(__name__)


class PromptsMobileView(BaseView):
    """Mobile view for prompts content that can be embedded in main window"""
    
    def __init__(self, app):
        """Initialize the mobile prompts view"""
        # Create the prompts content BEFORE calling super().__init__()
                # because BaseView.__init__ calls _create_content() which needs this
        self.prompts_content = PromptsContent(app=app)
        
        # Initialize BaseView first
        super().__init__(app, is_mobile=app.is_mobile)
        
        # Create toolbars after BaseView is initialized
        self._create_toolbars()
        
        logger.info("PromptsMobileView initialized")
    
    def create(self):
        """Create the prompts mobile view UI - return the full view container"""
        return self.get_container()
    
    def _create_toolbars(self):
        """Create top and bottom toolbars for prompts view"""
        try:
            from fichero.shared.toolbars.simple_top_toolbar import SimpleTopToolbar
            from fichero.shared.toolbars.bottom_toolbar import BottomToolbar
            
            # Create simple top toolbar using automatic navigation (no manual on_back)
            self.top_toolbar = SimpleTopToolbar(
                app=self.app,
                title="Prompts",
                is_mobile=self.is_mobile
            )
            
            # Bottom toolbar (empty for now, but consistent structure)
            class PromptsBottomToolbar(BottomToolbar):
                def _create_toolbar(self):
                    super()._create_toolbar()
                    # Prompts-specific actions could go here
            
            self.bottom_toolbar = PromptsBottomToolbar(self.app, is_mobile=self.is_mobile)
            
            # Set toolbars on the view (mobile navigation will be connected automatically)
            self.set_top_toolbar(self.top_toolbar)
            self.set_bottom_toolbar(self.bottom_toolbar)
            
            logger.info("Prompts mobile view toolbars created successfully")            
        except Exception as e:
            logger.error(f"Failed to create prompts toolbars: {e}")
    
    def _create_content(self):
        """Create the prompts content"""
        try:
            # Create content using the prompts content
            content = self.prompts_content.create()
            
            # Add to the content container
            if self.content_container and content:
                self.content_container.add(content)
                logger.info("Prompts content added to view")
            
        except Exception as e:
            logger.error(f"Failed to create prompts content: {e}")
    
    def _on_back_pressed(self):
        """Handle back button press"""
        logger.debug("Prompts back button pressed")
        # Use the app's window view manager to go back
        if hasattr(self.app, 'window_view_manager') and hasattr(self.app.window_view_manager, 'mobile_view_manager'):
            self.app.window_view_manager.mobile_view_manager.go_back()
    
    def show(self):
        """Show method for compatibility"""
        logger.info("Prompts mobile view shown")
    
    def hide(self):
        """Hide method for compatibility"""
        logger.info("Prompts mobile view hidden")
    
    def save_prompts(self):
        """Save current prompts"""
        return self.prompts_content.save_prompts()
    
    def load_prompts(self):
        """Load prompts"""
        return self.prompts_content.load_prompts()
    
    def refresh(self):
        """Refresh the prompts display"""
        self.prompts_content.refresh() 