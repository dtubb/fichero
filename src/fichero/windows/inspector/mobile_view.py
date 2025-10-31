"""
Inspector Mobile View

Mobile-specific view for the inspector that can be used in the main window.
Uses the standard base view pattern with consistent toolbars.
"""

import logging
from fichero.shared.views.base_view import BaseView

logger = logging.getLogger(__name__)


class InspectorMobileView(BaseView):
    """Mobile view for inspector content that can be embedded in main window"""

    def __init__(self, app, item_data=None, selection_type='ITEM'):
        """Initialize the mobile inspector view

        Args:
            app: The Toga application instance
            item_data: Dictionary of item metadata to display
            selection_type: Type of selection ('ITEM', 'COLLECTION', 'FOLDER')
        """
        # Store metadata for later
        self.item_data = item_data or {}
        self.selection_type = selection_type

        # Get or create the inspector window instance (shared with desktop)
        self.inspector_window = getattr(app, 'inspector_window', None)
        if not self.inspector_window:
            from fichero.windows.inspector.inspector_window import InspectorWindow
            self.inspector_window = InspectorWindow(app)
            app.inspector_window = self.inspector_window

        # Update inspector with metadata
        if self.item_data:
            self.inspector_window.update_metadata(self.item_data, self.selection_type)

        # Initialize BaseView
        super().__init__(app, is_mobile=app.is_mobile)

        # Create toolbars after BaseView is initialized
        self._create_toolbars()

        logger.info("InspectorMobileView initialized")

    def create(self):
        """Create the inspector mobile view UI - return the full view container"""
        return self.get_container()

    def _create_toolbars(self):
        """Create top and bottom toolbars for inspector view"""
        try:
            from fichero.shared.toolbars import TopToolbar, BottomToolbar

            # Create top toolbar without coordinator (no edit mode for modal views)
            self.top_toolbar = TopToolbar(
                app=self.app,
                title="Inspector",
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

            # Set toolbars on the view (mobile navigation will be connected automatically)
            self.set_top_toolbar(self.top_toolbar)
            self.set_bottom_toolbar(self.bottom_toolbar)

            logger.info("Inspector mobile view toolbars created successfully")
        except Exception as e:
            logger.error(f"Failed to create inspector toolbars: {e}")

    def _create_content(self):
        """Create the inspector content - uses the real InspectorWindow content"""
        try:
            # Get the OptionContainer from the inspector window
            # This is the same content shown on desktop, just in a mobile modal
            content = self.inspector_window.create_content()

            # Add to the content container (same pattern as Settings)
            if self.content_container and content:
                self.content_container.add(content)
                logger.info("Inspector content added to view")

        except Exception as e:
            logger.error(f"Failed to create inspector content: {e}")
            import traceback
            traceback.print_exc()

    def _on_back_pressed(self, widget=None):
        """Handle back button press - navigate back using NavigationController"""
        try:
            logger.info("Inspector back button pressed")
            if hasattr(self.app, 'view_integration'):
                nav_controller = self.app.view_integration.get_navigation_controller()
                if nav_controller:
                    nav_controller.navigate_back()
        except Exception as e:
            logger.error(f"Failed to handle back navigation: {e}")
