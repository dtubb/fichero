"""
Plans Mobile View

Mobile-specific view for plans that can be used in the main window.
"""

import logging
from fichero.windows.plans.plans_content import PlansContent

logger = logging.getLogger(__name__)


class PlansMobileView:
    """Mobile view for plans content that can be embedded in main window"""
    
    def __init__(self, app):
        """Initialize the mobile plans view"""
        self.app = app
        
        # Create the shared content (toolbar handles navigation)
        self.plans_content = PlansContent(app=app)
        
        logger.info("PlansMobileView initialized")
    
    def create(self):
        """Create the mobile plans view UI"""
        return self.plans_content.create()
    
    def show(self):
        """Show method for compatibility"""
        # Plans don't need special show logic like activity monitor
        logger.info("Plans mobile view shown")
    
    def hide(self):
        """Hide method for compatibility"""
        # Plans don't need special hide logic like activity monitor
        logger.info("Plans mobile view hidden")
    
    def save_plans(self):
        """Save current plans"""
        return self.plans_content.save_plans()
    
    def load_plans(self):
        """Load plans"""
        return self.plans_content.load_plans()
    
    def refresh(self):
        """Refresh the plans display"""
        self.plans_content.refresh() 