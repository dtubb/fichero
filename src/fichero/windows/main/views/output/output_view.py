"""
OutputView - Refactored PHASE 4 Version

Displays processing outputs using modular manager system.
Reduced from 3,039 lines to ~300 lines by delegating to:
- StepManager: state and navigation
- LayoutManager: split view layouts
- OutputPane: reusable display components

This version is the PHASE 4 refactoring target.
"""

import logging
import asyncio
from typing import Optional, List
from pathlib import Path

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW

from fichero.shared.views.base_view import BaseView
from fichero.shared.commands.view_mixin import ViewCommandMixin
from fichero.shared.toolbars import ToolbarCoordinator, TopToolbar, BottomToolbar

# PHASE 4: New manager imports
from .step_manager import StepManager, StepState
from .layout_manager import LayoutManager, LayoutType
from .output_pane import OutputPane
from .step_browser import StepBrowser

# PHASE 2: Renderer system
from fichero.library.renderers.renderer_registry import RendererRegistry

# PHASE 3: Inspector components (for Phase 4 integration)
from fichero.shared.components.metadata_viewer import MetadataViewer
from fichero.shared.components.json_editor import JsonEditor

logger = logging.getLogger(__name__)


class OutputView(BaseView, ViewCommandMixin):
    """
    Refactored Output view using manager pattern (PHASE 4).

    Architecture:
        StepManager → manages navigation state
        LayoutManager → manages split view layouts
        OutputPane → reusable display components

    Responsibilities:
        - Command definition and registration
        - Toolbar setup and updates
        - Event handling and coordination
        - View lifecycle management
    """

    def __init__(self, app, is_mobile: bool = False, library_manager=None):
        """
        Initialize output view with manager pattern.

        Args:
            app: Application instance
            is_mobile: Whether running in mobile mode
            library_manager: LibraryManager instance
        """
        logger.info("🔧 OutputView.__init__ starting (PHASE 4 refactored)")

        # Store library manager
        self.library_manager = library_manager

        # PHASE 4: Initialize managers
        self.step_manager = StepManager(library_manager)

        # PHASE 2: Initialize renderer registry
        self.renderer_registry = RendererRegistry()

        # PHASE 4: Initialize layout manager
        self.layout_manager = LayoutManager(library_manager, self.renderer_registry)

        # PHASE 4: Initialize tools menu manager
        from .tools_menu_manager import ToolsMenuManager
        self.tools_menu_manager = ToolsMenuManager(self, self.renderer_registry)

        # PHASE 4: Initialize step browser (shows list of steps/tools)
        self.step_browser = StepBrowser(on_step_selected=self._on_step_browser_selected)

        # PHASE 3: Initialize inspector components (for Phase 4 integration)
        self.metadata_viewer = MetadataViewer()
        self.json_editor = JsonEditor()

        # Connect step manager events
        self.step_manager.on_state_changed = self._on_step_state_changed

        # UI components
        self.content_area = None
        self.inspector_panel = None  # PHASE 4: inspector sidebar
        self.inspector_visible = False  # Inspector visibility state

        # Create toolbar coordinator
        self.coordinator = ToolbarCoordinator(app, is_mobile=is_mobile)

        # Register coordinator with NavigationController
        try:
            if hasattr(app, 'view_integration') and hasattr(app.view_integration, 'navigation_controller'):
                app.view_integration.navigation_controller.register_toolbar_coordinator(self.coordinator)
                logger.debug("Registered toolbar coordinator with navigation controller")
        except Exception as e:
            logger.warning(f"Could not register toolbar coordinator: {e}")

        # Force top toolbar on desktop (like Preview.app's markup toolbar)
        self.force_bottom_toolbar_on_desktop = False
        self.toolbar_visible = True  # Track toolbar visibility for toggle
        logger.info(f"🔧 OutputView: force_bottom_toolbar_on_desktop = {self.force_bottom_toolbar_on_desktop}, is_mobile = {is_mobile}")

        # Set view_id for command registration (BEFORE super().__init__)
        self.view_id = 'output'

        # Call parent init
        super().__init__(app, is_mobile)

        # Initialize ViewCommandMixin
        ViewCommandMixin.__init__(self)

        # Define and register commands
        self.define_commands()
        self.register_commands()

        # Set up toolbars
        self._setup_toolbars()

        # Set up Tools menu
        self._setup_tools_menu()

        logger.info("✅ OutputView (PHASE 4) initialization complete")

    def define_commands(self):
        """Define all commands for OutputView"""
        from fichero.shared.commands import FicheroCommand
        import toga

        try:
            # Create custom menu groups
            go_group = toga.Group("Go", order=40)
            tools_group = toga.Group("Tools", order=50)

            self.commands = {
                # ===== VIEW MENU - Zoom Commands =====
                # Note: Section 10 creates a divider below pane visibility toggles (section 0)
                'zoom_in': FicheroCommand(
                    id=f'{self.view_id}.zoom_in',
                    label=_("Zoom In"),
                    action=self._on_zoom_in,
                    shortcut=toga.Key.MOD_1 + toga.Key.PLUS,
                    description=_("Zoom in on image"),
                    group=toga.Group.VIEW,
                    section=10,
                    order=0,
                    show_in_menu=True,
                    desktop_only=False,
                    context='normal'
                ),
                'zoom_out': FicheroCommand(
                    id=f'{self.view_id}.zoom_out',
                    label=_("Zoom Out"),
                    action=self._on_zoom_out,
                    shortcut=toga.Key.MOD_1 + toga.Key.MINUS,
                    description=_("Zoom out on image"),
                    group=toga.Group.VIEW,
                    section=10,
                    order=1,
                    show_in_menu=True,
                    desktop_only=False,
                    context='normal'
                ),
                'zoom_fit': FicheroCommand(
                    id=f'{self.view_id}.zoom_fit',
                    label=_("Zoom to Fit"),
                    action=self._on_zoom_fit,
                    shortcut=toga.Key.MOD_1 + '9',
                    description=_("Fit image to window"),
                    group=toga.Group.VIEW,
                    section=10,
                    order=2,
                    show_in_menu=True,
                    desktop_only=False,
                    context='normal'
                ),
                'actual_size': FicheroCommand(
                    id=f'{self.view_id}.actual_size',
                    label=_("Actual Size"),
                    action=self._on_zoom_100,
                    shortcut=toga.Key.MOD_1 + '0',
                    description=_("Zoom to 100%"),
                    group=toga.Group.VIEW,
                    section=10,
                    order=3,
                    show_in_menu=True,
                    desktop_only=False,
                    context='normal'
                ),
                'fit_width': FicheroCommand(
                    id=f'{self.view_id}.fit_width',
                    label=_("Fit to Width"),
                    action=self._on_fit_width,
                    shortcut=toga.Key.MOD_1 + toga.Key.SHIFT + '0',
                    description=_("Fit image to window width"),
                    group=toga.Group.VIEW,
                    section=10,
                    order=4,
                    show_in_menu=True,
                    desktop_only=False,
                    context='normal'
                ),
                'fit_height': FicheroCommand(
                    id=f'{self.view_id}.fit_height',
                    label=_("Fit to Height"),
                    action=self._on_fit_height,
                    shortcut=toga.Key.MOD_1 + toga.Key.SHIFT + '9',
                    description=_("Fit image to window height"),
                    group=toga.Group.VIEW,
                    section=10,
                    order=5,
                    show_in_menu=True,
                    desktop_only=False,
                    context='normal'
                ),
                'zoom_selection': FicheroCommand(
                    id=f'{self.view_id}.zoom_selection',
                    label=_("Zoom to Selection"),
                    action=self._on_zoom_selection,
                    shortcut=toga.Key.MOD_1 + toga.Key.SHIFT + '8',
                    description=_("Zoom to selected area"),
                    group=toga.Group.VIEW,
                    section=10,
                    order=6,
                    show_in_menu=True,
                    desktop_only=False,
                    context='normal'
                ),

                # ===== GO MENU - Navigation Commands =====
                'prev_step': FicheroCommand(
                    id=f'{self.view_id}.prev_step',
                    label=_("Previous Step"),
                    action=self._on_prev_step,
                    shortcut=toga.Key.MOD_1 + toga.Key.LEFT,
                    description=_("Navigate to previous processing step"),
                    group=go_group,
                    section=0,
                    order=0,
                    show_in_menu=True,
                    desktop_only=False,
                    context='normal'
                ),
                'next_step': FicheroCommand(
                    id=f'{self.view_id}.next_step',
                    label=_("Next Step"),
                    action=self._on_next_step,
                    shortcut=toga.Key.MOD_1 + toga.Key.RIGHT,
                    description=_("Navigate to next processing step"),
                    group=go_group,
                    section=0,
                    order=1,
                    show_in_menu=True,
                    desktop_only=False,
                    context='normal'
                ),
                'prev_file': FicheroCommand(
                    id=f'{self.view_id}.prev_file',
                    label=_("Previous File"),
                    action=self._on_prev_file,
                    shortcut=toga.Key.MOD_1 + toga.Key.UP,
                    description=_("Navigate to previous file"),
                    group=go_group,
                    section=1,
                    order=0,
                    show_in_menu=True,
                    desktop_only=False,
                    context='normal'
                ),
                'next_file': FicheroCommand(
                    id=f'{self.view_id}.next_file',
                    label=_("Next File"),
                    action=self._on_next_file,
                    shortcut=toga.Key.MOD_1 + toga.Key.DOWN,
                    description=_("Navigate to next file"),
                    group=go_group,
                    section=1,
                    order=1,
                    show_in_menu=True,
                    desktop_only=False,
                    context='normal'
                ),

                # ===== TOOLS MENU - Image Adjustment Commands =====
                # These are always-visible adjustment tools (rotate, crop, reset)
                # They appear in bottom toolbar at all times (context='normal')
                'rotate_left': FicheroCommand(
                    id=f'{self.view_id}.rotate_left',
                    label=_("Rotate Left"),
                    action=self._on_rotate_left,
                    shortcut=toga.Key.MOD_1 + 'l',
                    icon='resources/icons/toolbar/rotate.left@10x.png',
                    description=_("Rotate image 90° counter-clockwise"),
                    group=tools_group,
                    section=0,
                    order=0,
                    toolbar_text=_("Rotate\nLeft"),
                    toolbar_position='left',
                    show_in_menu=False,  # Don't show in macOS menu/toolbar
                    show_in_top_toolbar=True,  # Show in OutputView's top toolbar only
                    show_in_bottom_toolbar=False,
                    desktop_only=False,
                    context='normal'  # Always visible, not just in edit mode
                ),
                'rotate_right': FicheroCommand(
                    id=f'{self.view_id}.rotate_right',
                    label=_("Rotate Right"),
                    action=self._on_rotate_right,
                    shortcut=toga.Key.MOD_1 + 'r',
                    icon='resources/icons/toolbar/rotate.right@10x.png',
                    description=_("Rotate image 90° clockwise"),
                    group=tools_group,
                    section=0,
                    order=1,
                    toolbar_text=_("Rotate\nRight"),
                    toolbar_position='left',
                    show_in_menu=False,  # Don't show in macOS menu/toolbar
                    show_in_top_toolbar=True,
                    show_in_bottom_toolbar=False,
                    desktop_only=False,
                    context='normal'  # Always visible, not just in edit mode
                ),
                'crop': FicheroCommand(
                    id=f'{self.view_id}.crop',
                    label=_("Crop"),
                    action=self._on_crop,
                    shortcut=toga.Key.MOD_1 + 'k',
                    icon='resources/icons/toolbar/crop.png',
                    description=_("Crop image"),
                    group=tools_group,
                    section=0,
                    order=2,
                    toolbar_text=_("Crop"),
                    toolbar_position='left',
                    show_in_menu=False,  # Don't show in macOS menu/toolbar
                    show_in_top_toolbar=True,
                    show_in_bottom_toolbar=False,
                    desktop_only=False,
                    context='normal'  # Always visible, not just in edit mode
                ),
                'reset': FicheroCommand(
                    id=f'{self.view_id}.reset',
                    label=_("Reset to Original"),
                    action=self._on_reset,
                    shortcut=toga.Key.MOD_1 + toga.Key.SHIFT + 'r',
                    icon='resources/icons/toolbar/arrow.up.left.and.arrow.down.right@10x.png',
                    description=_("Reset image to original state"),
                    group=tools_group,
                    section=0,
                    order=3,
                    toolbar_text=_("Reset"),
                    toolbar_position='left',
                    show_in_menu=False,  # Don't show in macOS menu/toolbar
                    show_in_top_toolbar=True,
                    show_in_bottom_toolbar=False,
                    desktop_only=False,
                    context='normal'  # Always visible, not just in edit mode
                ),
                'flip_horizontal': FicheroCommand(
                    id=f'{self.view_id}.flip_horizontal',
                    label=_("Flip Horizontal"),
                    action=self._on_flip_horizontal,
                    shortcut=toga.Key.MOD_1 + 'h',
                    icon='resources/icons/toolbar/arrow.left.and.right@10x.png',
                    description=_("Flip image horizontally"),
                    group=tools_group,
                    section=0,
                    order=4,
                    toolbar_text=_("Flip\nH"),
                    toolbar_position='left',
                    show_in_menu=False,  # Don't show in macOS menu/toolbar
                    show_in_top_toolbar=True,
                    show_in_bottom_toolbar=False,
                    desktop_only=False,
                    context='normal'
                ),
                'flip_vertical': FicheroCommand(
                    id=f'{self.view_id}.flip_vertical',
                    label=_("Flip Vertical"),
                    action=self._on_flip_vertical,
                    shortcut=toga.Key.MOD_1 + 'v',
                    icon='resources/icons/toolbar/arrow.up.and.down@10x.png',
                    description=_("Flip image vertically"),
                    group=tools_group,
                    section=0,
                    order=5,
                    toolbar_text=_("Flip\nV"),
                    toolbar_position='left',
                    show_in_menu=False,  # Don't show in macOS menu/toolbar
                    show_in_top_toolbar=True,
                    show_in_bottom_toolbar=False,
                    desktop_only=False,
                    context='normal'
                ),
                'straighten': FicheroCommand(
                    id=f'{self.view_id}.straighten',
                    label=_("Straighten"),
                    action=self._on_straighten,
                    shortcut=toga.Key.MOD_1 + 's',
                    icon='resources/icons/toolbar/level@10x.png',
                    description=_("Straighten image (fine rotation adjustment)"),
                    group=tools_group,
                    section=0,
                    order=6,
                    toolbar_text=_("Straight\nen"),
                    toolbar_position='left',
                    show_in_menu=True,
                    show_in_top_toolbar=True,
                    show_in_bottom_toolbar=False,
                    desktop_only=False,
                    context='normal'
                ),

                # ===== MOBILE TOOLBAR - Inspector Button =====
                'show_inspector': FicheroCommand(
                    id=f'{self.view_id}.show_inspector',
                    label=_("Show Inspector"),
                    action=self._on_toggle_inspector,
                    icon='resources/icons/toolbar/info.circle@10x.png',
                    description=_("Show/hide inspector panel"),
                    toolbar_position='right',
                    order=99,
                    show_in_top_toolbar=True,
                    mobile_only=True,
                    context='normal'
                ),
            }
            logger.info(f"✅ Defined {len(self.commands)} commands for OutputView")

        except Exception as e:
            logger.error(f"Failed to define commands: {e}")
            self.commands = {}

    def _create_content(self):
        """Create output view content"""
        logger.info("Creating output view content (PHASE 4)")

        # Main content area - horizontal layout for step browser + output + inspector
        self.content_area = toga.Box(
            style=Pack(
                direction=ROW,
                flex=1,
                margin=10
            )
        )

        # Add step browser on the left (shows list of steps: Original, transcribe, etc.)
        # No margin/padding - extends to top and bottom edges
        step_browser_container = toga.Box(
            style=Pack(
                direction=COLUMN,
                width=150  # Fixed width 150px (matches library/collection pane width)
            )
        )
        step_browser_container.add(self.step_browser.as_box())
        self.content_area.add(step_browser_container)

        # Add layout manager's container (output panes) in the middle
        self.content_area.add(self.layout_manager.get_container())

        # Create inspector panel (hidden by default)
        self._build_inspector_panel()

        # Add to content container (from BaseView)
        self.content_container.add(self.content_area)

    def get_container(self):
        """Return the main container for this view"""
        return self.container

    def show(self):
        """Show callback - called when view becomes active"""
        try:
            self.is_visible = True

            # Tell the coordinator that this view is now active
            if hasattr(self, 'coordinator') and self.coordinator:
                self.coordinator.set_active_view('output')
                logger.debug("OutputView notified coordinator of activation")
        except Exception as e:
            logger.error(f"Failed to notify coordinator in show(): {e}")

    def _setup_toolbars(self):
        """Set up toolbars with navigation buttons using declarative command system"""
        # _() is available globally via gettext.install() in app.py

        # Create top toolbar with file counter
        self.top_toolbar = TopToolbar(
            self.app,
            title=_("No file loaded"),
            auto_mobile_nav=True,
            is_mobile=self.is_mobile,
            coordinator=self.coordinator
        )

        # Add Export button to top toolbar (right side) - using command if available
        if hasattr(self, 'commands') and 'export_output' in self.commands:
            self.export_btn = self.top_toolbar.add_regular_button(
                button_id="export_output",
                position="right",
                text=_("Export"),
                on_press=self.commands['export_output'].action,
                style_class="right_aligned"
            )
        else:
            # Fallback to handler
            self.export_btn = self.top_toolbar.add_regular_button(
                button_id="export_output",
                position="right",
                text=_("Export"),
                on_press=lambda widget: logger.info("Export pressed (no command)"),
                style_class="right_aligned"
            )

        # Add Edit button to top toolbar (right side, before Export)
        if hasattr(self, 'commands') and 'toggle_inspector' in self.commands:
            self.edit_btn = self.top_toolbar.add_regular_button(
                button_id="edit_output",
                position="right",
                text=_("Edit"),
                on_press=self.commands['toggle_inspector'].action,
                style_class="right_aligned"
            )
        else:
            # Fallback to toggle_inspector method
            self.edit_btn = self.top_toolbar.add_regular_button(
                button_id="edit_output",
                position="right",
                text=_("Edit"),
                on_press=lambda widget: self._toggle_inspector(),
                style_class="right_aligned"
            )

        # Create bottom toolbar with three sections: file nav | step selector | step nav
        self.bottom_toolbar = BottomToolbar(
            self.app,
            is_mobile=self.is_mobile,
            coordinator=self.coordinator
        )

        # LEFT SECTION: File navigation buttons (up/down chevrons)
        # Use declarative commands for navigation
        self.bottom_prev_file_btn = self.bottom_toolbar.add_normal_mode_button(
            icon="resources/icons/toolbar/chevron.up@10x.png",
            on_press=lambda widget: asyncio.create_task(self._trigger_command('prev_file', widget)),
            position="left",
            label=_("Prev\nFile")
        )

        self.bottom_next_file_btn = self.bottom_toolbar.add_normal_mode_button(
            icon="resources/icons/toolbar/chevron.down@10x.png",
            on_press=lambda widget: asyncio.create_task(self._trigger_command('next_file', widget)),
            position="left",
            label=_("Next\nFile")
        )

        # CENTER SECTION: Empty (removed step selector - not needed)
        # Step selector was here but removed per user request
        self.step_selector = None  # Removed - no longer used

        # RIGHT SECTION: Step navigation buttons (left/right chevrons)
        self.prev_step_btn = self.bottom_toolbar.add_normal_mode_button(
            icon="resources/icons/toolbar/chevron.left@10x.png",
            on_press=lambda widget: self._trigger_command('prev_step', widget),
            position="right",
            label=_("Prev\nStep")
        )

        self.next_step_btn = self.bottom_toolbar.add_normal_mode_button(
            icon="resources/icons/toolbar/chevron.forward@10x.png",
            on_press=lambda widget: self._trigger_command('next_step', widget),
            position="right",
            label=_("Next\nStep")
        )

        # ADJUSTMENT TOOLS: Auto-populated from command definitions
        # Commands with context='normal' and show_in_bottom_toolbar=True will be added automatically
        # These are always-visible tools (not hidden in "edit mode")
        # See define_commands() for: rotate_left, rotate_right, crop, reset
        logger.debug("Adjustment tool buttons will be auto-populated from command definitions")

        # Toolbars auto-register with coordinator via constructor (coordinator=self.coordinator)

        # Register toolbars with BaseView (this adds them to the container)
        self.set_toolbars(
            top_toolbar=self.top_toolbar,
            bottom_toolbar=self.bottom_toolbar
        )

        # Initial button states (disabled until content is loaded)
        self._update_toolbar_state()

        logger.info("✅ Toolbars set up with navigation controls")

    def _setup_tools_menu(self):
        """Set up the Tools menu with Adjust, Go To, and Process submenus"""
        logger.info("Setting up Tools menu")

        try:
            # Build the menu using the tools menu manager
            tools_menu = self.tools_menu_manager.build_menu()

            # Register the menu with the app
            # Note: In Toga, menus are typically added to the app's main_window
            # We need to check if the app has a menubar we can add to
            if hasattr(self.app, 'main_window') and hasattr(self.app.main_window, '_impl'):
                # The actual menu registration depends on the platform
                # For now, we'll just log that it's ready
                logger.info("Tools menu built and ready")
                # TODO: Actual menu registration may need to happen at app level
                # The tools_menu is stored in self.tools_menu_manager.tools_menu
            else:
                logger.warning("Cannot register Tools menu - no main_window available")

        except Exception as e:
            logger.error(f"Error setting up Tools menu: {e}", exc_info=True)

    def _trigger_command(self, command_id: str, widget):
        """Trigger a command from the declarative command registry"""
        if hasattr(self, 'commands') and command_id in self.commands:
            command = self.commands[command_id]
            if command.action:
                # Call the command's action
                result = command.action(widget)
                # Handle async commands
                if asyncio.iscoroutine(result):
                    return result
        else:
            logger.warning(f"Command '{command_id}' not found in registry")

    # ==================== PUBLIC API ====================

    def load_output(self, item_id: str = None, source_item_ids: List[str] = None,
                    file_index: int = 0, step_index: int = 0,
                    # Backward compatibility with old parameter names
                    file_path=None, source_files=None, source_index: int = None):
        """
        Load output for display (PHASE 4 refactored).

        Args:
            item_id: Single library item ID to load
            source_item_ids: List of item IDs for multi-file navigation
            file_index: Which file to display initially
            step_index: Which step to display initially
            file_path: (Deprecated) Old parameter - ignored, use item_id instead
            source_files: (Deprecated) Old parameter - ignored, use source_item_ids instead
            source_index: (Deprecated) Old parameter - mapped to file_index
        """
        # Map old parameter names to new ones for backward compatibility
        if source_index is not None:
            file_index = source_index

        logger.info(f"Loading output: item_id={item_id}, file_index={file_index}, step_index={step_index}")

        # Run async loading in background task
        asyncio.create_task(self._load_output_async(item_id, source_item_ids, file_index, step_index))

    async def _load_output_async(self, item_id: str, source_item_ids: List[str],
                                 file_index: int, step_index: int):
        """Internal async method to load output"""
        try:
            # Load via step manager
            if source_item_ids:
                # Multi-file navigation
                await self.step_manager.load_item_list(source_item_ids, initial_index=file_index)
            elif item_id:
                # Single file
                await self.step_manager.load_item(item_id)
            else:
                logger.warning("No item_id or source_item_ids provided")
                return

            # Populate step browser with loaded steps
            if self.step_manager.steps:
                logger.info(f"Populating step browser with {len(self.step_manager.steps)} steps")
                # load_steps() will trigger _on_step_browser_selected() which handles:
                # - set_current_step() -> emits state change
                # - State change callback loads pane and updates UI
                self.step_browser.load_steps(self.step_manager.steps, current_index=step_index)
            else:
                # No steps found - clear the step browser
                logger.warning("No processing steps found - clearing step browser")
                self.step_browser.clear()

        except Exception as e:
            logger.error(f"Error loading output: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def set_layout(self, layout_type: LayoutType):
        """
        Switch to a different layout.

        Args:
            layout_type: Layout type to switch to
        """
        self.layout_manager.set_layout(layout_type)

    # ==================== EVENT HANDLERS ====================

    def _on_step_state_changed(self, state: StepState):
        """
        Handle step state change from StepManager.

        Called automatically when navigation changes.
        Updates UI to reflect new state.
        """
        logger.debug(f"Step state changed: step {state.step_index}/{state.total_steps}, "
                    f"file {state.file_index}/{state.total_files}")

        # Update UI
        self._update_ui_from_state()

        # Reload current step in pane
        if state.item_id and state.step_index >= 0:
            pane = self.layout_manager.get_primary_pane()
            if pane:
                current_step = self.step_manager.get_step(state.step_index)
                asyncio.create_task(pane.set_step(state.item_id, state.step_index, step=current_step))

        # Update inspector if visible (PHASE 4)
        if self.inspector_visible:
            self._update_inspector()

    def _update_ui_from_state(self):
        """Update UI elements based on current StepState"""
        state = self.step_manager.get_state()

        # Update toolbar state
        self._update_toolbar_state()

        # Update Tools menu state
        if hasattr(self, 'tools_menu_manager'):
            self.tools_menu_manager.update_menu_states()

        # Update step selector dropdown
        self._update_step_selector()

    def _update_toolbar_state(self):
        """Update toolbar button states and labels based on current StepState"""
        # _() is available globally via gettext.install() in app.py

        state = self.step_manager.get_state()

        # Update top toolbar title with file counter
        if state.total_files > 0:
            file_title = _("File {}/{}").format(state.file_index + 1, state.total_files)
        elif state.item_id:
            file_title = _("File 1/1")
        else:
            file_title = _("No file loaded")

        # Update toolbar title (directly update title_label like the old code does)
        if hasattr(self, 'top_toolbar') and self.top_toolbar:
            if hasattr(self.top_toolbar, 'title_label') and self.top_toolbar.title_label:
                self.top_toolbar.title_label.text = file_title

        # Enable/disable navigation buttons based on state
        if hasattr(self, 'prev_step_btn'):
            self.prev_step_btn.enabled = state.can_go_prev_step
        if hasattr(self, 'next_step_btn'):
            self.next_step_btn.enabled = state.can_go_next_step
        if hasattr(self, 'bottom_prev_file_btn'):
            self.bottom_prev_file_btn.enabled = state.can_go_prev_file
        if hasattr(self, 'bottom_next_file_btn'):
            self.bottom_next_file_btn.enabled = state.can_go_next_file

        # Enable/disable export/edit buttons
        has_content = state.item_id is not None and state.total_steps > 0
        if hasattr(self, 'export_btn'):
            self.export_btn.enabled = has_content
        if hasattr(self, 'edit_btn'):
            self.edit_btn.enabled = has_content

    def _update_step_selector(self):
        """Update step selector dropdown with current steps"""
        # _() is available globally via gettext.install() in app.py

        # Step selector was removed from bottom toolbar - skip update
        if not hasattr(self, 'step_selector') or self.step_selector is None:
            return

        # Get steps from manager
        steps = self.step_manager.steps

        if not steps:
            self.step_selector.items = [_("No steps loaded")]
            self.step_selector.enabled = False
            return

        # Build step list with format: "1. Crop Image", "2. Enhance", etc.
        step_items = []
        for i, step in enumerate(steps):
            step_items.append(f"{i + 1}. {step.step_name}")

        self.step_selector.items = step_items
        self.step_selector.enabled = True

        # Set current selection
        current_index = self.step_manager.current_step_index
        if 0 <= current_index < len(step_items):
            self.step_selector.value = step_items[current_index]

    def _on_step_selected(self, widget):
        """Handle step selector dropdown change"""
        if not hasattr(self, 'step_selector') or not self.step_selector.value:
            return

        # Parse step index from selection (format: "1. Step Name")
        try:
            selection = self.step_selector.value
            step_index = int(selection.split('.')[0]) - 1  # Convert to 0-based index

            # Update step manager
            self.step_manager.set_current_step(step_index)
            # State change event will trigger UI update

        except (ValueError, IndexError) as e:
            logger.error(f"Failed to parse step selection: {e}")

    # ==================== NAVIGATION HANDLERS ====================

    def _on_prev_step(self, widget):
        """Navigate to previous step"""
        if self.step_manager.prev_step():
            logger.debug("Navigated to previous step")
            # State change event will trigger UI update

    def _on_next_step(self, widget):
        """Navigate to next step"""
        if self.step_manager.next_step():
            logger.debug("Navigated to next step")
            # State change event will trigger UI update

    async def _on_prev_file(self, widget):
        """Navigate to previous file"""
        if await self.step_manager.prev_file():
            logger.debug("Navigated to previous file")
            # State change event will trigger UI update

    async def _on_next_file(self, widget):
        """Navigate to next file"""
        if await self.step_manager.next_file():
            logger.debug("Navigated to next file")
            # State change event will trigger UI update

    def _on_step_browser_selected(self, step_index: int):
        """
        Handle step selection from step browser.

        Args:
            step_index: Index of selected step
        """
        logger.info(f"Step browser: Step {step_index} selected")

        # Update step manager to the selected step
        # This will trigger _on_step_state_changed() which handles UI updates and pane loading
        self.step_manager.set_current_step(step_index)

    # ==================== ZOOM HANDLERS ====================

    def _on_zoom_in(self, widget):
        """Zoom in on current pane"""
        pane = self.layout_manager.get_primary_pane()
        if pane:
            pane.zoom_in()

    def _on_zoom_out(self, widget):
        """Zoom out on current pane"""
        pane = self.layout_manager.get_primary_pane()
        if pane:
            pane.zoom_out()

    def _on_zoom_fit(self, widget):
        """Fit image to window"""
        pane = self.layout_manager.get_primary_pane()
        if pane:
            pane.zoom_fit()

    def _on_zoom_100(self, widget):
        """Reset zoom to 100%"""
        pane = self.layout_manager.get_primary_pane()
        if pane:
            pane.zoom_100()

    def _on_fit_width(self, widget):
        """Fit image to window width"""
        pane = self.layout_manager.get_primary_pane()
        if pane:
            pane.zoom_fit_width()

    def _on_fit_height(self, widget):
        """Fit image to window height"""
        pane = self.layout_manager.get_primary_pane()
        if pane:
            pane.zoom_fit_height()

    def _on_zoom_selection(self, widget):
        """Zoom to selected area (Shift+drag in viewer)"""
        # Selection is handled automatically in JavaScript with Shift+drag
        # This command just shows a message to the user
        logger.info("Zoom to selection: Hold Shift and drag to select an area to zoom to")

    # ==================== ROTATION/EDIT HANDLERS ====================

    def _on_rotate_left(self, widget):
        """Rotate image 90° counter-clockwise"""
        pane = self.layout_manager.get_primary_pane()
        if pane:
            pane.rotate_left()

    def _on_rotate_right(self, widget):
        """Rotate image 90° clockwise"""
        pane = self.layout_manager.get_primary_pane()
        if pane:
            pane.rotate_right()

    def _on_crop(self, widget):
        """Activate crop tool"""
        pane = self.layout_manager.get_primary_pane()
        if pane:
            pane.activate_crop()

    def _on_reset(self, widget):
        """Reset image to original state (undo all edits)"""
        pane = self.layout_manager.get_primary_pane()
        if pane:
            # Reset rotation and zoom
            pane.reset_rotation()
            pane.zoom_100()

    def _on_flip_horizontal(self, widget):
        """Flip image horizontally"""
        pane = self.layout_manager.get_primary_pane()
        if pane:
            pane.flip_horizontal()

    def _on_flip_vertical(self, widget):
        """Flip image vertically"""
        pane = self.layout_manager.get_primary_pane()
        if pane:
            pane.flip_vertical()

    def _on_straighten(self, widget):
        """Activate straighten tool (fine rotation adjustment)"""
        pane = self.layout_manager.get_primary_pane()
        if pane:
            pane.activate_straighten()

    def _on_toggle_inspector(self, widget):
        """Toggle inspector panel visibility (command handler)"""
        self._toggle_inspector()

    # ==================== INSPECTOR INTEGRATION (PHASE 4) ====================

    def _build_inspector_panel(self):
        """Build the inspector sidebar panel (PHASE 4)"""
        # Create inspector container (right sidebar)
        self.inspector_panel = toga.Box(
            style=Pack(
                direction=COLUMN,
                width=350,  # Fixed width for inspector
                margin_left=10
            )
        )

        # Create ScrollContainer for inspector content
        inspector_scroll = toga.ScrollContainer(
            style=Pack(flex=1)
        )

        # Create vertical box to hold Phase 3 components
        inspector_content = toga.Box(
            style=Pack(direction=COLUMN, margin=5)
        )

        # Add Phase 3 MetadataViewer
        inspector_content.add(self.metadata_viewer.as_box())

        # Add separator
        separator = toga.Box(style=Pack(height=2, background_color='#CCCCCC', margin=(10, 0)))
        inspector_content.add(separator)

        # Add Phase 3 JsonEditor with callbacks
        self.json_editor.on_save = self._on_inspector_save
        self.json_editor.on_cancel = self._on_inspector_cancel
        inspector_content.add(self.json_editor.as_box())

        # Add content to scroll container
        inspector_scroll.content = inspector_content

        # Add scroll container to inspector panel
        self.inspector_panel.add(inspector_scroll)

        # Inspector starts hidden
        # (will be added to content_area when shown)

    async def _show_inspector_async(self):
        """Show inspector panel with current step metadata and editable JSON from renderer (async)"""
        if self.inspector_visible:
            return  # Already visible

        try:
            # Get current state from step manager (synchronously)
            state = self.step_manager.get_state()
            if not state or not state.item_id:
                logger.warning("No current step to display in inspector")
                return

            # Get current pane from layout manager
            pane = self.layout_manager.get_primary_pane()
            if not pane:
                logger.warning("No output pane available")
                return

            # Build metadata from current state
            metadata = {
                'Item ID': state.item_id,
                'Step': f"{state.step_index + 1} / {state.total_steps}",
                'File': f"{state.file_index + 1} / {state.total_files}",
            }

            # Get step info from current processing steps
            if hasattr(pane, 'current_item_id') and hasattr(pane, 'current_step_index'):
                # Get output data asynchronously
                output_data = await self.library_manager.get_item_output_data(pane.current_item_id)
                step_info = None

                if output_data and output_data.get('processing_steps'):
                    processing_steps = output_data['processing_steps']
                    # Adjust for 0-indexed (step 0 is original, processing starts at 1)
                    processing_step_index = pane.current_step_index - 1
                    if 0 <= processing_step_index < len(processing_steps):
                        step_info = processing_steps[processing_step_index]

                if step_info:
                    # Add step-specific metadata
                    metadata['Step Name'] = step_info.step_name if hasattr(step_info, 'step_name') else 'Unknown'
                    metadata['Tool'] = step_info.tool_name if hasattr(step_info, 'tool_name') else 'Unknown'
                    metadata['File Path'] = str(step_info.file_path) if hasattr(step_info, 'file_path') else 'N/A'
                    metadata['File Type'] = step_info.file_type if hasattr(step_info, 'file_type') else 'Unknown'

                    # Get renderer for this step
                    from fichero.library.renderers.renderer_registry import RendererRegistry
                    from fichero.library.renderers.base_renderer import RenderContext
                    from pathlib import Path

                    tool_name = step_info.tool_name if hasattr(step_info, 'tool_name') else 'unknown'
                    file_type = step_info.file_type if hasattr(step_info, 'file_type') else 'unknown'
                    file_path = Path(step_info.file_path) if hasattr(step_info, 'file_path') and step_info.file_path else Path('/')

                    renderer = RendererRegistry.get_renderer_for_step(
                        tool_name=tool_name,
                        file_type=file_type,
                        file_path=file_path
                    )

                    logger.info(f"Using renderer {renderer.__class__.__name__} for inspector JSON")

                    # Load manifest from file system
                    manifest_entry = None

                    # Build path to manifest file
                    # Pattern: {file_path parent}/assets/{tool_name}d/{tool_name}_manifest.jsonl
                    # Example: .../EAP1740_NP_T19_1700_001_01.tif/assets/cropped/crop_manifest.jsonl
                    try:
                        import json
                        from pathlib import Path

                        logger.info(f"Loading manifest for tool '{tool_name}' from file_path: {file_path}")

                        # Get the item output directory
                        # file_path is like: .../item.tif/assets/cropped/file.jpg
                        # We need to go up to .../item.tif/ and then into assets/{tool_name}d/
                        file_parent = file_path.parent  # .../item.tif/assets/cropped/
                        item_dir = file_parent.parent.parent  # .../item.tif/

                        # Build manifest path: {item_dir}/assets/{tool_name}d/{tool_name}_manifest.jsonl
                        manifest_dir_name = f"{tool_name}ped" if tool_name == "crop" else f"{tool_name}d"
                        manifest_file = item_dir / "assets" / manifest_dir_name / f"{tool_name}_manifest.jsonl"

                        logger.info(f"Looking for manifest at: {manifest_file}")

                        if manifest_file.exists():
                            # Read JSONL file (one JSON object per line)
                            with open(manifest_file, 'r') as f:
                                # Read first line (should be the only line for simple tools)
                                line = f.readline().strip()
                                if line:
                                    manifest_entry = json.loads(line)
                                    logger.info(f"✅ Loaded manifest from file: {manifest_file}")
                                    logger.info(f"Manifest entry keys: {list(manifest_entry.keys())}")
                        else:
                            logger.warning(f"❌ Manifest file not found: {manifest_file}")
                    except Exception as e:
                        logger.error(f"❌ Error loading manifest file: {e}", exc_info=True)

                    logger.info(f"Manifest entry is: {'LOADED' if manifest_entry else 'None'}")

                    # Create render context
                    context = RenderContext(
                        item_id=pane.current_item_id,
                        step_index=pane.current_step_index,
                        step_name=step_info.step_name if hasattr(step_info, 'step_name') else 'Unknown',
                        tool_name=tool_name,
                        file_path=file_path,
                        file_type=file_type,
                        manifest_entry=manifest_entry,
                        show_metadata=True,
                        show_content=True,
                        interactive=True
                    )

                    # Get editable JSON from renderer
                    editable_json = renderer.get_editable_json(context)

                    if editable_json:
                        logger.info(f"Got editable JSON from renderer: {editable_json}")
                        self.json_editor.set_data(editable_json)

                        # Store context for later use in save
                        self._current_render_context = context
                        self._current_renderer = renderer
                    else:
                        logger.info(f"Renderer {renderer.__class__.__name__} returned no editable JSON")
                        self.json_editor.set_data({})
                        self._current_render_context = None
                        self._current_renderer = None
                else:
                    logger.warning("No step info available")
                    self.json_editor.set_data({})
                    self._current_render_context = None
                    self._current_renderer = None

            # Update metadata viewer
            self.metadata_viewer.set_metadata(metadata)

            # Add inspector panel to content area
            self.content_area.add(self.inspector_panel)
            self.inspector_visible = True

            logger.debug("Inspector panel shown with renderer JSON")

        except Exception as e:
            logger.error(f"Error showing inspector: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _show_inspector(self):
        """Show inspector panel (synchronous wrapper)"""
        # Schedule the async version using asyncio
        import asyncio
        asyncio.create_task(self._show_inspector_async())
        logger.info("Inspector show scheduled")

    def _hide_inspector(self):
        """Hide inspector panel (PHASE 4)"""
        if not self.inspector_visible:
            return  # Already hidden

        # Remove inspector panel from content area
        try:
            self.content_area.remove(self.inspector_panel)
            self.inspector_visible = False
            logger.debug("Inspector panel hidden")
        except Exception as e:
            logger.error(f"Error hiding inspector panel: {e}")

    def _toggle_inspector(self):
        """Toggle inspector panel visibility (PHASE 4)"""
        if self.inspector_visible:
            self._hide_inspector()
        else:
            self._show_inspector()

    def toggle_toolbar(self):
        """Toggle markup toolbar visibility"""
        if not hasattr(self, 'top_toolbar') or not self.top_toolbar:
            logger.warning("Cannot toggle toolbar: toolbar not created yet")
            return

        # Toggle visibility state
        self.toolbar_visible = not self.toolbar_visible

        if self.toolbar_visible:
            # Show toolbar
            self.top_toolbar.container.style.visibility = 'visible'
            self.top_toolbar.container.style.height = None  # Auto height
            logger.info("🔧 Markup toolbar shown")
        else:
            # Hide toolbar
            self.top_toolbar.container.style.visibility = 'hidden'
            self.top_toolbar.container.style.height = 0
            logger.info("🔧 Markup toolbar hidden")

        # Force refresh
        if hasattr(self.top_toolbar.container, 'refresh'):
            self.top_toolbar.container.refresh()

    def _update_inspector(self):
        """Update inspector with current step data (PHASE 4)"""
        if self.inspector_visible:
            # Re-fetch and update
            self._hide_inspector()
            self._show_inspector()

    def _on_inspector_save(self, updated_data: dict):
        """
        Handle inspector save event using renderer system.

        Called when user saves edited parameters in JsonEditor.
        Uses renderer.apply_json_edits() to validate and apply changes.

        Args:
            updated_data: Updated parameters from JsonEditor
        """
        logger.info(f"Inspector save requested with data: {updated_data}")

        # Check if we have a current renderer and context
        if not hasattr(self, '_current_renderer') or not self._current_renderer:
            logger.error("No renderer available for saving")
            # TODO: Show error feedback to user
            return

        if not hasattr(self, '_current_render_context') or not self._current_render_context:
            logger.error("No render context available for saving")
            # TODO: Show error feedback to user
            return

        try:
            # Validate JSON with renderer
            is_valid, error_message = self._current_renderer.validate_json(updated_data)

            if not is_valid:
                logger.error(f"JSON validation failed: {error_message}")
                # TODO: Show error feedback to user with error_message
                return

            logger.info("JSON validation passed")

            # Apply edits using renderer
            success, error_message = self._current_renderer.apply_json_edits(
                self._current_render_context,
                updated_data
            )

            if success:
                logger.info("Parameters applied successfully by renderer")
                # TODO: Show success feedback to user

                # Refresh the output pane to show updated result
                pane = self.layout_manager.get_primary_pane()
                if pane and hasattr(pane, 'refresh'):
                    pane.refresh()
                    logger.info("Output pane refreshed")
            else:
                logger.error(f"Failed to apply parameters: {error_message}")
                # TODO: Show error feedback to user with error_message

        except Exception as e:
            logger.error(f"Error in inspector save: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # TODO: Show error feedback to user

    def _on_inspector_cancel(self):
        """Handle inspector cancel event (PHASE 4)"""
        logger.debug("Inspector edit cancelled")
        # Just hide the inspector - data will be refreshed on next show
        self._hide_inspector()

    def _get_step_editor(self):
        """Get or create step editor instance"""
        if not hasattr(self.library_manager, 'step_editor'):
            from fichero.library.step_editor import StepEditor
            self.library_manager.step_editor = StepEditor(self.library_manager)
        return self.library_manager.step_editor
