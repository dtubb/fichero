"""
Settings Mobile View

Mobile-specific view for settings that can be used in the main window.
"""

import logging
import toga
from toga.style import Pack
from toga.constants import COLUMN

from fichero.windows.settings.settings_content import SettingsContent
from fichero.shared.views.base_view import BaseView
from fichero.shared.toolbars import ToolbarCoordinator, TopToolbar, BottomToolbar

logger = logging.getLogger(__name__)


class SettingsMobileView(BaseView):
    """Mobile view for settings content that can be embedded in main window"""
    
    def __init__(self, app):
        """Initialize the mobile settings view"""
        # Create the settings content BEFORE calling super().__init__()
        # because BaseView.__init__ calls _create_content() which needs this
        self.settings_content = SettingsContent(app=app)
        
        # Initialize BaseView
        super().__init__(app, app.is_mobile)
        
        # Create toolbars
        self._create_toolbars()
        
        logger.info("SettingsMobileView initialized")
    
    def create(self):
        """Create the mobile settings view UI"""
        # Use BaseView's create which handles toolbar + content layout
        return self.get_container()
    
    def _create_content(self):
        """Create the settings content"""
        try:
            # Create content using the shared settings content
            content = self.settings_content.create()
            
            # Add to the content container
            if self.content_container and content:
                self.content_container.add(content)
                logger.info("Settings content added to view")
            
        except Exception as e:
            logger.error(f"Failed to create settings content: {e}")
    
    def _create_toolbars(self):
        """Create top and bottom toolbars for settings view"""
        try:
            from fichero.shared.toolbars import TopToolbar, BottomToolbar

            # Create top toolbar without coordinator (no edit mode for modal views)
            self.top_toolbar = TopToolbar(
                app=self.app,
                title="Settings",
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

            # Add settings-specific buttons using composition
            self._add_settings_toolbar_buttons()

            # Set toolbars on the view (mobile navigation will be connected automatically)
            self.set_top_toolbar(self.top_toolbar)
            self.set_bottom_toolbar(self.bottom_toolbar)

            logger.info("Settings toolbars created successfully")
        except Exception as e:
            logger.error(f"Failed to create settings toolbars: {e}")

    def _add_settings_toolbar_buttons(self):
        """Add settings-specific buttons using composition"""
        try:
            # Modal windows should have no toolbar buttons - only back button at top
            logger.debug("Settings modal view - no toolbar buttons added")

        except Exception as e:
            logger.error(f"Failed to add settings toolbar buttons: {e}")

    def _on_back_pressed(self, widget=None):
        """Handle back button press - close modal"""
        try:
            logger.info("Settings view back button pressed - closing modal")
            # Use the WindowViewManager to close the modal
            if hasattr(self.app, 'window_view_manager'):
                self.app.window_view_manager._close_modal_overlay()
            else:
                # Fallback: use NavigationController back navigation
                self.app.view_integration.navigation_controller.navigate_back()
        except Exception as e:
            logger.error(f"Failed to handle back navigation: {e}")

    def _on_save_settings(self, widget=None):
        """Handle save settings button press"""
        try:
            logger.info("Save settings button pressed")
            # TODO: Implement save settings functionality
            if hasattr(self.settings_content, 'save_settings'):
                self.settings_content.save_settings()

        except Exception as e:
            logger.error(f"Failed to save settings: {e}")

    def _on_reset_settings(self, widget=None):
        """Handle reset settings button press"""
        try:
            logger.info("Reset settings button pressed")
            # TODO: Implement reset settings functionality
            if hasattr(self.settings_content, 'reset_settings'):
                self.settings_content.reset_settings()

        except Exception as e:
            logger.error(f"Failed to reset settings: {e}")

    def show(self):
        """Show method for compatibility"""
        # Settings don't need special show logic like activity monitor
        logger.info("Settings mobile view shown")
    
    def hide(self):
        """Hide method for compatibility"""
        # Settings don't need special hide logic like activity monitor
        logger.info("Settings mobile view hidden")
    
    def save_settings(self):
        """Save current settings"""
        return self.settings_content.save_settings()
    
    def load_settings(self):
        """Load settings"""
        return self.settings_content.load_settings()
    
    def refresh(self):
        """Refresh the settings display"""
        self.settings_content.refresh() 