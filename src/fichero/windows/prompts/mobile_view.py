"""
Prompts Mobile View

Mobile-specific view for prompts that can be used in the main window.
"""

import logging
from fichero.windows.prompts.prompts_content import PromptsContent

logger = logging.getLogger(__name__)


class PromptsMobileView:
    """Mobile view for prompts content that can be embedded in main window"""
    
    def __init__(self, app):
        """Initialize the mobile prompts view"""
        self.app = app
        
        # Create the shared content (toolbar handles navigation)
        self.prompts_content = PromptsContent(app=app)
        
        logger.info("PromptsMobileView initialized")
    
    def create(self):
        """Create the mobile prompts view UI"""
        return self.prompts_content.create()
    
    def show(self):
        """Show method for compatibility"""
        # Prompts don't need special show logic like activity monitor
        logger.info("Prompts mobile view shown")
    
    def hide(self):
        """Hide method for compatibility"""
        # Prompts don't need special hide logic like activity monitor
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