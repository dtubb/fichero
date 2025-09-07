"""
Plans Mobile View

Mobile-specific view for plans that can be used in the main window.
Uses the standard base view pattern with consistent toolbars.
"""

import logging
from fichero.windows.main.views.base_view import BaseView
from fichero.windows.plans.plans_content import PlansContent

logger = logging.getLogger(__name__)


class PlansMobileView(BaseView):
    """Mobile view for plans content that can be embedded in main window"""
    
    def __init__(self, app):
        """Initialize the mobile plans view"""
        # Create the plans content BEFORE calling super().__init__()
                # because BaseView.__init__ calls _create_content() which needs this
        self.plans_content = PlansContent(app=app)
        
        # Initialize BaseView first
        super().__init__(app, is_mobile=app.is_mobile)
        
        # Create toolbars after BaseView is initialized
        self._create_toolbars()
        
        logger.info("PlansMobileView initialized")
    
    def create(self):
        """Create the plans mobile view UI - return the full view container"""
        return self.get_container()
    
    def _create_toolbars(self):
        """Create top and bottom toolbars for plans view"""
        try:
            from fichero.shared.toolbars.simple_top_toolbar import SimpleTopToolbar
            from fichero.windows.main.toolbars.bottom_toolbar import BottomToolbar
            
            # Create simple top toolbar using the standardized class
            self.top_toolbar = SimpleTopToolbar(
                app=self.app,
                title="Plans",
                on_back=self._on_back_pressed,
                is_mobile=self.is_mobile
            )
            
            # Bottom toolbar (empty for now, but consistent structure)
            class PlansBottomToolbar(BottomToolbar):
                def _create_toolbar(self):
                    super()._create_toolbar()
                    # Plans-specific actions could go here
            
            self.bottom_toolbar = PlansBottomToolbar(self.app, is_mobile=self.is_mobile)
            
            # Set toolbars on the view
            self.set_top_toolbar(self.top_toolbar)
            self.set_bottom_toolbar(self.bottom_toolbar)
            
            logger.info("Plans mobile view toolbars created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create plans toolbars: {e}")
    
    def _create_content(self):
        """Create the plans content"""
        try:
            # Create content using the plans content
            content = self.plans_content.create()
            
            # Add to the content container
            if self.content_container and content:
                self.content_container.add(content)
                logger.info("Plans content added to view")
            
        except Exception as e:
            logger.error(f"Failed to create plans content: {e}")
    
    def _on_back_pressed(self):
        """Handle back button press"""
        logger.debug("Plans back button pressed")
        # Use the app's window view manager to go back
        if hasattr(self.app, 'window_view_manager') and hasattr(self.app.window_view_manager, 'mobile_view_manager'):
            self.app.window_view_manager.mobile_view_manager.go_back()
    
    def show(self):
        """Show method for compatibility"""
        logger.info("Plans mobile view shown")
    
    def hide(self):
        """Hide method for compatibility"""
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