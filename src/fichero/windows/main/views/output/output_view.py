"""
OutputView - Main Window Output View

Displays processing outputs with flexible dual-pane comparison and navigation.
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
from fichero.library.outputs_manager import ToolOutput  # For creating tool output objects

logger = logging.getLogger(__name__)


class OutputView(BaseView, ViewCommandMixin):
    """Output view for main window center pane"""

    def __init__(self, app, is_mobile: bool = False, library_manager=None):
        """Initialize output view

        Args:
            app: Application instance
            is_mobile: Whether running in mobile mode
            library_manager: LibraryManager instance for file-specific filtering
        """
        logger.info("🔧 OutputView.__init__ starting")

        # Library integration (PREFERRED: for item_id-based loading with file-specific filtering)
        self.current_item_id: Optional[str] = None
        self.library_manager = library_manager  # LibraryManager for file-specific filtering

        # Output state
        self.processing_steps: List[ToolOutput] = []
        self.current_step_index: int = 0
        self.current_file_index: int = 0
        self.current_file_path: Optional[Path] = None

        # Source file list (for file navigation across different input files)
        self.source_files: List[Path] = []  # LEGACY: Will be replaced by source_item_ids
        self.current_source_index: int = 0

        # Item ID list (PREFERRED: for library-based file navigation)
        self.source_item_ids: List[str] = []  # List of library item IDs for navigation

        # Dual pane state (desktop only)
        self.left_step_index: int = 0
        self.right_step_index: int = 0
        self.split_mode: bool = False  # Single view by default

        # Persistent viewer state (preserved across file/step changes)
        self.viewer_state = {
            'scale': 1.0,
            'rotation': 0,
            'scroll_x': 0,
            'scroll_y': 0
        }

        # UI components
        self.content_area = None
        self.left_pane = None
        self.right_pane = None

        # Create toolbar coordinator
        self.coordinator = ToolbarCoordinator(app, is_mobile=is_mobile)

        # Register coordinator with NavigationController
        try:
            if hasattr(app, 'view_integration') and hasattr(app.view_integration, 'navigation_controller'):
                app.view_integration.navigation_controller.register_toolbar_coordinator(self.coordinator)
                logger.debug("Registered toolbar coordinator with navigation controller")
        except Exception as e:
            logger.warning(f"Could not register toolbar coordinator with navigation controller: {e}")

        # Call parent init FIRST (sets self.app and self.is_mobile)
        super().__init__(app, is_mobile)

        # Set view_id for command registration
        self.view_id = 'output'

        # Initialize ViewCommandMixin
        ViewCommandMixin.__init__(self)

        # Force bottom toolbar on desktop for navigation controls (file/step navigation, plan/step selectors)
        self.force_bottom_toolbar_on_desktop = True

        # Define and register commands using ViewCommandMixin pattern
        self.define_commands()
        self.register_commands()

        # Set up toolbars with custom buttons
        # Commands are now available in registry for _create_edit_mode_buttons()
        self._setup_toolbars()

        logger.info("✅ OutputView initialization complete")

    def define_commands(self):
        """Define all commands for OutputView using ViewCommandMixin pattern"""
        from fichero.shared.commands import FicheroCommand
        import toga

        try:
            # Create custom menu groups
            go_group = toga.Group("Go", order=40)  # After View (30), before Tools
            tools_group = toga.Group("Tools", order=50)  # After Go (40), before Window (90)

            self.commands = {
                # ===== TOOLS MENU - Image Edit Commands =====
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
                    show_in_menu=True,
                    show_in_bottom_toolbar=True,  # Show in edit mode toolbar
                    desktop_only=False,
                    context='edit'  # Only show in edit mode
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
                    show_in_menu=True,
                    show_in_bottom_toolbar=True,  # Show in edit mode toolbar
                    desktop_only=False,
                    context='edit'  # Only show in edit mode
                ),
                'crop': FicheroCommand(
                    id=f'{self.view_id}.crop',
                    label=_("Crop Image"),
                    action=self._on_crop,
                    shortcut=toga.Key.MOD_1 + 'k',
                    icon='resources/icons/chatgpt_icons/crop.png',
                    description=_("Crop image to selection"),
                    group=tools_group,
                    section=0,
                    order=2,
                    toolbar_text=_("Crop"),
                    toolbar_position='left',
                    show_in_menu=True,
                    show_in_bottom_toolbar=True,  # Show in edit mode toolbar
                    desktop_only=False,
                    context='edit'  # Only show in edit mode
                ),
                'reset': FicheroCommand(
                    id=f'{self.view_id}.reset',
                    label=_("Reset to Original"),
                    action=self._on_reset,
                    shortcut=toga.Key.MOD_1 + '0',
                    icon='resources/icons/toolbar/arrow.up.left.and.arrow.down.right@10x.png',
                    description=_("Reset image to original state"),
                    group=tools_group,
                    section=0,
                    order=3,
                    toolbar_text=_("Reset"),
                    toolbar_position='left',
                    show_in_menu=True,
                    show_in_bottom_toolbar=True,  # Show in edit mode toolbar
                    desktop_only=False,
                    context='edit'  # Only show in edit mode
                ),

                # ===== VIEW MENU - Zoom Commands =====
                'zoom_in': FicheroCommand(
                    id=f'{self.view_id}.zoom_in',
                    label=_("Zoom In"),
                    action=self._on_zoom_in,
                    shortcut=toga.Key.MOD_1 + toga.Key.PLUS,
                    description=_("Zoom in on image"),
                    group=toga.Group.VIEW,
                    section=0,
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
                    section=0,
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
                    section=0,
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
                    description=_("Zoom to 100% (actual size)"),
                    group=toga.Group.VIEW,
                    section=0,
                    order=3,
                    show_in_menu=True,
                    desktop_only=False,
                    context='normal'
                ),
                'fit_width': FicheroCommand(
                    id=f'{self.view_id}.fit_width',
                    label=_("Fit Width"),
                    action=self._on_zoom_fit_width,
                    shortcut=toga.Key.MOD_1 + toga.Key.SHIFT + '0',
                    description=_("Fit image to window width"),
                    group=toga.Group.VIEW,
                    section=0,
                    order=4,
                    show_in_menu=True,
                    desktop_only=False,
                    context='normal'
                ),
                'fit_height': FicheroCommand(
                    id=f'{self.view_id}.fit_height',
                    label=_("Fit Height"),
                    action=self._on_zoom_fit_height,
                    shortcut=toga.Key.MOD_1 + toga.Key.SHIFT + '9',
                    description=_("Fit image to window height"),
                    group=toga.Group.VIEW,
                    section=0,
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
                    section=0,
                    order=6,
                    show_in_menu=True,
                    desktop_only=False,
                    context='normal'
                ),

                # ===== GO MENU - Navigation Commands =====
                'prev_step': FicheroCommand(
                    id=f'{self.view_id}.prev_step',
                    label=_("Previous Step"),
                    action=lambda w: self._on_prev_step(w),
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
                    action=lambda w: self._on_next_step(w),
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
            }
            logger.info(f"✅ Defined {len(self.commands)} commands for OutputView")

        except Exception as e:
            logger.error(f"Failed to define commands: {e}")
            self.commands = {}

    def _create_content(self):
        """Create output view content - implements BaseView abstract method"""
        logger.info("Creating output view content")

        # Content area (will hold single or split view)
        # Don't use flex=1 - this prevents horizontal expansion
        # Instead, content will naturally size and scroll if needed
        self.content_area = toga.Box(
            style=Pack(
                direction=ROW if self.split_mode else COLUMN,
                flex=1,
                margin=10
                # No min-width/max-width - let pane constrain it
            )
        )

        # Add to content container (from BaseView)
        self.content_container.add(self.content_area)

        # Show initial state
        self._show_no_output_message()

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
        """Set up toolbars with navigation buttons using proper toolbar methods"""
        try:
            # Create top toolbar with file navigation (up/down chevrons)
            # Title will show file indicator in center
            self.top_toolbar = TopToolbar(
                self.app,
                title="File 1/1",  # Start with default, will update dynamically
                auto_mobile_nav=True,
                is_mobile=self.is_mobile,
                coordinator=self.coordinator
            )

            # Add Edit button to top toolbar (right side, text-only like Library button)
            # This toggles edit mode on/off and shows edit mode toolbar when active
            self.edit_btn = self.top_toolbar.add_regular_button(
                button_id="edit_output",
                position="right",
                text=_("Edit"),  # Text parameter for consistency with Library
                on_press=self._on_edit_pressed,
                style_class="right_aligned"
            )
            self.edit_btn.enabled = True

            # Create bottom toolbar with new layout:
            # LEFT: File navigation (prev/next file)
            # CENTER: Plan selector + Step selector dropdowns
            # RIGHT: Step navigation (prev/next step)
            self.bottom_toolbar = BottomToolbar(
                self.app,
                is_mobile=self.is_mobile,
                coordinator=self.coordinator
            )

            # LEFT: File navigation buttons (up/down arrows for file navigation)
            # Previous file (up chevron)
            self.bottom_prev_file_btn = self.bottom_toolbar.add_normal_mode_button(
                icon="resources/icons/toolbar/chevron.up@10x.png",
                on_press=self._on_prev_file,
                position="left",
                label=_("Prev\nFile")
            )
            self.bottom_prev_file_btn.enabled = False

            # Next file (down chevron)
            self.bottom_next_file_btn = self.bottom_toolbar.add_normal_mode_button(
                icon="resources/icons/toolbar/chevron.down@10x.png",
                on_press=self._on_next_file,
                position="left",
                label=_("Next\nFile")
            )
            self.bottom_next_file_btn.enabled = False

            # CENTER: Step selector dropdown only (plan selector removed per user request)
            import toga

            # Step selector dropdown (shows current step)
            self.step_selector = toga.Selection(
                items=["No steps loaded"],
                on_change=self._on_step_selected,
                style=Pack(flex=1, margin=(5, 10))
            )
            self.step_selector.enabled = False

            # Add step selector to toolbar center (plan selector removed)
            if hasattr(self.bottom_toolbar, 'center_content'):
                self.bottom_toolbar.center_content.add(self.step_selector)
                logger.debug("Added step selector to bottom toolbar center")
            else:
                logger.warning("Bottom toolbar has no center_content attribute")

            # RIGHT: Step navigation buttons (left/right chevrons)
            # Previous step (left chevron)
            self.prev_step_btn = self.bottom_toolbar.add_normal_mode_button(
                icon="resources/icons/toolbar/chevron.left@10x.png",
                on_press=self._on_prev_step,
                position="right",
                label=_("Prev\nStep")
            )
            self.prev_step_btn.enabled = False

            # Next step (right/forward chevron)
            self.next_step_btn = self.bottom_toolbar.add_normal_mode_button(
                icon="resources/icons/toolbar/chevron.forward@10x.png",
                on_press=self._on_next_step,
                position="right",
                label=_("Next\nStep")
            )
            self.next_step_btn.enabled = False

            # Create edit mode buttons for bottom toolbar (initially hidden)
            # These will be shown when Edit button is pressed
            self._create_edit_mode_buttons()

            # Edit mode state
            self.is_edit_mode = False

            # Set toolbars using BaseView method
            self.set_toolbars(self.top_toolbar, self.bottom_toolbar)

            logger.debug("Toolbars configured with centered titles and right-side navigation buttons")

        except Exception as e:
            logger.error(f"Failed to set up toolbars: {e}")

    def _create_edit_mode_buttons(self):
        """Create edit mode buttons for bottom toolbar using unified command system"""
        try:
            from fichero.shared.commands import CommandRegistry

            logger.info(f"🔧 Creating edit mode buttons for bottom toolbar (id={id(self.bottom_toolbar)})")

            # Get command registry
            registry = CommandRegistry.get_instance()

            # Add edit commands as toolbar buttons (edit mode only)
            # Commands are now registered via ViewCommandMixin in define_commands()
            # All edit buttons removed per user request - access via Edit menu and keyboard shortcuts
            edit_commands = [
                # No toolbar buttons - all commands available via menu/shortcuts
            ]

            for command_id, position in edit_commands:
                command = registry.get(command_id)
                if command and command.show_in_bottom_toolbar:
                    # Use add_command_button with mode="edit"
                    btn = self.bottom_toolbar.add_command_button(
                        command=command,
                        position=position,
                        mode="edit"
                    )
                    # Store button references for enable/disable operations
                    if "rotate_left" in command_id:
                        self.rotate_left_btn = btn
                    elif "rotate_right" in command_id:
                        self.rotate_right_btn = btn
                    elif "crop" in command_id:
                        self.crop_btn = btn
                    elif "reset" in command_id:
                        self.reset_btn = btn

            logger.info(f"✅ Created {len(self.bottom_toolbar._edit_buttons)} edit mode buttons using unified command system")

        except Exception as e:
            logger.error(f"Failed to create edit mode buttons: {e}")

    def _on_edit_pressed(self, widget):
        """Handle Edit button press - toggle edit mode"""
        try:
            self.is_edit_mode = not self.is_edit_mode

            if self.is_edit_mode:
                # Enter edit mode
                logger.info("Entering edit mode")
                self._enter_edit_mode()
            else:
                # Exit edit mode
                logger.info("Exiting edit mode")
                self._exit_edit_mode()

        except Exception as e:
            logger.error(f"Failed to toggle edit mode: {e}")

    def _enter_edit_mode(self):
        """Enter edit mode - show edit toolbar"""
        try:
            # Update Edit button text to "Done"
            if hasattr(self, 'edit_btn'):
                # Find the button in the toolbar and update its text
                # Note: Toga buttons don't support text updates easily, so we'll use coordinator
                pass

            # Use the toolbar coordinator to switch to edit mode
            # Pass view_id so toolbar can query declarative commands
            if self.coordinator:
                from fichero.shared.toolbars.toolbar_coordinator import EditModeState
                # Pass view_id for declarative command system
                self.coordinator.set_edit_mode(
                    EditModeState.EDIT,
                    context={'view_id': 'output'}
                )

            logger.debug("Entered output edit mode")

        except Exception as e:
            logger.error(f"Failed to enter edit mode: {e}")

    def _exit_edit_mode(self):
        """Exit edit mode - restore normal toolbar"""
        try:
            # Update Done button back to "Edit"
            if hasattr(self, 'edit_btn'):
                pass

            # Use the toolbar coordinator to switch to normal mode
            if self.coordinator:
                from fichero.shared.toolbars.toolbar_coordinator import EditModeState
                # Pass view_id for consistency with declarative system
                self.coordinator.set_edit_mode(
                    EditModeState.NORMAL,
                    context={'view_id': 'output'}
                )

            logger.debug("Exited output edit mode")

        except Exception as e:
            logger.error(f"Failed to exit edit mode: {e}")

    async def _on_rotate_left(self, widget):
        """Rotate image 90 degrees counter-clockwise"""
        try:
            if hasattr(self, 'current_webview') and self.current_webview:
                await self.current_webview.evaluate_javascript("rotateLeft();")
                logger.debug("Rotate: left (counter-clockwise)")
        except Exception as e:
            logger.error(f"Error rotating left: {e}")

    async def _on_rotate_right(self, widget):
        """Rotate image 90 degrees clockwise"""
        try:
            if hasattr(self, 'current_webview') and self.current_webview:
                await self.current_webview.evaluate_javascript("rotateRight();")
                logger.debug("Rotate: right (clockwise)")
        except Exception as e:
            logger.error(f"Error rotating right: {e}")

    async def _on_crop(self, widget):
        """Crop image (placeholder for future implementation)"""
        try:
            logger.info("Crop button pressed - feature to be implemented")
            # TODO: Implement crop functionality
        except Exception as e:
            logger.error(f"Error cropping: {e}")

    async def _on_reset(self, widget):
        """Reset image to original state"""
        try:
            if hasattr(self, 'current_webview') and self.current_webview:
                # Reset zoom to fit and rotation to 0
                await self.current_webview.evaluate_javascript("fitToWindow(); rotation = 0; updateImageSize();")
                logger.debug("Reset image to original state")
        except Exception as e:
            logger.error(f"Error resetting image: {e}")

    # Zoom command handlers
    async def _on_zoom_in(self, widget=None):
        """Zoom in"""
        if hasattr(self, 'current_webview') and self.current_webview:
            await self.current_webview.evaluate_javascript("zoomIn();")

    async def _on_zoom_out(self, widget=None):
        """Zoom out"""
        if hasattr(self, 'current_webview') and self.current_webview:
            await self.current_webview.evaluate_javascript("zoomOut();")

    async def _on_zoom_100(self, widget=None):
        """Zoom to 100% (actual size)"""
        if hasattr(self, 'current_webview') and self.current_webview:
            await self.current_webview.evaluate_javascript("actualSize();")

    async def _on_zoom_fit(self, widget=None):
        """Zoom to fit window"""
        if hasattr(self, 'current_webview') and self.current_webview:
            await self.current_webview.evaluate_javascript("fitToWindow();")

    async def _on_zoom_fit_width(self, widget=None):
        """Zoom to fit width"""
        if hasattr(self, 'current_webview') and self.current_webview:
            await self.current_webview.evaluate_javascript("fitToWidth();")

    async def _on_zoom_fit_height(self, widget=None):
        """Zoom to fit height"""
        if hasattr(self, 'current_webview') and self.current_webview:
            await self.current_webview.evaluate_javascript("fitToHeight();")

    async def _on_zoom_selection(self, widget=None):
        """Zoom to selected area (if selection exists)"""
        if hasattr(self, 'current_webview') and self.current_webview:
            await self.current_webview.evaluate_javascript("zoomToSelection();")

    def load_output(self, file_path: Path = None, source_files: List[Path] = None, source_index: int = 0,
                   item_id: str = None, source_item_ids: List[str] = None):
        """Load output from Director-processed file or original file

        Args:
            file_path: Path to the file to display (fallback mode - shows file without processing steps)
            source_files: List of source files for file navigation (LEGACY - use source_item_ids instead)
            source_index: Current index in source_files/source_item_ids
            item_id: Library item ID to load file-specific processing results from (PREFERRED)
            source_item_ids: List of library item IDs for file navigation (PREFERRED over source_files)
        """
        try:
            # Store item_id for future library queries
            self.current_item_id = item_id

            # PREFERRED: Store source item IDs for library-based navigation
            if source_item_ids:
                self.source_item_ids = source_item_ids
                self.current_source_index = source_index
                logger.info(f"📚 Loaded {len(self.source_item_ids)} source item IDs for library-based navigation, current index: {source_index}")
                # Also store source_files for backwards compatibility with legacy code paths
                self.source_files = source_files or []
            # LEGACY: Store source file list for file navigation
            elif source_files or not hasattr(self, 'source_files') or not self.source_files:
                self.source_files = source_files or []
                self.source_item_ids = []  # Clear item IDs if using legacy path
                self.current_source_index = source_index
                logger.info(f"Loaded {len(self.source_files)} source files (legacy mode), current index: {source_index}")
            else:
                logger.info(f"Keeping existing {len(self.source_files)} source files, updating index to: {source_index}")

            # PREFERRED: Use library_manager for file-specific filtering when available
            if item_id:
                # If we have an item_id, library_manager is REQUIRED
                if not self.library_manager:
                    error_msg = f"❌ CONFIGURATION ERROR: item_id provided but no library_manager available"
                    logger.error(error_msg)
                    self._show_error_message("Configuration error: No library manager available")
                    return

                logger.info(f"📊 Loading file-specific output data from LibraryManager for item_id: {item_id}")
                # Schedule async load using asyncio
                asyncio.create_task(self._load_from_library(item_id))
                self._update_file_navigation_buttons()
                return

            # FALLBACK: Show file without processing steps
            elif file_path:
                logger.info(f"Loading file without processing steps: {file_path}")
                self.current_file_path = file_path
                self._show_original_as_single_step(file_path)
            else:
                logger.error("No file_path or item_id provided")
                self._show_error_message("No file to display")
                return

            # Update file navigation buttons based on collection context
            self._update_file_navigation_buttons()

        except Exception as e:
            logger.error(f"Error loading output: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._show_error_message(f"Failed to load output: {e}")

    def _convert_processing_step_to_tool_output(self, step) -> ToolOutput:
        """Convert LibraryManager's ProcessingStep to OutputView's ToolOutput

        This conversion layer allows OutputView to use LibraryManager's pre-filtered
        data while maintaining compatibility with its existing display code.

        Args:
            step: ProcessingStep from DirectorOutputParser with fields:
                  - step_number: int
                  - step_name: str
                  - file_path: Path
                  - file_type: str ("image", "text", "document")
                  - description: str

        Returns:
            ToolOutput compatible with OutputView display system
        """
        from fichero.library.outputs_manager import ToolOutput

        # Create ToolOutput from ProcessingStep
        # ToolOutput requires: tool_name, output_folder, manifest_path
        tool_output = ToolOutput(
            tool_name=step.step_name,
            output_folder=step.file_path.parent,
            # Create a mock manifest path (ProcessingStep doesn't have manifest)
            # This is OK because we'll manually set _files below
            manifest_path=step.file_path.parent / f"{step.step_name.lower().replace(' ', '_')}.jsonl"
        )

        # Manually set the files to just this specific file
        # This ensures file-specific filtering - each ToolOutput only shows ONE file
        tool_output._files = [step.file_path]

        return tool_output

    async def _load_from_library(self, item_id: str):
        """Load file-specific processing steps from LibraryManager

        This is the PREFERRED method for loading outputs when working with
        library items. It ensures proper file-specific filtering and never
        mixes results from different files in batch processing.

        Args:
            item_id: Library item ID to load processing results for
        """
        try:
            # Get file-specific output data from LibraryManager (async call)
            output_data = await self.library_manager.get_item_output_data(item_id)

            # If no output data or no processing steps, try to show the source file/URL
            if not output_data or not output_data.get('processing_steps', []):
                logger.info(f"No processing results for item_id: {item_id}, showing source file/URL")

                # Get source path from output_data if available, otherwise query library directly
                source_path = None
                if output_data and output_data.get('source_path'):
                    source_path = output_data.get('source_path')
                else:
                    # Query library directly for source file/URL
                    item = await self.library_manager.get_item(item_id)
                    if item:
                        # Check if it's a URL (external source) or local file path
                        # item is a CollectionItem object - use attribute access (not .get())
                        # CollectionItem has: storage_type ("url"|"local"|"external"), source_path, type
                        if item.storage_type == "url" and item.source_path:
                            source_path = item.source_path  # URL string (don't convert to Path)
                        elif item.source_path:
                            from pathlib import Path
                            source_path = Path(item.source_path)  # Local file path

                # Display the source file/URL if available
                if source_path:
                    # source_path can be either a Path object (local file) or string (URL)
                    self._show_original_as_single_step(source_path)
                    return
                else:
                    # No source found at all
                    self._show_error_message("No source file or URL found for this item")
                    return

            # Extract processing steps (already file-specific filtered by LibraryManager)
            processing_steps = output_data.get('processing_steps', [])

            # Convert ProcessingStep objects to ToolOutput objects
            logger.info(f"Converting {len(processing_steps)} ProcessingSteps to ToolOutputs")
            self.processing_steps = []
            for step in processing_steps:
                tool_output = self._convert_processing_step_to_tool_output(step)
                self.processing_steps.append(tool_output)

            # Set current file path from first step
            if self.processing_steps and self.processing_steps[0].files:
                self.current_file_path = Path(self.processing_steps[0].files[0])

            # Set up navigation indices
            self.current_step_index = 0
            self.left_step_index = 0
            self.right_step_index = 0
            self.current_file_index = 0

            # Update UI
            self._update_step_selector()
            self._update_navigation()
            self._show_output_content()

            logger.info(f"✅ Successfully loaded {len(self.processing_steps)} file-specific processing steps from library")

        except Exception as e:
            logger.error(f"Error loading from library: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._show_error_message(f"Failed to load from library: {e}")

    def _update_navigation(self):
        """Update navigation buttons state"""
        try:
            if not self.processing_steps:
                return

            current_step = self.processing_steps[self.current_step_index]

            # Update step navigation buttons based on position (use display to remove from layout)
            has_prev_step = self.current_step_index > 0
            has_next_step = self.current_step_index < len(self.processing_steps) - 1

            self.prev_step_btn.style.display = "pack" if has_prev_step else "none"
            self.next_step_btn.style.display = "pack" if has_next_step else "none"

            # Update file navigation buttons on bottom toolbar
            has_prev_file = self.source_files and self.current_source_index > 0
            has_next_file = self.source_files and self.current_source_index < len(self.source_files) - 1

            self.bottom_prev_file_btn.style.display = "pack" if has_prev_file else "none"
            self.bottom_next_file_btn.style.display = "pack" if has_next_file else "none"

        except Exception as e:
            logger.error(f"Error updating navigation: {e}")
    
    async def _on_prev_file(self, widget):
        """Navigate to previous source file (keeping same step) using library-based navigation"""
        try:
            logger.info(f"🔼 Previous File button pressed!")

            # Save current viewer state before navigating
            await self._save_viewer_state()

            # PREFERRED: Library-based navigation with item IDs
            if self.source_item_ids and self.current_source_index > 0:
                self.current_source_index -= 1
                next_item_id = self.source_item_ids[self.current_source_index]

                # Check if next_item_id is None (item has no ID) - FAIL LOUDLY
                if next_item_id is None:
                    logger.error(f"❌ NAVIGATION FAILED: Item at index {self.current_source_index} has no library ID - cannot navigate")
                    self.current_source_index += 1  # Restore index
                    self._show_error_message(f"Navigation failed: Item has no library ID")
                    return

                # Reload output using library manager for proper file-specific filtering
                logger.info(f"📚 Library-based navigation: Loading item_id {next_item_id} (index {self.current_source_index})")
                self.load_output(
                    item_id=next_item_id,
                    source_item_ids=self.source_item_ids,
                    source_files=self.source_files,  # Pass for backwards compatibility
                    source_index=self.current_source_index
                )

            # LEGACY: File-based navigation (bypasses library - not recommended)
            elif self.source_files and self.current_source_index > 0:
                self.current_source_index -= 1
                next_file = self.source_files[self.current_source_index]

                logger.warning(f"⚠️ LEGACY file-based navigation: {next_file.name} (no library integration)")
                # Reload output for the new file, keeping the same step
                self.load_output(next_file, self.source_files, self.current_source_index)

        except Exception as e:
            logger.error(f"Error navigating to previous file: {e}")

    async def _on_next_file(self, widget):
        """Navigate to next source file (keeping same step) using library-based navigation"""
        try:
            logger.info(f"🔽 Next File button pressed!")

            # Save current viewer state before navigating
            await self._save_viewer_state()

            # PREFERRED: Library-based navigation with item IDs
            if self.source_item_ids and self.current_source_index < len(self.source_item_ids) - 1:
                self.current_source_index += 1
                next_item_id = self.source_item_ids[self.current_source_index]

                # Check if next_item_id is None (item has no ID) - FAIL LOUDLY
                if next_item_id is None:
                    logger.error(f"❌ NAVIGATION FAILED: Item at index {self.current_source_index} has no library ID - cannot navigate")
                    self.current_source_index -= 1  # Restore index
                    self._show_error_message(f"Navigation failed: Item has no library ID")
                    return

                # Reload output using library manager for proper file-specific filtering
                logger.info(f"📚 Library-based navigation: Loading item_id {next_item_id} (index {self.current_source_index})")
                self.load_output(
                    item_id=next_item_id,
                    source_item_ids=self.source_item_ids,
                    source_files=self.source_files,  # Pass for backwards compatibility
                    source_index=self.current_source_index
                )

            # LEGACY: File-based navigation (bypasses library - not recommended)
            elif self.source_files and self.current_source_index < len(self.source_files) - 1:
                self.current_source_index += 1
                next_file = self.source_files[self.current_source_index]

                logger.warning(f"⚠️ LEGACY file-based navigation: {next_file.name} (no library integration)")
                # Reload output for the new file, keeping the same step
                self.load_output(next_file, self.source_files, self.current_source_index)

        except Exception as e:
            logger.error(f"Error navigating to next file: {e}")

    def _update_file_navigation_buttons(self):
        """Update file navigation button visibility based on source files"""
        try:
            # Navigate through source files, not step files
            has_prev = self.source_files and self.current_source_index > 0
            has_next = self.source_files and self.current_source_index < len(self.source_files) - 1

            # Update top toolbar title to show source file position
            if self.source_files and hasattr(self.top_toolbar, 'title_label') and self.top_toolbar.title_label:
                self.top_toolbar.title_label.text = f"File {self.current_source_index + 1}/{len(self.source_files)}"
            elif hasattr(self.top_toolbar, 'title_label') and self.top_toolbar.title_label:
                self.top_toolbar.title_label.text = "File 1/1"

            # Show/hide buttons based on position (use display to remove from layout)
            # Note: Top toolbar file nav buttons removed per user request

            logger.debug(f"File nav buttons: prev={has_prev}, next={has_next}, source={self.current_source_index + 1}/{len(self.source_files)}")

        except Exception as e:
            logger.error(f"Error updating file navigation buttons: {e}")
    
    def _on_prev_step(self, widget):
        """Navigate to previous step"""
        if self.current_step_index > 0:
            self.current_step_index -= 1
            self.current_file_index = 0
            # Update split view indices
            self.left_step_index = max(0, self.current_step_index - 1)
            self.right_step_index = self.current_step_index
            self._load_current_file()
            self._update_navigation()
    
    def _on_next_step(self, widget):
        """Navigate to next step"""
        if self.current_step_index < len(self.processing_steps) - 1:
            self.current_step_index += 1
            self.current_file_index = 0
            # Update split view indices
            self.left_step_index = self.current_step_index - 1
            self.right_step_index = self.current_step_index
            self._load_current_file()
            self._update_navigation()

    def _on_back_to_collection(self, widget=None):
        """Navigate back to collection view using navigation controller"""
        try:
            if hasattr(self.app, 'view_integration') and hasattr(self.app.view_integration, 'navigation_controller'):
                nav_controller = self.app.view_integration.navigation_controller

                # Navigate back once (output -> collection)
                if hasattr(nav_controller, 'navigate_back'):
                    nav_controller.navigate_back()
                    logger.info("Navigated back to collection view")
                else:
                    logger.warning("NavigationController has no navigate_back method")
            else:
                logger.warning("Navigation controller not available")
        except Exception as e:
            logger.error(f"Error navigating back to collection: {e}")

    def _on_back_to_library(self, widget=None):
        """Navigate back to library view using navigation controller"""
        try:
            if hasattr(self.app, 'view_integration') and hasattr(self.app.view_integration, 'navigation_controller'):
                nav_controller = self.app.view_integration.navigation_controller

                # Navigate to library directly
                if hasattr(nav_controller, 'navigate_to_library'):
                    nav_controller.navigate_to_library()
                    logger.info("Navigated back to library view")
                else:
                    logger.warning("NavigationController has no navigate_to_library method")
            else:
                logger.warning("Navigation controller not available")
        except Exception as e:
            logger.error(f"Error navigating back to library: {e}")

    async def _save_viewer_state(self):
        """Save current viewer state (zoom, rotation, scroll position)"""
        try:
            if hasattr(self, 'current_webview') and self.current_webview:
                state_js = await self.current_webview.evaluate_javascript(
                    "JSON.stringify({scale: scale, rotation: rotation, scrollX: container.scrollLeft, scrollY: container.scrollTop})"
                )
                import json
                state = json.loads(state_js)
                self.viewer_state = {
                    'scale': state.get('scale', 1.0),
                    'rotation': state.get('rotation', 0),
                    'scroll_x': state.get('scrollX', 0),
                    'scroll_y': state.get('scrollY', 0)
                }
                logger.debug(f"Saved viewer state: {self.viewer_state}")
        except Exception as e:
            logger.debug(f"Could not save viewer state: {e}")

    async def _restore_viewer_state(self):
        """Restore saved viewer state to new image"""
        try:
            if hasattr(self, 'current_webview') and self.current_webview:
                await self.current_webview.evaluate_javascript(
                    f"restoreViewerState({self.viewer_state['scale']}, {self.viewer_state['rotation']}, {self.viewer_state['scroll_x']}, {self.viewer_state['scroll_y']});"
                )
                logger.debug(f"Restored viewer state: {self.viewer_state}")
        except Exception as e:
            logger.debug(f"Could not restore viewer state: {e}")


    def _load_current_file(self):
        """Load current file and update display"""
        try:
            current_step = self.processing_steps[self.current_step_index]
            current_file = current_step.files[self.current_file_index]
            self.current_file_path = current_file
            self._show_output_content()
        
        except Exception as e:
            logger.error(f"Error loading current file: {e}")
    
    def _show_output_content(self):
        """Show output content (split or single)"""
        self.content_area.clear()
        
        if self.split_mode and len(self.processing_steps) > 1:
            self._show_split_view()
        else:
            self._show_single_view()
    
    def _show_split_view(self):
        """Show dual-pane split view"""
        # Left pane
        left_step = self.processing_steps[self.left_step_index]
        if left_step.files:
            left_file = left_step.files[self.current_file_index] if self.current_file_index < len(left_step.files) else left_step.files[0]
            left_box = self._create_pane_box(left_file, left_step.tool_name)
            self.content_area.add(left_box)
        else:
            # No files in this step, show message
            self._show_error_message(f"No output files in step: {left_step.tool_name}")
            return

        # Right pane
        right_step = self.processing_steps[self.right_step_index]
        if right_step.files:
            right_file = right_step.files[self.current_file_index] if self.current_file_index < len(right_step.files) else right_step.files[0]
            right_box = self._create_pane_box(right_file, right_step.tool_name)
            self.content_area.add(right_box)
        else:
            # No files in this step, show left pane only with message
            pass
    
    def _show_single_view(self):
        """Show single pane view"""
        current_step = self.processing_steps[self.current_step_index]
        if current_step.files:
            current_file = current_step.files[self.current_file_index] if self.current_file_index < len(current_step.files) else current_step.files[0]
            single_box = self._create_pane_box(current_file, current_step.tool_name)
            self.content_area.add(single_box)
        else:
            # No files in this step, show message
            self._show_error_message(f"No output files in step: {current_step.tool_name}")
    
    def _create_pane_box(self, file_path: Path, step_name: str):
        """Create a pane box for displaying content

        In desktop mode, panes are constrained by the parent container width.
        They should not expand horizontally beyond the right pane's allocated space.

        Args:
            file_path: Path object for local files or string for URLs
            step_name: Name of the processing step
        """
        pane = toga.Box(
            style=Pack(
                direction=COLUMN,
                flex=1,  # Fills vertical space
                margin=5
                # No width set - constrained by parent (right_pane from MainWindow)
            )
        )

        # Header with truncated filename to prevent horizontal scrolling
        # Handle both Path objects and URL strings
        if isinstance(file_path, str) and file_path.startswith(('http://', 'https://')):
            # URL - extract filename from URL
            from urllib.parse import urlparse
            parsed = urlparse(file_path)
            filename = parsed.path.split('/')[-1] or "Remote Image"
        else:
            # Local file
            filename = file_path.name

        # Truncate filename if too long
        max_length = 50
        if len(filename) > max_length:
            filename = filename[:max_length-3] + "..."

        header = toga.Label(
            f"{step_name}: {filename}",
            style=Pack(
                font_weight='bold',
                margin=(0, 0, 10, 0)
            )
        )
        pane.add(header)

        # Content based on file type - use modular viewer system
        content = self._create_file_viewer(file_path)

        pane.add(content)
        return pane

    def _create_file_viewer(self, file_path: Path):
        """Create appropriate viewer widget based on file type - always in-app, no external viewers

        Supports both local files (Path objects) and URLs (strings).
        """
        # Check if this is a URL string
        is_url = isinstance(file_path, str) and file_path.startswith(('http://', 'https://'))

        if is_url:
            # URL - assume it's an image and create image viewer
            logger.info(f"Creating viewer for URL: {file_path[:100]}...")
            viewer = self._create_webview_image_viewer(file_path)
            return viewer

        # Local file - determine type by extension
        suffix = file_path.suffix.lower()

        # Try WebView first for most formats (HTML wrapper approach)
        # This gives us maximum flexibility and consistency
        try:
            # Image formats - wrap in HTML for better display control
            if suffix in ['.jpg', '.jpeg', '.png', '.tiff', '.tif', '.gif', '.bmp', '.webp']:
                viewer = self._create_webview_image_viewer(file_path)
                return viewer

            # HTML files - direct WebView
            elif suffix in ['.html', '.htm']:
                return self._create_webview_direct(file_path)

            # PDF - WebView with PDF.js or native PDF support
            elif suffix == '.pdf':
                return self._create_webview_pdf_viewer(file_path)

            # Text-based formats - wrap in HTML for syntax highlighting
            elif suffix in ['.txt', '.md', '.log', '.csv', '.xml', '.json']:
                return self._create_webview_text_viewer(file_path)

            # Office documents - convert to HTML
            elif suffix in ['.docx', '.doc']:
                return self._create_webview_docx_viewer(file_path)

            # Fallback - show as text in HTML
            else:
                return self._create_webview_text_viewer(file_path)

        except Exception as e:
            logger.error(f"Error creating viewer: {e}")
            # Ultimate fallback - show error message
            return toga.Label(f"Error loading file: {e}", style=Pack(margin=20))

    def _create_webview_image_viewer(self, file_path: Path):
        """Create WebView-based image viewer - controls via toolbar buttons

        Supports both local files and HTTP/HTTPS URLs.
        """
        import base64

        try:
            # Check if file_path is a URL (string starting with http:// or https://)
            is_url = isinstance(file_path, str) and file_path.startswith(('http://', 'https://'))

            if is_url:
                # For URLs, use the URL directly in the img src (no base64 encoding needed)
                image_data = None
                image_url = file_path
                logger.info(f"Creating image viewer for URL: {image_url[:100]}...")
            else:
                # For local files, read and encode as base64
                with open(file_path, 'rb') as f:
                    image_data = base64.b64encode(f.read()).decode('utf-8')
                image_url = None

            # Determine MIME type and image source
            if is_url:
                # For URLs, detect MIME from URL extension or default to jpeg
                url_lower = image_url.lower()
                if '.png' in url_lower:
                    mime_type = 'image/png'
                elif '.gif' in url_lower:
                    mime_type = 'image/gif'
                elif '.webp' in url_lower:
                    mime_type = 'image/webp'
                elif '.tiff' in url_lower or '.tif' in url_lower:
                    mime_type = 'image/tiff'
                else:
                    mime_type = 'image/jpeg'

                # Use URL directly as src
                img_src = image_url
                img_alt = "Remote Image"
            else:
                # For local files, use base64 data URI
                mime_types = {
                    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                    '.png': 'image/png', '.gif': 'image/gif',
                    '.bmp': 'image/bmp', '.webp': 'image/webp',
                    '.tiff': 'image/tiff', '.tif': 'image/tiff'
                }
                mime_type = mime_types.get(file_path.suffix.lower(), 'image/jpeg')
                img_src = f"data:{mime_type};base64,{image_data}"
                img_alt = file_path.name

            # Create simple HTML viewer - toolbar will provide controls
            # Use container-based sizing (100%, not viewport units) to respect parent constraints
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
                <style>
                    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                    html, body {{
                        width: 100%;
                        height: 100%;
                        background: #2c2c2c;
                        overflow: hidden;
                    }}
                    #imageContainer {{
                        width: 100%;
                        height: 100%;
                        overflow: auto;
                        position: relative;
                        cursor: grab;
                        -webkit-overflow-scrolling: touch;
                    }}
                    #imageContainer.grabbing {{ cursor: grabbing; }}
                    #imageWrapper {{
                        min-width: 100%;
                        min-height: 100%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                    }}
                    img {{
                        display: block;
                        max-width: 100%;
                        height: auto;
                        user-select: none;
                        -webkit-user-select: none;
                        pointer-events: none;
                    }}
                    #minimap {{
                        position: fixed;
                        top: 10px;
                        right: 10px;
                        width: 80px;
                        height: 80px;
                        background: rgba(0, 0, 0, 0.7);
                        border: 2px solid #666;
                        border-radius: 4px;
                        overflow: hidden;
                        display: none;  /* Hidden when not zoomed */
                        cursor: pointer;
                    }}
                    #minimapCanvas {{
                        width: 100%;
                        height: 100%;
                    }}
                    #minimapViewport {{
                        position: absolute;
                        border: 2px solid #4CAF50;
                        background: rgba(76, 175, 80, 0.2);
                        cursor: move;
                        pointer-events: auto;
                    }}
                    #selectionBox {{
                        position: absolute;
                        border: 2px dashed #FF9800;
                        background: rgba(255, 152, 0, 0.1);
                        display: none;
                        pointer-events: none;
                        z-index: 10;
                    }}
                    #loadingSpinner {{
                        position: absolute;
                        top: 50%;
                        left: 50%;
                        transform: translate(-50%, -50%);
                        color: white;
                        font-size: 18px;
                        display: none;
                    }}
                </style>
            </head>
            <body>
                <div id="imageContainer">
                    <div id="imageWrapper">
                        <div id="loadingSpinner">Loading image...</div>
                        <img id="image" src="{img_src}" alt="{img_alt}" crossorigin="anonymous">
                        <div id="selectionBox"></div>
                    </div>
                </div>
                <div id="minimap">
                    <canvas id="minimapCanvas"></canvas>
                    <div id="minimapViewport"></div>
                </div>
                <script>
                    let scale = 1;
                    let rotation = 0;  // Track rotation in degrees (0, 90, 180, 270)
                    let isDragging = false;
                    let isSelecting = false;
                    let selectionStart = null;
                    let selectionRect = null;
                    let startX, startY, scrollLeft, scrollTop;

                    const img = document.getElementById('image');
                    const container = document.getElementById('imageContainer');
                    const wrapper = document.getElementById('imageWrapper');
                    const minimap = document.getElementById('minimap');
                    const minimapCanvas = document.getElementById('minimapCanvas');
                    const minimapViewport = document.getElementById('minimapViewport');
                    const selectionBox = document.getElementById('selectionBox');
                    const loadingSpinner = document.getElementById('loadingSpinner');
                    const ctx = minimapCanvas.getContext('2d');

                    // Show loading spinner for remote images
                    const isRemoteImage = img.src.startsWith('http://') || img.src.startsWith('https://');
                    if (isRemoteImage) {{
                        loadingSpinner.style.display = 'block';
                    }}

                    // Load image fitted to window by default
                    img.onload = function() {{
                        loadingSpinner.style.display = 'none';
                        fitToWindow();
                        drawMinimap();
                    }};

                    // Handle image load errors (e.g., CORS, network issues)
                    img.onerror = function() {{
                        loadingSpinner.textContent = 'Failed to load image. Check network connection.';
                        console.error('Failed to load image:', img.src);
                    }};

                    function updateImageSize() {{
                        img.style.width = (img.naturalWidth * scale) + 'px';
                        img.style.height = (img.naturalHeight * scale) + 'px';
                        img.style.transform = `rotate(${{rotation}}deg)`;

                        // Update wrapper to be at least container size or image size
                        // Account for rotation by using bounding box size
                        let imgWidth = img.naturalWidth * scale;
                        let imgHeight = img.naturalHeight * scale;

                        // Swap dimensions if rotated 90 or 270 degrees
                        if (rotation === 90 || rotation === 270) {{
                            [imgWidth, imgHeight] = [imgHeight, imgWidth];
                        }}

                        wrapper.style.width = Math.max(imgWidth, container.clientWidth) + 'px';
                        wrapper.style.height = Math.max(imgHeight, container.clientHeight) + 'px';

                        // Update minimap
                        updateMinimap();
                    }}

                    function fitToWindow() {{
                        const containerRect = container.getBoundingClientRect();
                        const imgNaturalWidth = img.naturalWidth;
                        const imgNaturalHeight = img.naturalHeight;

                        scale = Math.min(
                            containerRect.width / imgNaturalWidth,
                            containerRect.height / imgNaturalHeight
                        );

                        updateImageSize();
                    }}

                    function fitToWidth() {{
                        const containerRect = container.getBoundingClientRect();
                        scale = containerRect.width / img.naturalWidth;
                        updateImageSize();
                    }}

                    function fitToHeight() {{
                        const containerRect = container.getBoundingClientRect();
                        scale = containerRect.height / img.naturalHeight;
                        updateImageSize();
                    }}

                    function actualSize() {{
                        scale = 1;
                        updateImageSize();
                        container.scrollTop = 0;
                        container.scrollLeft = 0;
                    }}

                    function zoomIn() {{
                        scale = Math.min(scale * 1.2, 5);
                        updateImageSize();
                    }}

                    function zoomOut() {{
                        scale = Math.max(scale / 1.2, 0.1);
                        updateImageSize();
                    }}

                    function getZoomLevel() {{
                        return Math.round(scale * 100);
                    }}

                    function rotateLeft() {{
                        rotation = (rotation - 90 + 360) % 360;
                        updateImageSize();
                    }}

                    function rotateRight() {{
                        rotation = (rotation + 90) % 360;
                        updateImageSize();
                    }}

                    function zoomToSelection() {{
                        // Check if there's a stored selection
                        if (!selectionRect) {{
                            console.log("No selection to zoom to");
                            return;
                        }}

                        // Calculate the scale needed to fit the selection
                        const containerRect = container.getBoundingClientRect();
                        const scaleX = containerRect.width / selectionRect.width;
                        const scaleY = containerRect.height / selectionRect.height;
                        scale = Math.min(scaleX, scaleY, 5);  // Cap at 5x zoom

                        updateImageSize();

                        // Center the selection in the viewport
                        const selectionCenterX = selectionRect.x + selectionRect.width / 2;
                        const selectionCenterY = selectionRect.y + selectionRect.height / 2;
                        container.scrollLeft = selectionCenterX - containerRect.width / 2;
                        container.scrollTop = selectionCenterY - containerRect.height / 2;

                        // Hide selection box after zooming
                        selectionBox.style.display = 'none';
                    }}

                    function restoreViewerState(savedScale, savedRotation, savedScrollX, savedScrollY) {{
                        scale = savedScale;
                        rotation = savedRotation;
                        updateImageSize();

                        // Restore scroll position after a brief delay to ensure layout is complete
                        setTimeout(function() {{
                            container.scrollLeft = savedScrollX;
                            container.scrollTop = savedScrollY;
                        }}, 50);
                    }}

                    function drawMinimap() {{
                        minimapCanvas.width = 80;
                        minimapCanvas.height = 80;

                        const minimapScale = Math.min(80 / img.naturalWidth, 80 / img.naturalHeight);
                        const minimapWidth = img.naturalWidth * minimapScale;
                        const minimapHeight = img.naturalHeight * minimapScale;
                        const offsetX = (80 - minimapWidth) / 2;
                        const offsetY = (80 - minimapHeight) / 2;

                        ctx.clearRect(0, 0, 80, 80);
                        ctx.drawImage(img, offsetX, offsetY, minimapWidth, minimapHeight);
                    }}

                    function updateMinimap() {{
                        // Show minimap except when viewing at exact fit-to-window scale
                        const fitScale = Math.min(container.clientWidth / img.naturalWidth, container.clientHeight / img.naturalHeight);
                        if (Math.abs(scale - fitScale) > 0.01) {{
                            minimap.style.display = 'block';
                            updateMinimapViewport();
                        }} else {{
                            minimap.style.display = 'none';
                        }}
                    }}

                    function updateMinimapViewport() {{
                        const minimapScale = Math.min(80 / img.naturalWidth, 80 / img.naturalHeight);
                        const minimapWidth = img.naturalWidth * minimapScale;
                        const minimapHeight = img.naturalHeight * minimapScale;
                        const offsetX = (80 - minimapWidth) / 2;
                        const offsetY = (80 - minimapHeight) / 2;

                        // Get actual displayed image dimensions
                        const displayedWidth = img.naturalWidth * scale;
                        const displayedHeight = img.naturalHeight * scale;

                        // Calculate viewport size and position relative to displayed image
                        const viewportWidth = (container.clientWidth / displayedWidth) * minimapWidth;
                        const viewportHeight = (container.clientHeight / displayedHeight) * minimapHeight;
                        const viewportX = (container.scrollLeft / displayedWidth) * minimapWidth + offsetX;
                        const viewportY = (container.scrollTop / displayedHeight) * minimapHeight + offsetY;

                        minimapViewport.style.width = viewportWidth + 'px';
                        minimapViewport.style.height = viewportHeight + 'px';
                        minimapViewport.style.left = viewportX + 'px';
                        minimapViewport.style.top = viewportY + 'px';
                    }}

                    // Update minimap viewport on scroll
                    container.addEventListener('scroll', updateMinimapViewport);

                    // Drag viewport box or click minimap to jump
                    let isDraggingViewport = false;
                    let dragOffset = null;
                    let initialScroll = null;

                    function minimapToImageCoords(minimapX, minimapY) {{
                        const minimapScale = Math.min(80 / img.naturalWidth, 80 / img.naturalHeight);
                        const minimapWidth = img.naturalWidth * minimapScale;
                        const minimapHeight = img.naturalHeight * minimapScale;
                        const offsetX = (80 - minimapWidth) / 2;
                        const offsetY = (80 - minimapHeight) / 2;

                        const relX = (minimapX - offsetX) / minimapWidth;
                        const relY = (minimapY - offsetY) / minimapHeight;

                        return {{
                            x: relX * img.naturalWidth * scale - container.clientWidth / 2,
                            y: relY * img.naturalHeight * scale - container.clientHeight / 2
                        }};
                    }}

                    minimapViewport.addEventListener('mousedown', function(e) {{
                        e.preventDefault();
                        e.stopPropagation();
                        isDraggingViewport = true;

                        // Store the offset from the viewport's top-left corner
                        const viewportRect = minimapViewport.getBoundingClientRect();
                        const minimapRect = minimap.getBoundingClientRect();
                        dragOffset = {{
                            x: e.clientX - viewportRect.left,
                            y: e.clientY - viewportRect.top
                        }};

                        // Store initial scroll position
                        initialScroll = {{
                            x: container.scrollLeft,
                            y: container.scrollTop
                        }};
                    }});

                    minimap.addEventListener('mousedown', function(e) {{
                        if (e.target === minimap || e.target === minimapCanvas) {{
                            const rect = minimap.getBoundingClientRect();
                            const clickX = e.clientX - rect.left;
                            const clickY = e.clientY - rect.top;
                            const coords = minimapToImageCoords(clickX, clickY);
                            container.scrollLeft = coords.x;
                            container.scrollTop = coords.y;
                        }}
                    }});

                    document.addEventListener('mousemove', function(e) {{
                        if (isDraggingViewport && dragOffset) {{
                            const rect = minimap.getBoundingClientRect();
                            // Calculate new viewport position (accounting for the drag offset)
                            const viewportX = e.clientX - rect.left - dragOffset.x;
                            const viewportY = e.clientY - rect.top - dragOffset.y;

                            // Convert to scroll coordinates
                            const minimapScale = Math.min(80 / img.naturalWidth, 80 / img.naturalHeight);
                            const minimapWidth = img.naturalWidth * minimapScale;
                            const minimapHeight = img.naturalHeight * minimapScale;
                            const offsetX = (80 - minimapWidth) / 2;
                            const offsetY = (80 - minimapHeight) / 2;

                            const relX = (viewportX - offsetX) / minimapWidth;
                            const relY = (viewportY - offsetY) / minimapHeight;

                            container.scrollLeft = relX * img.naturalWidth * scale;
                            container.scrollTop = relY * img.naturalHeight * scale;
                        }}
                    }});

                    document.addEventListener('mouseup', function() {{
                        isDraggingViewport = false;
                        dragOffset = null;
                        initialScroll = null;
                    }});

                    // Mouse wheel/trackpad:
                    // - Default: pans up/down (native scrolling)
                    // - With Cmd/Ctrl: zooms in/out
                    container.addEventListener('wheel', function(e) {{
                        if (e.metaKey || e.ctrlKey) {{
                            // Zoom with modifier key
                            e.preventDefault();
                            if (e.deltaY < 0) {{
                                zoomIn();
                            }} else {{
                                zoomOut();
                            }}
                        }}
                        // Otherwise allow native scrolling
                    }}, {{ passive: false }});

                    // Pan with mouse drag OR selection with Shift+drag
                    container.addEventListener('mousedown', function(e) {{
                        // Shift key enables selection mode
                        if (e.shiftKey) {{
                            isSelecting = true;
                            isDragging = false;

                            // Get mouse position relative to the image
                            const rect = img.getBoundingClientRect();
                            selectionStart = {{
                                x: e.clientX - rect.left,
                                y: e.clientY - rect.top
                            }};

                            // Show selection box at start position
                            selectionBox.style.left = e.clientX - container.getBoundingClientRect().left + 'px';
                            selectionBox.style.top = e.clientY - container.getBoundingClientRect().top + 'px';
                            selectionBox.style.width = '0px';
                            selectionBox.style.height = '0px';
                            selectionBox.style.display = 'block';

                            container.style.cursor = 'crosshair';
                        }} else {{
                            isDragging = true;
                            isSelecting = false;
                            container.classList.add('grabbing');
                            startX = e.pageX - container.offsetLeft;
                            startY = e.pageY - container.offsetTop;
                            scrollLeft = container.scrollLeft;
                            scrollTop = container.scrollTop;
                        }}
                    }});

                    container.addEventListener('mouseleave', function() {{
                        isDragging = false;
                        isSelecting = false;
                        container.classList.remove('grabbing');
                        container.style.cursor = 'grab';
                    }});

                    container.addEventListener('mouseup', function(e) {{
                        if (isSelecting) {{
                            // Finalize selection
                            isSelecting = false;
                            container.style.cursor = 'grab';

                            // Save selection rect for zoom-to-selection
                            if (selectionRect && selectionRect.width > 10 && selectionRect.height > 10) {{
                                console.log("Selection created:", selectionRect);
                            }} else {{
                                // Too small, clear it
                                selectionBox.style.display = 'none';
                                selectionRect = null;
                            }}
                        }}

                        isDragging = false;
                        container.classList.remove('grabbing');
                    }});

                    container.addEventListener('mousemove', function(e) {{
                        if (isSelecting) {{
                            // Update selection box
                            const containerRect = container.getBoundingClientRect();
                            const currentX = e.clientX - containerRect.left;
                            const currentY = e.clientY - containerRect.top;

                            const startXContainer = parseFloat(selectionBox.style.left);
                            const startYContainer = parseFloat(selectionBox.style.top);

                            const width = currentX - startXContainer;
                            const height = currentY - startYContainer;

                            // Update selection box visual
                            if (width >= 0) {{
                                selectionBox.style.width = width + 'px';
                            }} else {{
                                selectionBox.style.left = currentX + 'px';
                                selectionBox.style.width = Math.abs(width) + 'px';
                            }}

                            if (height >= 0) {{
                                selectionBox.style.height = height + 'px';
                            }} else {{
                                selectionBox.style.top = currentY + 'px';
                                selectionBox.style.height = Math.abs(height) + 'px';
                            }}

                            // Store selection rectangle in image coordinates
                            const imgRect = img.getBoundingClientRect();
                            selectionRect = {{
                                x: parseFloat(selectionBox.style.left) + container.scrollLeft,
                                y: parseFloat(selectionBox.style.top) + container.scrollTop,
                                width: Math.abs(width),
                                height: Math.abs(height)
                            }};

                        }} else if (isDragging) {{
                            // Pan the image
                            e.preventDefault();
                            const x = e.pageX - container.offsetLeft;
                            const y = e.pageY - container.offsetTop;
                            const walkX = (x - startX);
                            const walkY = (y - startY);
                            container.scrollLeft = scrollLeft - walkX;
                            container.scrollTop = scrollTop - walkY;
                        }}
                    }});

                    // Pinch-to-zoom support for touch devices
                    let lastTouchDistance = 0;
                    let touchStartScale = 1;

                    container.addEventListener('touchstart', function(e) {{
                        if (e.touches.length === 2) {{
                            const touch1 = e.touches[0];
                            const touch2 = e.touches[1];
                            lastTouchDistance = Math.hypot(
                                touch2.pageX - touch1.pageX,
                                touch2.pageY - touch1.pageY
                            );
                            touchStartScale = scale;
                        }}
                    }}, {{ passive: true }});

                    container.addEventListener('touchmove', function(e) {{
                        if (e.touches.length === 2) {{
                            e.preventDefault();
                            const touch1 = e.touches[0];
                            const touch2 = e.touches[1];
                            const touchDistance = Math.hypot(
                                touch2.pageX - touch1.pageX,
                                touch2.pageY - touch1.pageY
                            );

                            if (lastTouchDistance > 0) {{
                                const ratio = touchDistance / lastTouchDistance;
                                scale = Math.min(Math.max(touchStartScale * ratio, 0.1), 5);
                                updateImageSize();
                                touchStartScale = scale;
                                lastTouchDistance = touchDistance;
                            }}
                        }}
                    }}, {{ passive: false }});

                    container.addEventListener('touchend', function(e) {{
                        if (e.touches.length < 2) {{
                            lastTouchDistance = 0;
                        }}
                    }}, {{ passive: true }});
                </script>
            </body>
            </html>
            """

            webview = toga.WebView(style=Pack(flex=1))
            webview.set_content("", html)

            # Store reference for toolbar controls
            self.current_webview = webview

            return webview

        except Exception as e:
            logger.error(f"Error creating image viewer: {e}")
            return toga.Label(f"Error loading image: {e}", style=Pack(margin=20))

    def _create_webview_direct(self, file_path: Path):
        """Create WebView for direct HTML files"""
        try:
            return toga.WebView(url=f"file://{file_path.absolute()}", style=Pack(flex=1))
        except Exception as e:
            return toga.Label(f"Error loading HTML: {e}", style=Pack(margin=20))

    def _create_webview_pdf_viewer(self, file_path: Path):
        """Create WebView PDF viewer using browser's native PDF support"""
        try:
            # Modern browsers can display PDFs natively
            return toga.WebView(url=f"file://{file_path.absolute()}", style=Pack(flex=1))
        except Exception as e:
            return toga.Label(f"Error loading PDF: {e}", style=Pack(margin=20))

    def _create_webview_text_viewer(self, file_path: Path):
        """Create WebView for text files with syntax highlighting"""
        import html

        try:
            # Read file content
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()

            # Escape HTML
            escaped_content = html.escape(content)

            # Create HTML with syntax highlighting
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{
                        margin: 0;
                        padding: 20px;
                        font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
                        font-size: 13px;
                        background: #f5f5f5;
                    }}
                    pre {{
                        background: white;
                        padding: 15px;
                        border-radius: 4px;
                        overflow-x: auto;
                        white-space: pre-wrap;
                        word-wrap: break-word;
                    }}
                </style>
            </head>
            <body>
                <pre>{escaped_content}</pre>
            </body>
            </html>
            """

            webview = toga.WebView(style=Pack(flex=1))
            webview.set_content("", html_content)
            return webview

        except Exception as e:
            return toga.Label(f"Error loading text: {e}", style=Pack(margin=20))

    def _create_webview_docx_viewer(self, file_path: Path):
        """Create WebView for Word documents - extract and display as HTML"""
        import html

        try:
            # Try to extract text from DOCX
            try:
                from docx import Document
                doc = Document(file_path)
                paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
                content = '\n\n'.join(paragraphs) if paragraphs else "(Document appears to be empty)"
            except ImportError:
                content = "Install 'python-docx' to view document content\n\nFile: " + file_path.name

            # Escape and format as HTML
            escaped_content = html.escape(content)
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{
                        margin: 0;
                        padding: 30px;
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                        line-height: 1.6;
                        background: #f5f5f5;
                    }}
                    .content {{
                        background: white;
                        padding: 40px;
                        border-radius: 4px;
                        max-width: 800px;
                        margin: 0 auto;
                    }}
                    p {{ margin: 1em 0; }}
                </style>
            </head>
            <body>
                <div class="content">
                    <p>{escaped_content.replace(chr(10) + chr(10), '</p><p>').replace(chr(10), '<br>')}</p>
                </div>
            </body>
            </html>
            """

            webview = toga.WebView(style=Pack(flex=1))
            webview.set_content("", html_content)
            return webview

        except Exception as e:
            return toga.Label(f"Error loading document: {e}", style=Pack(margin=20))

    def _show_original_as_single_step(self, file_path: Path):
        """Show original file as a single step (no processing steps available)"""
        self.content_area.clear()

        # Create a pseudo-step for the original file
        from fichero.library.outputs_manager import ToolOutput

        # Mock ToolOutput for original file
        self.processing_steps = []
        self.current_step_index = 0
        self.current_file_index = 0
        self.left_step_index = 0
        self.right_step_index = 0

        # Display the file
        box = self._create_pane_box(file_path, "Original")
        self.content_area.add(box)

        # Update top toolbar title to show "File 1/1"
        if hasattr(self.top_toolbar, 'title_label') and self.top_toolbar.title_label:
            self.top_toolbar.title_label.text = "File 1/1"

        # Hide file navigation buttons (no other files in this context)
        # Note: Top toolbar file nav buttons removed per user request
        self.bottom_prev_file_btn.style.display = "none"
        self.bottom_next_file_btn.style.display = "none"

        # Hide step navigation buttons (no processing steps)
        self.prev_step_btn.style.display = "none"
        self.next_step_btn.style.display = "none"

        logger.debug("Showing original file as single step")
    
    def _show_no_output_message(self):
        """Show message when no output loaded"""
        self.content_area.clear()
        
        message = toga.Box(
            style=Pack(
                direction=COLUMN,
                alignment='center',
                flex=1
            )
        )
        
        icon = toga.Label(
            "📊",
            style=Pack(
                font_size=64,
                text_align='center',
                margin=(0, 0, 20, 0)
            )
        )
        message.add(icon)
        
        text = toga.Label(
            "No output loaded\n\nSelect a processed file from the library to view outputs",
            style=Pack(
                text_align='center',
                margin=20
            )
        )
        message.add(text)
        
        self.content_area.add(message)
    
    def _show_error_message(self, error: str):
        """Show error message"""
        self.content_area.clear()
        
        error_box = toga.Box(
            style=Pack(
                direction=COLUMN,
                alignment='center',
                flex=1
            )
        )
        
        icon = toga.Label(
            "⚠️",
            style=Pack(
                font_size=48,
                text_align='center',
                margin=(0, 0, 10, 0)
            )
        )
        error_box.add(icon)
        
        text = toga.Label(
            error,
            style=Pack(
                text_align='center',
                margin=10
            )
        )
        error_box.add(text)

        self.content_area.add(error_box)

    def _update_step_selector(self):
        """Update the step selector dropdown with processing step names"""
        try:
            if not hasattr(self, 'step_selector') or not self.step_selector:
                return

            if not self.processing_steps:
                self.step_selector.items = ["No steps loaded"]
                self.step_selector.enabled = False
                return

            # Build list of step names
            step_names = []
            for idx, step in enumerate(self.processing_steps):
                step_name = f"{idx + 1}. {step.tool_name}"
                step_names.append(step_name)

            self.step_selector.items = step_names
            self.step_selector.enabled = True

            # Set current selection
            if hasattr(self, 'current_step_index') and 0 <= self.current_step_index < len(step_names):
                self.step_selector.value = step_names[self.current_step_index]

            logger.debug(f"Updated step selector with {len(step_names)} steps")

        except Exception as e:
            logger.error(f"Failed to update step selector: {e}")

    def _on_plan_selected(self, widget):
        """Handle plan selection from dropdown"""
        try:
            if not widget.value:
                return

            # Extract plan information from selection
            selection_text = str(widget.value)
            logger.info(f"Plan selected from dropdown: {selection_text}")

            # TODO: Implement plan switching logic when needed
            # For now, this is a display-only dropdown showing the current plan

        except Exception as e:
            logger.error(f"Failed to handle plan selection: {e}")

    def _on_step_selected(self, widget):
        """Handle step selection from dropdown"""
        try:
            if not self.processing_steps or not widget.value:
                return

            # Extract step index from selection (format: "1. step_name")
            selection_text = str(widget.value)
            if '. ' not in selection_text:
                return

            step_num_str = selection_text.split('.')[0]
            try:
                step_index = int(step_num_str) - 1
            except ValueError:
                return

            if 0 <= step_index < len(self.processing_steps):
                logger.info(f"Step selected from dropdown: {step_index} ({self.processing_steps[step_index].tool_name})")

                # Update current step index
                self.current_step_index = step_index
                self.left_step_index = step_index
                self.right_step_index = step_index

                # Update current file to first file in selected step
                if self.processing_steps[step_index].files:
                    self.current_file_path = Path(self.processing_steps[step_index].files[0])

                # Refresh display
                self._update_navigation()
                self._show_output_content()

                # Update inspector with step metadata
                if hasattr(self.app, 'inspector_window') and self.app.inspector_window:
                    metadata = self._get_step_metadata(step_index)
                    self.app.inspector_window.update_metadata(metadata, selection_type="STEP")
                    logger.debug("Inspector updated with step metadata")

        except Exception as e:
            logger.error(f"Failed to handle step selection: {e}")

    def _get_step_metadata(self, step_index: int) -> str:
        """Get metadata for a selected step"""
        try:
            if not self.processing_steps or step_index >= len(self.processing_steps):
                return "No step data available"

            step = self.processing_steps[step_index]

            metadata = f"=== STEP METADATA ===\n"
            metadata += f"Tool Name: {step.tool_name}\n"
            metadata += f"Step Number: {step_index + 1}\n"
            metadata += f"Status: {step.status}\n"
            metadata += f"\n"

            metadata += f"=== FILES ===\n"
            metadata += f"File Count: {len(step.files)}\n"
            if step.files:
                metadata += f"First File: {Path(step.files[0]).name}\n"
            metadata += f"\n"

            metadata += f"=== TIMING ===\n"
            if step.start_time:
                metadata += f"Start Time: {step.start_time}\n"
            if step.end_time:
                metadata += f"End Time: {step.end_time}\n"
            if step.duration:
                metadata += f"Duration: {step.duration:.2f}s\n"

            return metadata

        except Exception as e:
            logger.error(f"Failed to get step metadata: {e}")
            return f"Error getting step metadata: {e}"
