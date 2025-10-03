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
            from fichero.shared.toolbars import TopToolbar, BottomToolbar

            # Create top toolbar without coordinator (no edit mode for modal views)
            self.top_toolbar = TopToolbar(
                app=self.app,
                title="Prompts",
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

            # Add prompts-specific buttons using composition
            self._add_prompts_toolbar_buttons()

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

    def _add_prompts_toolbar_buttons(self):
        """Add prompts-specific buttons using composition"""
        try:
            # Modal windows should have no toolbar buttons - only back button at top
            logger.debug("Prompts modal view - no toolbar buttons added")

            logger.debug("Prompts toolbar buttons configured")

        except Exception as e:
            logger.error(f"Failed to add prompts toolbar buttons: {e}")

    def _on_back_pressed(self, widget=None):
        """Handle back button press - close modal"""
        try:
            logger.info("Prompts view back button pressed - closing modal")
            # Use the WindowViewManager to close the modal
            if hasattr(self.app, 'window_view_manager'):
                self.app.window_view_manager._close_modal_overlay()
            else:
                # Fallback: use NavigationController back navigation
                self.app.view_integration.navigation_controller.navigate_back()
        except Exception as e:
            logger.error(f"Failed to handle back navigation: {e}")

    def _on_new_prompt(self, widget=None):
        """Handle new prompt button press"""
        try:
            logger.info("New prompt button pressed")
            # TODO: Implement new prompt functionality
            if hasattr(self.prompts_content, 'create_new_prompt'):
                self.prompts_content.create_new_prompt()

        except Exception as e:
            logger.error(f"Failed to create new prompt: {e}")

    def _on_export_prompts(self, widget=None):
        """Handle export prompts button press"""
        try:
            logger.info("Export prompts button pressed")
            # TODO: Implement export prompts functionality
            if hasattr(self.prompts_content, 'export_prompts'):
                self.prompts_content.export_prompts()

        except Exception as e:
            logger.error(f"Failed to export prompts: {e}")