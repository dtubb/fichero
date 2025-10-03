"""
Plans Mobile View

Mobile-specific view for plans that can be used in the main window.
Uses the standard base view pattern with consistent toolbars.
"""

import logging
from fichero.shared.views.base_view import BaseView
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
            from fichero.shared.toolbars import TopToolbar, BottomToolbar

            # Create top toolbar without coordinator (no edit mode for modal views)
            self.top_toolbar = TopToolbar(
                app=self.app,
                title="Plans",
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

            # Add plans-specific buttons using composition
            self._add_plans_toolbar_buttons()

            # Set toolbars on the view (mobile navigation will be connected automatically)
            self.set_top_toolbar(self.top_toolbar)
            self.set_bottom_toolbar(self.bottom_toolbar)

            logger.info("Plans mobile view toolbars created successfully")
        except Exception as e:
            logger.error(f"Failed to create plans toolbars: {e}")
    
    def _add_plans_toolbar_buttons(self):
        """Add plans-specific buttons using composition"""
        try:
            # Modal windows should have no toolbar buttons - only back button at top
            logger.debug("Plans modal view - no toolbar buttons added")

            logger.debug("Plans toolbar buttons configured")

        except Exception as e:
            logger.error(f"Failed to add plans toolbar buttons: {e}")

    def _on_back_pressed(self, widget=None):
        """Handle back button press - close modal"""
        try:
            logger.info("Plans view back button pressed - closing modal")
            # Use the WindowViewManager to close the modal
            if hasattr(self.app, 'window_view_manager'):
                self.app.window_view_manager._close_modal_overlay()
            else:
                # Fallback: use NavigationController back navigation
                self.app.view_integration.navigation_controller.navigate_back()
        except Exception as e:
            logger.error(f"Failed to handle back navigation: {e}")

    def _on_new_plan(self, widget=None):
        """Handle new plan button press"""
        try:
            logger.info("New plan button pressed")
            # TODO: Implement new plan functionality
            if hasattr(self.plans_content, 'create_new_plan'):
                self.plans_content.create_new_plan()

        except Exception as e:
            logger.error(f"Failed to create new plan: {e}")

    def _on_export_plan(self, widget=None):
        """Handle export plan button press"""
        try:
            logger.info("Export plan button pressed")
            # TODO: Implement export plan functionality
            if hasattr(self.plans_content, 'export_plan'):
                self.plans_content.export_plan()

        except Exception as e:
            logger.error(f"Failed to export plan: {e}")

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