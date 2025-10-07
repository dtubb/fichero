"""
OutputView - Main Window Output View

Displays processing outputs with flexible dual-pane comparison and navigation.
"""

import logging
from typing import Optional, List
from pathlib import Path

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW

from fichero.shared.views.base_view import BaseView
from fichero.shared.toolbars import ToolbarCoordinator, TopToolbar, BottomToolbar
from fichero.library.outputs_manager import OutputsManager, OutputSession, ToolOutput
from fichero.library.outputs.editor_registry import EditorRegistry

logger = logging.getLogger(__name__)


class OutputView(BaseView):
    """Output view for main window center pane"""
    
    def __init__(self, app, is_mobile: bool = False):
        """Initialize output view"""
        logger.info("🔧 OutputView.__init__ starting")

        # Initialize outputs system
        self.outputs_manager = OutputsManager()
        self.editor_registry = EditorRegistry()

        # Output state
        self.output_session: Optional[OutputSession] = None
        self.processing_steps: List[ToolOutput] = []
        self.current_step_index: int = 0
        self.current_file_index: int = 0
        self.current_file_path: Optional[Path] = None

        # Library integration (for item_id-based loading)
        self.current_item_id: Optional[str] = None
        self.library_manager = None  # Will be set when loading from library

        # Source file list (for file navigation across different input files)
        self.source_files: List[Path] = []
        self.current_source_index: int = 0

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

        # Call parent init (creates toolbars)
        super().__init__(app, is_mobile)

        # Set up toolbars with custom buttons
        self._setup_toolbars()

        logger.info("✅ OutputView initialization complete")
    
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
        """Show callback"""
        self.is_visible = True

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

            # Add file navigation buttons to top toolbar right side
            # Previous file (up chevron)
            self.prev_file_btn = self.top_toolbar.add_regular_button(
                button_id="prev_file",
                position="right",
                icon="resources/icons/toolbar/chevron.up@10x.png",
                on_press=self._on_prev_file,
                label=_("Previous\nFile")
            )
            self.prev_file_btn.enabled = False

            # Next file (down chevron)
            self.next_file_btn = self.top_toolbar.add_regular_button(
                button_id="next_file",
                position="right",
                icon="resources/icons/toolbar/chevron.down@10x.png",
                on_press=self._on_next_file,
                label=_("Next\nFile")
            )
            self.next_file_btn.enabled = False

            # Create bottom toolbar with step navigation (left/right chevrons)
            # Will use add_title for centered step indicator
            self.bottom_toolbar = BottomToolbar(
                self.app,
                is_mobile=self.is_mobile,
                coordinator=self.coordinator
            )

            # Add centered step indicator title
            self.step_title = self.bottom_toolbar.add_title(
                title="Step 1/1",
                on_click=None
            )

            # Add step navigation buttons to bottom toolbar right side
            # Previous step (left chevron)
            self.prev_step_btn = self.bottom_toolbar.add_normal_mode_button(
                icon="resources/icons/toolbar/chevron.left@10x.png",
                on_press=self._on_prev_step,
                position="right",
                label=_("Previous\nStep")
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

            # Add image zoom controls (shown only when viewing images)
            self.zoom_out_btn = self.bottom_toolbar.add_normal_mode_button(
                icon="resources/icons/toolbar/minus.magnifyingglass@10x.png",
                on_press=self._on_zoom_out,
                position="left",
                label=_("−")
            )
            self.zoom_out_btn.style.display = "none"  # Hidden by default

            self.zoom_fit_btn = self.bottom_toolbar.add_normal_mode_button(
                icon="resources/icons/toolbar/arrow.up.left.and.arrow.down.right@10x.png",
                on_press=self._on_zoom_fit,
                position="left",
                label=_("Fit")
            )
            self.zoom_fit_btn.style.display = "none"  # Hidden by default

            self.zoom_fit_width_btn = self.bottom_toolbar.add_normal_mode_button(
                icon="resources/icons/toolbar/arrow.left.and.right@10x.png",
                on_press=self._on_zoom_fit_width,
                position="left",
                label=_("Width")
            )
            self.zoom_fit_width_btn.style.display = "none"  # Hidden by default

            self.zoom_fit_height_btn = self.bottom_toolbar.add_normal_mode_button(
                icon="resources/icons/toolbar/arrow.up.and.down@10x.png",
                on_press=self._on_zoom_fit_height,
                position="left",
                label=_("Height")
            )
            self.zoom_fit_height_btn.style.display = "none"  # Hidden by default

            self.zoom_100_btn = self.bottom_toolbar.add_normal_mode_button(
                icon="resources/icons/toolbar/arrow.up.left.and.down.right.magnifyingglass@10x.png",
                on_press=self._on_zoom_100,
                position="left",
                label=_("100%")
            )
            self.zoom_100_btn.style.display = "none"  # Hidden by default

            self.zoom_in_btn = self.bottom_toolbar.add_normal_mode_button(
                icon="resources/icons/toolbar/plus.magnifyingglass@10x.png",
                on_press=self._on_zoom_in,
                position="left",
                label=_("+")
            )
            self.zoom_in_btn.style.display = "none"  # Hidden by default

            # Add rotation controls (shown only when viewing images)
            self.rotate_left_btn = self.bottom_toolbar.add_normal_mode_button(
                icon="resources/icons/toolbar/rotate.left@10x.png",
                on_press=self._on_rotate_left,
                position="left",
                label=_("Rotate\nLeft")
            )
            self.rotate_left_btn.style.display = "none"  # Hidden by default

            self.rotate_right_btn = self.bottom_toolbar.add_normal_mode_button(
                icon="resources/icons/toolbar/rotate.right@10x.png",
                on_press=self._on_rotate_right,
                position="left",
                label=_("Rotate\nRight")
            )
            self.rotate_right_btn.style.display = "none"  # Hidden by default

            # Add step selector dropdown in center of bottom toolbar
            import toga
            self.step_selector = toga.Selection(
                items=["No steps loaded"],
                on_change=self._on_step_selected,
                style=Pack(flex=1, margin=(5, 10))
            )
            self.step_selector.enabled = False

            # Add to toolbar center
            if hasattr(self.bottom_toolbar, 'center_content'):
                self.bottom_toolbar.center_content.add(self.step_selector)
                logger.debug("Added step selector to bottom toolbar center")
            else:
                logger.warning("Bottom toolbar has no center_content attribute")

            # Set toolbars using BaseView method
            self.set_toolbars(self.top_toolbar, self.bottom_toolbar)

            logger.debug("Toolbars configured with centered titles and right-side navigation buttons")

        except Exception as e:
            logger.error(f"Failed to set up toolbars: {e}")
    
    def load_output(self, file_path: Path = None, source_files: List[Path] = None, source_index: int = 0,
                   output_root_path: Path = None, item_id: str = None):
        """Load output from Director-processed file or original file

        Args:
            file_path: Path to the file to display (legacy mode)
            source_files: List of source files for file navigation (up/down between files)
            source_index: Current index in source_files
            output_root_path: Direct path to Director output folder (preferred)
            item_id: Library item ID to load processing results from (future enhancement)
        """
        try:
            # Store item_id for future library queries
            self.current_item_id = item_id

            # Store source file list for file navigation
            if source_files or not hasattr(self, 'source_files') or not self.source_files:
                self.source_files = source_files or []
                self.current_source_index = source_index
                logger.info(f"Loaded {len(self.source_files)} source files, current index: {source_index}")
            else:
                logger.info(f"Keeping existing {len(self.source_files)} source files, updating index to: {source_index}")

            # Prioritize explicit output_root_path over file-based discovery
            if output_root_path:
                logger.info(f"📊 Loading from Director output root: {output_root_path}")
                self._load_from_output_root(output_root_path, file_path)
            elif file_path:
                logger.info(f"Loading output from file: {file_path}")
                self.current_file_path = file_path

                # Try to detect Director output structure
                output_root = self._find_output_root(file_path)

                if output_root:
                    self._load_from_output_root(output_root, file_path)
                else:
                    # Not a Director output - show original file as single step
                    logger.info("Not a Director output, showing original file as single step")
                    self._show_original_as_single_step(file_path)
            else:
                logger.error("No file_path or output_root_path provided")
                self._show_error_message("No file to display")
                return

            # Update file navigation buttons based on collection context
            self._update_file_navigation_buttons()

        except Exception as e:
            logger.error(f"Error loading output: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._show_error_message(f"Failed to load output: {e}")
    
    def _load_from_output_root(self, output_root: Path, original_file_path: Path = None):
        """Load processing steps from Director output root folder

        Args:
            output_root: Path to Director output folder root
            original_file_path: Optional original file path to highlight current step
        """
        try:
            logger.info(f"📊 Loading outputs from: {output_root}")

            # Load Director outputs
            self.output_session = self.outputs_manager.load_output_folder(output_root)
            all_steps = self.outputs_manager.list_tools(self.output_session)

            # Filter out build_documents_manifest step
            self.processing_steps = [step for step in all_steps if step.tool_name != "build_documents_manifest"]

            # Add "Original" step at the beginning with the source file
            if original_file_path and original_file_path.exists():
                from fichero.library.outputs_manager import ToolOutput
                original_step = ToolOutput(
                    tool_name="Original",
                    output_folder=original_file_path.parent,
                    manifest_path=original_file_path.parent / "original.jsonl"
                )
                # Manually set the files to just the original file
                original_step._files = [original_file_path]
                self.processing_steps.insert(0, original_step)

            if self.processing_steps:
                logger.info(f"📊 Found {len(self.processing_steps)} processing steps (including Original)")

                # Update step selector dropdown
                self._update_step_selector()

                # If we have an original file path, try to find matching step
                if original_file_path:
                    self.current_file_path = original_file_path
                    self._find_current_step(original_file_path)
                else:
                    # Default to first step with files
                    first_step_with_files = next((i for i, step in enumerate(self.processing_steps) if step.files), None)
                    if first_step_with_files is not None:
                        self.current_step_index = first_step_with_files
                        self.left_step_index = first_step_with_files
                        self.right_step_index = first_step_with_files
                        # Set current_file_path to first file in first step
                        self.current_file_path = Path(self.processing_steps[first_step_with_files].files[0])
                    else:
                        # No steps have files
                        logger.warning("No processing steps contain output files")
                        self.current_step_index = 0
                        self.left_step_index = 0
                        self.right_step_index = 0

                self._update_navigation()
                self._show_output_content()
                logger.info(f"✅ Successfully loaded {len(self.processing_steps)} processing steps")
            else:
                # Director output folder exists but no steps
                logger.info("No processing steps found in output folder")
                if original_file_path:
                    self._show_original_as_single_step(original_file_path)
                else:
                    self._show_error_message("No processing steps found in output folder")

        except Exception as e:
            logger.error(f"Error loading from output root: {e}")
            import traceback
            logger.error(traceback.format_exc())
            if original_file_path:
                logger.info("Falling back to showing original file")
                self._show_original_as_single_step(original_file_path)
            else:
                self._show_error_message(f"Failed to load outputs: {e}")

    def _find_output_root(self, file_path: Path) -> Optional[Path]:
        """Find Director output root folder"""
        try:
            current = file_path.parent

            # Walk up to find folder with 'assets' folder containing 'manifests'
            # Note: Director creates 'assets' and 'logs' but NOT 'documents'
            for _ in range(5):
                if (current / 'assets').exists():
                    if (current / 'assets' / 'manifests').exists():
                        logger.debug(f"Found Director output root: {current}")
                        return current

                if current.parent == current:
                    break

                current = current.parent

            return None

        except Exception as e:
            logger.debug(f"Error finding output root: {e}")
            return None
    
    def _find_current_step(self, file_path: Path):
        """Find which step the file belongs to"""
        try:
            for i, step in enumerate(self.processing_steps):
                for step_file in step.files:
                    if Path(step_file).resolve() == file_path.resolve():
                        self.current_step_index = i
                        self.left_step_index = max(0, i - 1)  # Default: prev step on left
                        self.right_step_index = i  # Current step on right
                        return
            
            self.current_step_index = 0
        
        except Exception as e:
            logger.error(f"Error finding current step: {e}")
            self.current_step_index = 0
    
    def _update_navigation(self):
        """Update navigation buttons state"""
        try:
            if not self.processing_steps:
                return

            current_step = self.processing_steps[self.current_step_index]

            # Update bottom toolbar title to show step indicator (truncate tool name if needed)
            if hasattr(self, 'step_title') and self.step_title:
                tool_name = current_step.tool_name
                max_tool_length = 30
                if len(tool_name) > max_tool_length:
                    tool_name = tool_name[:max_tool_length-3] + "..."
                self.step_title.text = f"Step {self.current_step_index + 1}/{len(self.processing_steps)}: {tool_name}"

            # Show/hide step navigation buttons based on position (use display to remove from layout)
            has_prev_step = self.current_step_index > 0
            has_next_step = self.current_step_index < len(self.processing_steps) - 1

            self.prev_step_btn.style.display = "pack" if has_prev_step else "none"
            self.next_step_btn.style.display = "pack" if has_next_step else "none"

        except Exception as e:
            logger.error(f"Error updating navigation: {e}")
    
    async def _on_prev_file(self, widget):
        """Navigate to previous source file (keeping same step)"""
        try:
            logger.info(f"🔼 Previous File button pressed!")

            # Save current viewer state before navigating
            await self._save_viewer_state()

            # Navigate to previous source file
            if self.source_files and self.current_source_index > 0:
                self.current_source_index -= 1
                next_file = self.source_files[self.current_source_index]

                # Reload output for the new file, keeping the same step
                self.load_output(next_file, self.source_files, self.current_source_index)
                logger.info(f"Navigated to previous source file: {next_file.name}")

        except Exception as e:
            logger.error(f"Error navigating to previous file: {e}")

    async def _on_next_file(self, widget):
        """Navigate to next source file (keeping same step)"""
        try:
            logger.info(f"🔽 Next File button pressed!")

            # Save current viewer state before navigating
            await self._save_viewer_state()

            # Navigate to next source file
            if self.source_files and self.current_source_index < len(self.source_files) - 1:
                self.current_source_index += 1
                next_file = self.source_files[self.current_source_index]

                # Reload output for the new file, keeping the same step
                self.load_output(next_file, self.source_files, self.current_source_index)
                logger.info(f"Navigated to next source file: {next_file.name}")

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
            self.prev_file_btn.style.display = "pack" if has_prev else "none"
            self.next_file_btn.style.display = "pack" if has_next else "none"

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

    async def _on_zoom_fit(self, widget):
        """Fit image to window"""
        try:
            if hasattr(self, 'current_webview') and self.current_webview:
                await self.current_webview.evaluate_javascript("fitToWindow();")
                logger.debug("Zoom: fit to window")
        except Exception as e:
            logger.error(f"Error fitting image: {e}")

    async def _on_zoom_fit_width(self, widget):
        """Fit image width to window"""
        try:
            if hasattr(self, 'current_webview') and self.current_webview:
                await self.current_webview.evaluate_javascript("fitToWidth();")
                logger.debug("Zoom: fit to width")
        except Exception as e:
            logger.error(f"Error fitting to width: {e}")

    async def _on_zoom_fit_height(self, widget):
        """Fit image height to window"""
        try:
            if hasattr(self, 'current_webview') and self.current_webview:
                await self.current_webview.evaluate_javascript("fitToHeight();")
                logger.debug("Zoom: fit to height")
        except Exception as e:
            logger.error(f"Error fitting to height: {e}")

    async def _on_zoom_100(self, widget):
        """Set image to actual size (100%)"""
        try:
            if hasattr(self, 'current_webview') and self.current_webview:
                await self.current_webview.evaluate_javascript("actualSize();")
                logger.debug("Zoom: 100%")
        except Exception as e:
            logger.error(f"Error setting actual size: {e}")

    async def _on_zoom_in(self, widget):
        """Zoom in"""
        try:
            if hasattr(self, 'current_webview') and self.current_webview:
                await self.current_webview.evaluate_javascript("zoomIn();")
                logger.debug("Zoom: in")
        except Exception as e:
            logger.error(f"Error zooming in: {e}")

    async def _on_zoom_out(self, widget):
        """Zoom out"""
        try:
            if hasattr(self, 'current_webview') and self.current_webview:
                await self.current_webview.evaluate_javascript("zoomOut();")
                logger.debug("Zoom: out")
        except Exception as e:
            logger.error(f"Error zooming out: {e}")

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

    def _show_zoom_controls(self, show: bool):
        """Show or hide zoom and rotation control buttons"""
        try:
            display = "pack" if show else "none"
            self.zoom_out_btn.style.display = display
            self.zoom_fit_btn.style.display = display
            self.zoom_fit_width_btn.style.display = display
            self.zoom_fit_height_btn.style.display = display
            self.zoom_100_btn.style.display = display
            self.zoom_in_btn.style.display = display
            self.rotate_left_btn.style.display = display
            self.rotate_right_btn.style.display = display
            logger.debug(f"Image controls: {'shown' if show else 'hidden'}")
        except Exception as e:
            logger.error(f"Error toggling image controls: {e}")

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
        """Create appropriate viewer widget based on file type - always in-app, no external viewers"""
        suffix = file_path.suffix.lower()

        # Try WebView first for most formats (HTML wrapper approach)
        # This gives us maximum flexibility and consistency
        try:
            # Image formats - wrap in HTML for better display control
            if suffix in ['.jpg', '.jpeg', '.png', '.tiff', '.tif', '.gif', '.bmp', '.webp']:
                viewer = self._create_webview_image_viewer(file_path)
                self._show_zoom_controls(True)  # Show zoom controls for images
                return viewer

            # HTML files - direct WebView
            elif suffix in ['.html', '.htm']:
                self._show_zoom_controls(False)  # Hide zoom controls
                return self._create_webview_direct(file_path)

            # PDF - WebView with PDF.js or native PDF support
            elif suffix == '.pdf':
                self._show_zoom_controls(False)  # Hide zoom controls
                return self._create_webview_pdf_viewer(file_path)

            # Text-based formats - wrap in HTML for syntax highlighting
            elif suffix in ['.txt', '.md', '.log', '.csv', '.xml', '.json']:
                self._show_zoom_controls(False)  # Hide zoom controls
                return self._create_webview_text_viewer(file_path)

            # Office documents - convert to HTML
            elif suffix in ['.docx', '.doc']:
                self._show_zoom_controls(False)  # Hide zoom controls
                return self._create_webview_docx_viewer(file_path)

            # Fallback - show as text in HTML
            else:
                self._show_zoom_controls(False)  # Hide zoom controls
                return self._create_webview_text_viewer(file_path)

        except Exception as e:
            logger.error(f"Error creating viewer: {e}")
            self._show_zoom_controls(False)  # Hide zoom controls on error
            # Ultimate fallback - show error message
            return toga.Label(f"Error loading file: {e}", style=Pack(margin=20))

    def _create_webview_image_viewer(self, file_path: Path):
        """Create WebView-based image viewer - controls via toolbar buttons"""
        import base64

        try:
            # Read image and encode as base64
            with open(file_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')

            # Determine MIME type
            mime_types = {
                '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.png': 'image/png', '.gif': 'image/gif',
                '.bmp': 'image/bmp', '.webp': 'image/webp',
                '.tiff': 'image/tiff', '.tif': 'image/tiff'
            }
            mime_type = mime_types.get(file_path.suffix.lower(), 'image/jpeg')

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
                </style>
            </head>
            <body>
                <div id="imageContainer">
                    <div id="imageWrapper">
                        <img id="image" src="data:{mime_type};base64,{image_data}" alt="{file_path.name}">
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
                    let startX, startY, scrollLeft, scrollTop;

                    const img = document.getElementById('image');
                    const container = document.getElementById('imageContainer');
                    const wrapper = document.getElementById('imageWrapper');
                    const minimap = document.getElementById('minimap');
                    const minimapCanvas = document.getElementById('minimapCanvas');
                    const minimapViewport = document.getElementById('minimapViewport');
                    const ctx = minimapCanvas.getContext('2d');

                    // Load image fitted to window by default
                    img.onload = function() {{
                        fitToWindow();
                        drawMinimap();
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

                    // Pan with mouse drag
                    container.addEventListener('mousedown', function(e) {{
                        isDragging = true;
                        container.classList.add('grabbing');
                        startX = e.pageX - container.offsetLeft;
                        startY = e.pageY - container.offsetTop;
                        scrollLeft = container.scrollLeft;
                        scrollTop = container.scrollTop;
                    }});

                    container.addEventListener('mouseleave', function() {{
                        isDragging = false;
                        container.classList.remove('grabbing');
                    }});

                    container.addEventListener('mouseup', function() {{
                        isDragging = false;
                        container.classList.remove('grabbing');
                    }});

                    container.addEventListener('mousemove', function(e) {{
                        if (!isDragging) return;
                        e.preventDefault();
                        const x = e.pageX - container.offsetLeft;
                        const y = e.pageY - container.offsetTop;
                        const walkX = (x - startX);
                        const walkY = (y - startY);
                        container.scrollLeft = scrollLeft - walkX;
                        container.scrollTop = scrollTop - walkY;
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
        self.prev_file_btn.style.display = "none"
        self.next_file_btn.style.display = "none"

        # Update bottom toolbar title to show "Step 1/1: Original"
        if hasattr(self, 'step_title') and self.step_title:
            self.step_title.text = "Step 1/1: Original"

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

        except Exception as e:
            logger.error(f"Failed to handle step selection: {e}")
