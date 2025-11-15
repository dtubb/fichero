"""
StepView - Processing steps browser view.

Extracted from OutputView (Phase 2.1) as a standalone view that implements BaseViewInterface.
Shows the list of processing steps for a file (Original -> tool outputs).
"""

import logging
from typing import Optional, List, Callable, Dict, Any
from pathlib import Path

import toga
from toga.style import Pack

from fichero.shared.views.base_view_interface import BaseViewInterface
from fichero.shared.views.view_types import ViewType
from fichero.shared.focus import FocusBorder
from fichero.shared.widgets.list_widget import ListWidget


logger = logging.getLogger(__name__)


class StepView(BaseViewInterface):
    """
    Processing steps browser view (Phase 2.1).

    Displays the list of processing steps for the current file:
    - First item: "Original" (the source file)
    - Subsequent items: Each tool/step (transcribe, enhance, etc.)

    Implements BaseViewInterface for universal navigation system.

    Example:
        step_view = StepView(view_id="step-1")
        step_view.load_steps(steps, current_index=0)
        step_view.on_step_selected = lambda index: handle_step_change(index)
        main_container.add(step_view.container)
    """

    def __init__(
        self,
        view_id: str,
        on_step_selected: Optional[Callable[[int], None]] = None
    ):
        """
        Initialize step view.

        Args:
            view_id: Unique identifier for this view instance
            on_step_selected: Callback when step is selected (receives step index)
        """
        self._view_id = view_id
        self.on_step_selected = on_step_selected
        self.logger = logging.getLogger(__name__)

        # Current state
        self.steps: List[Dict[str, Any]] = []  # List of step data dicts
        self.current_index: int = 0

        # UI components
        self._container = None
        self._inner_container = None
        self._step_list = None
        self._empty_label = None
        self._focus_border = None

        self._build_ui()

    # ==================== BaseViewInterface Implementation ====================

    @property
    def view_id(self) -> str:
        """Unique identifier for this view instance."""
        return self._view_id

    @property
    def view_type(self) -> ViewType:
        """Type of view (STEP)"""
        return ViewType.STEP

    @property
    def container(self) -> toga.Box:
        """The root container widget for this view."""
        return self._container

    @property
    def is_focused(self) -> bool:
        """Whether this view currently has focus."""
        return self._focus_border.is_focused if self._focus_border else False

    def set_focused(self, focused: bool):
        """Update focus state and visual indicator."""
        if self._focus_border:
            self._focus_border.set_focused(focused)
            self.logger.debug(f"StepView {self.view_id}: Focus set to {focused}")

    def get_state(self) -> Dict[str, Any]:
        """
        Return current state for persistence.

        Returns:
            Dictionary with:
                - current_index: Currently selected step index
                - total_steps: Total number of steps
                - step_names: List of step names (for debugging)
        """
        return {
            'view_id': self.view_id,
            'view_type': self.view_type.value,
            'current_index': self.current_index,
            'total_steps': len(self.steps),
            'step_names': [step.get('step_name', 'Unknown') for step in self.steps]
        }

    def restore_state(self, state: Dict[str, Any]):
        """
        Restore view from saved state.

        Args:
            state: State dict from get_state()
        """
        if not state:
            return

        # Restore selection index
        saved_index = state.get('current_index', 0)
        if 0 <= saved_index < len(self.steps):
            self.set_current_index(saved_index)
            self.logger.info(f"StepView {self.view_id}: Restored state with index={saved_index}")

    # ==================== UI Construction ====================

    def _build_ui(self):
        """Build UI components"""
        # Outer container - has focus border
        self._container = toga.Box(
            style=Pack(
                direction='column',
                flex=1,
                margin=0
            )
        )

        # Inner container - no margin, extends to edges (Finder-style)
        self._inner_container = toga.Box(
            style=Pack(
                direction='column',
                flex=1,
                margin=0
            )
        )

        # Initialize focus border on outer container
        self._focus_border = FocusBorder(self._container)

        # Empty state label
        self._empty_label = toga.Label(
            "No steps",
            style=Pack(
                text_align='center',
                margin=20,
                font_size=12,
                color='#999999'
            )
        )

        # Add inner container to outer container
        self._container.add(self._inner_container)

        # Show empty state initially
        self._inner_container.add(self._empty_label)

    # ==================== Step Management ====================

    def load_steps(self, steps: List[Dict[str, Any]], current_index: int = 0):
        """
        Load steps into view.

        Args:
            steps: List of step data dictionaries with keys:
                - step_name: Display name (e.g., "Original", "transcribe")
                - tool_name: Internal tool name
                - file_type: Type of file (image, text, json, etc.)
                - file_path: Path to step output file
                Additional keys are preserved for event callbacks
            current_index: Index of currently selected step
        """
        self.logger.info(f"StepView {self.view_id}: Loading {len(steps)} steps, current_index={current_index}")

        self.steps = steps
        self.current_index = current_index

        # Clear inner container
        self._inner_container.clear()

        if not steps:
            # Show empty state
            self._inner_container.add(self._empty_label)
            return

        # Create data for ListWidget
        list_data = []

        for i, step in enumerate(steps):
            # Extract step information
            step_name = step.get('step_name', 'Unknown')
            file_type = step.get('file_type', 'unknown')
            tool_name = step.get('tool_name', 'unknown')

            # Determine display name and icon
            if i == 0 or step_name == 'Original':
                # First step is the original file
                title = "Original"
                subtitle = file_type
                icon_name = self._get_icon_for_file_type(file_type)
            else:
                # Subsequent steps are tool outputs
                title = step_name
                subtitle = file_type
                icon_name = self._get_icon_for_tool(tool_name)

            # Create icon object, but handle case where no Toga app exists (testing)
            icon = None
            if icon_name:
                try:
                    icon = toga.Icon(icon_name)
                except (AttributeError, RuntimeError):
                    # No Toga app available (e.g., during testing) - skip icon
                    pass

            list_data.append({
                'text': title,
                'subtitle': subtitle,
                'icon': icon,
                '_item_id': i,  # Store index for callback
                '_step_data': step  # Store full step data for event
            })

        # Create step list using ListWidget with native renderer
        self._step_list = ListWidget(
            headings=['Steps'],
            data=list_data,
            on_select=self._on_step_selected,
            renderer='native',
            force_widget_type='table',
            style=Pack(flex=1, margin_left=2)
        )

        # Add to inner container
        self._inner_container.add(self._step_list.widget)

        # Trigger initial selection callback if within range
        if 0 <= current_index < len(list_data):
            self.logger.debug(f"StepView {self.view_id}: Initial step index is {current_index}")
            if self.on_step_selected:
                self.on_step_selected(current_index)

    def _get_icon_for_file_type(self, file_type: str) -> Optional[str]:
        """Get icon resource path for a file type"""
        icon_map = {
            'image': 'resources/icons/toolbar/document@10x.png',
            'text': 'resources/icons/toolbar/text.document@10x.png',
            'document': 'resources/icons/toolbar/document.png',
            'json': 'resources/icons/toolbar/text.document@10x.png',
            'folder': 'resources/icons/toolbar/folder@10x.png',
        }
        return icon_map.get(file_type, 'resources/icons/toolbar/document.png')

    def _get_icon_for_tool(self, tool_name: str) -> Optional[str]:
        """Get icon resource path for a tool"""
        icon_map = {
            'transcribe': 'resources/icons/toolbar/text.document@10x.png',
            'enhance': 'resources/icons/toolbar/wand.and.stars@10x.png',
            'catalogue': 'resources/icons/toolbar/list.bullet@10x.png',
            'convert_to_word': 'resources/icons/toolbar/document.png',
        }
        return icon_map.get(tool_name, 'resources/icons/toolbar/gear@10x.png')

    def _on_step_selected(self, widget, **kwargs):
        """Handle step selection (internal callback from ListWidget)"""
        try:
            # ListWidget passes the selected item data in kwargs
            selected_data = kwargs.get('selected_data')
            if not selected_data:
                self.logger.warning(f"StepView {self.view_id}: No selected_data in callback")
                return

            # Get the index from _item_id
            index = selected_data.get('_item_id')
            if index is None:
                self.logger.warning(f"StepView {self.view_id}: No _item_id in selected_data")
                return

            self.logger.info(f"StepView {self.view_id}: Step selected at index {index}")
            self.current_index = index

            # Notify external callback
            if self.on_step_selected:
                self.on_step_selected(index)

        except Exception as e:
            self.logger.error(f"Error handling step selection: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

    # ==================== Public Methods ====================

    def set_current_index(self, index: int):
        """
        Update the selected step by index.

        Args:
            index: Index to select
        """
        if not self._step_list:
            return

        if 0 <= index < len(self.steps):
            self.current_index = index
            # Note: selection is read-only in Toga, so we just update internal state
            # and trigger the callback
            self.logger.debug(f"StepView {self.view_id}: Updated current index to {index}")
            if self.on_step_selected:
                self.on_step_selected(index)

    def clear(self):
        """Clear the step view"""
        self.steps = []
        self.current_index = 0
        self._inner_container.clear()
        self._inner_container.add(self._empty_label)
        self.logger.debug(f"StepView {self.view_id}: Cleared")

    def get_current_step(self) -> Optional[Dict[str, Any]]:
        """
        Get currently selected step data.

        Returns:
            Step data dict or None if no steps
        """
        if 0 <= self.current_index < len(self.steps):
            return self.steps[self.current_index]
        return None


__all__ = ['StepView']
