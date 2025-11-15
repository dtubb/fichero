"""
Example View - Demonstrates Unified Command System

This is a complete working example showing how to use the unified command system.
Copy and adapt this pattern for your own views.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN
import logging
from fichero.shared.views.base_view import BaseView
from fichero.shared.commands import FicheroCommand, ViewCommandMixin
from fichero.shared.toolbars import TopToolbar, BottomToolbar

logger = logging.getLogger(__name__)


class ExampleView(BaseView, ViewCommandMixin):
    """
    Example view demonstrating the unified command system.

    This view shows:
    1. How to define commands using FicheroCommand
    2. How to register commands with the system
    3. How to auto-populate toolbars from commands
    4. Platform-adaptive behavior (desktop vs mobile)
    """

    def __init__(self, app, is_mobile=False):
        """Initialize the example view"""
        logger.info("Creating ExampleView")

        # STEP 1: Set view identifier (required for command system)
        self.view_id = "example"

        # STEP 2: Call parent constructors
        super().__init__(app, is_mobile)
        ViewCommandMixin.__init__(self)

        # STEP 3: Define commands
        self.define_commands()

        # STEP 4: Register commands with system
        # This automatically:
        # - Desktop: Adds to menus with shortcuts
        # - Both: Makes available for toolbars
        self.register_commands()

        # STEP 5: Setup toolbars
        self._setup_toolbars()

        # STEP 6: Create view content
        self._create_content()

        logger.info("ExampleView created successfully")

    def define_commands(self):
        """
        Define all commands for this view.

        Commands are defined once and work on both mobile and desktop.
        The system automatically routes them to appropriate UI elements.
        """
        self.commands = {
            # Edit commands with shortcuts
            'rotate_left': FicheroCommand(
                id=f'{self.view_id}.rotate_left',
                label='Rotate Left',
                action=self._rotate_left,
                shortcut=toga.Key.MOD_1 + 'l',  # Cmd+L on Mac, Ctrl+L elsewhere
                icon='resources/icons/rotate_left.png',
                toolbar_text='Rotate\nLeft',
                toolbar_position='center',
                show_in_menu=True,      # Desktop: appears in menu with shortcut
                show_in_toolbar=True,   # Both: appears in toolbar
                description='Rotate the image 90 degrees counter-clockwise'
            ),

            'rotate_right': FicheroCommand(
                id=f'{self.view_id}.rotate_right',
                label='Rotate Right',
                action=self._rotate_right,
                shortcut=toga.Key.MOD_1 + 'r',
                icon='resources/icons/rotate_right.png',
                toolbar_text='Rotate\nRight',
                toolbar_position='center',
                show_in_menu=True,
                show_in_toolbar=True,
                description='Rotate the image 90 degrees clockwise'
            ),

            'crop': FicheroCommand(
                id=f'{self.view_id}.crop',
                label='Crop',
                action=self._crop,
                shortcut=toga.Key.MOD_1 + 'k',
                icon='resources/icons/crop@10x.png',
                toolbar_text='Crop',
                toolbar_position='center',
                show_in_menu=True,
                show_in_toolbar=True,
                description='Crop the image to selection'
            ),

            # View commands
            'zoom_in': FicheroCommand(
                id=f'{self.view_id}.zoom_in',
                label='Zoom In',
                action=self._zoom_in,
                shortcut=toga.Key.MOD_1 + '+',
                icon='resources/icons/zoom_in.png',
                toolbar_text='Zoom\nIn',
                toolbar_position='right',
                show_in_menu=True,
                show_in_toolbar=True,
                group=toga.Group.VIEW,  # Places in View menu
                description='Increase zoom level'
            ),

            'zoom_out': FicheroCommand(
                id=f'{self.view_id}.zoom_out',
                label='Zoom Out',
                action=self._zoom_out,
                shortcut=toga.Key.MOD_1 + '-',
                icon='resources/icons/zoom_out.png',
                toolbar_text='Zoom\nOut',
                toolbar_position='right',
                show_in_menu=True,
                show_in_toolbar=True,
                group=toga.Group.VIEW,
                description='Decrease zoom level'
            ),

            # Mobile-only command (only appears on mobile)
            'share': FicheroCommand(
                id=f'{self.view_id}.share',
                label='Share',
                action=self._share,
                icon='resources/icons/share.png',
                toolbar_text='Share',
                toolbar_position='right',
                show_in_menu=False,
                show_in_toolbar=True,
                mobile_only=True,  # Only on mobile
                description='Share this image'
            ),

            # Desktop-only command (only appears on desktop)
            'export': FicheroCommand(
                id=f'{self.view_id}.export',
                label='Export...',
                action=self._export,
                shortcut=toga.Key.MOD_1 + 'e',
                icon='resources/icons/export.png',
                toolbar_text='Export',
                toolbar_position='right',
                show_in_menu=True,
                show_in_toolbar=True,
                desktop_only=True,  # Only on desktop
                description='Export image with options'
            )
        }

    def _setup_toolbars(self):
        """
        Setup toolbars with auto-population from commands.

        The toolbars automatically populate themselves with commands
        based on the view_id and context.
        """
        # Create top toolbar
        self.top_toolbar = TopToolbar(
            app=self.app,
            title="Example View",
            is_mobile=self.is_mobile
        )

        # Create bottom toolbar (mobile primarily)
        self.bottom_toolbar = BottomToolbar(
            app=self.app,
            is_mobile=self.is_mobile
        )

        # Auto-populate toolbars with commands
        # The 'normal' context shows regular commands
        # The 'edit' context would show edit-specific commands
        self.populate_toolbar_with_commands(self.top_toolbar, context="normal")

        # Set toolbars on view
        self.set_toolbars(self.top_toolbar, self.bottom_toolbar)

        logger.info("Toolbars setup complete")

    def _create_content(self):
        """Create the view content"""
        # Create a simple content area
        content_box = toga.Box(
            style=Pack(
                direction=COLUMN,
                flex=1,
                margin=20
            )
        )

        # Add title
        title = toga.Label(
            "Example View with Unified Commands",
            style=Pack(
                font_size=18,
                font_weight='bold',
                margin_bottom=10
            )
        )
        content_box.add(title)

        # Add description
        description = toga.Label(
            "This view demonstrates the unified command system.\n\n"
            "Commands defined in define_commands() automatically appear in:\n"
            "- Desktop: Native menus with keyboard shortcuts\n"
            "- Both: Custom toolbars\n\n"
            "Try the toolbar buttons or use keyboard shortcuts!",
            style=Pack(margin_bottom=20)
        )
        content_box.add(description)

        # Add status label
        self.status_label = toga.Label(
            "Ready",
            style=Pack(margin_top=20, font_size=14)
        )
        content_box.add(self.status_label)

        # Set content on view
        if hasattr(self, 'content_container'):
            self.content_container.add(content_box)

    # Command implementations
    # These are the actual actions that get executed when commands are triggered

    def _rotate_left(self, widget):
        """Rotate image left"""
        logger.info("🔄 Rotate Left command executed")
        self.status_label.text = "Rotated left 90°"
        # Implementation: rotate image counter-clockwise

    def _rotate_right(self, widget):
        """Rotate image right"""
        logger.info("🔄 Rotate Right command executed")
        self.status_label.text = "Rotated right 90°"
        # Implementation: rotate image clockwise

    def _crop(self, widget):
        """Crop image"""
        logger.info("✂️ Crop command executed")
        self.status_label.text = "Cropping image..."
        # Implementation: show crop interface

    def _zoom_in(self, widget):
        """Zoom in"""
        logger.info("🔍 Zoom In command executed")
        self.status_label.text = "Zoomed in"
        # Implementation: increase zoom level

    def _zoom_out(self, widget):
        """Zoom out"""
        logger.info("🔍 Zoom Out command executed")
        self.status_label.text = "Zoomed out"
        # Implementation: decrease zoom level

    def _share(self, widget):
        """Share (mobile only)"""
        logger.info("📤 Share command executed (mobile)")
        self.status_label.text = "Sharing..."
        # Implementation: show share sheet (iOS/Android)

    def _export(self, widget):
        """Export (desktop only)"""
        logger.info("💾 Export command executed (desktop)")
        self.status_label.text = "Exporting..."
        # Implementation: show export dialog (desktop)


# Example usage in your app:
"""
# In your main app or window:
from fichero.shared.commands.example_view import ExampleView

class MyApp(toga.App):
    def startup(self):
        # Create example view
        example_view = ExampleView(
            app=self,
            is_mobile=self.is_mobile
        )

        # Add to window
        self.main_window = toga.MainWindow(title="Command System Example")
        self.main_window.content = example_view.container
        self.main_window.show()
"""
