"""
StepBrowser - Component for displaying processing steps in OutputView

PHASE 4: Shows the list of processing steps (tools) for a file.
The first step is always the "Original" file, followed by each tool's output.
Allows navigation between steps (Original -> transcribe -> enhance -> etc.)
"""

import logging
from typing import Optional, List, Callable

import toga
from toga.style import Pack

from .step_manager import Step
from fichero.shared.widgets.list_widget import ListWidget

logger = logging.getLogger(__name__)


class StepBrowser:
    """
    Step browser component for OutputView (PHASE 4).

    Displays the list of processing steps for the current file.
    - First item: "Original" (the source file)
    - Subsequent items: Each tool/step (transcribe, enhance, etc.)

    Example:
        browser = StepBrowser(on_step_selected=self._handle_step_selection)
        browser.load_steps(steps, current_index=0)
        container.add(browser.as_box())
    """

    def __init__(self, on_step_selected: Optional[Callable] = None):
        """
        Initialize step browser.

        Args:
            on_step_selected: Callback when step is selected (receives step index)
        """
        self.on_step_selected = on_step_selected
        self.logger = logging.getLogger(__name__)

        # Current state
        self.steps: List[Step] = []
        self.current_index: int = 0

        # UI components
        self._container = None
        self._step_list = None
        self._empty_label = None

        self._build_ui()

    def _build_ui(self):
        """Build UI components"""
        # Main container - no margin, extends to edges (Finder-style)
        self._container = toga.Box(
            style=Pack(
                direction='column',
                flex=1,
                margin=0  # Remove all margins - extends to top/bottom/left/right
            )
        )

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

        # Show empty state initially
        self._container.add(self._empty_label)

    def load_steps(self, steps: List[Step], current_index: int = 0):
        """
        Load steps into browser.

        Args:
            steps: List of Step objects to display
            current_index: Index of currently selected step
        """
        self.logger.info(f"StepBrowser: Loading {len(steps)} steps, current_index={current_index}")

        self.steps = steps
        self.current_index = current_index

        # Clear container
        self._container.clear()

        if not steps:
            # Show empty state
            self._container.add(self._empty_label)
            return

        # Create data for ListWidget
        # The first step is the "Original" file, followed by tool outputs
        list_data = []

        for i, step in enumerate(steps):
            # Determine display name
            if i == 0:
                # First step is the original file
                title = "Original"
                subtitle = step.file_type
                icon_name = self._get_icon_for_file_type(step.file_type)
            else:
                # Subsequent steps are tool outputs
                title = step.step_name
                subtitle = step.file_type
                icon_name = self._get_icon_for_tool(step.tool_name)

            list_data.append({
                'text': title,  # ListWidget uses 'text' for primary content
                'subtitle': subtitle,
                'icon': toga.Icon(icon_name) if icon_name else None,
                '_item_id': i  # Store index for callback
            })

        # Create or recreate step list using ListWidget with native renderer
        # Force 'table' for now - Tree icons have issues with non-Icon values
        self._step_list = ListWidget(
            headings=['Steps'],  # Single column for steps
            data=list_data,
            on_select=self._on_step_selected,
            renderer='native',  # Use native Table/DetailedList
            force_widget_type='table',  # Force table - tree icons are problematic
            style=Pack(flex=1, margin_left=2)  # Small left margin so focus ring is visible
        )

        # Add to container (ListWidget.widget is the actual toga widget)
        self._container.add(self._step_list.widget)

        # Note: We don't programmatically set selection as it's read-only in Toga
        # The selection will be set when user clicks, or we trigger the callback manually
        if 0 <= current_index < len(list_data):
            self.logger.debug(f"StepBrowser: Initial step index is {current_index}")
            # Trigger the selection callback manually to load the step
            if self.on_step_selected:
                self.on_step_selected(current_index)

    def _get_icon_for_file_type(self, file_type: str) -> Optional[str]:
        """Get icon resource path for a file type"""
        # Map file types to icon resources
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
        # Map tool names to icon resources
        icon_map = {
            'transcribe': 'resources/icons/toolbar/text.document@10x.png',
            'enhance': 'resources/icons/toolbar/wand.and.stars@10x.png',
            'catalogue': 'resources/icons/toolbar/list.bullet@10x.png',
            'convert_to_word': 'resources/icons/toolbar/document.png',
        }
        return icon_map.get(tool_name, 'resources/icons/toolbar/gear@10x.png')

    def _on_step_selected(self, widget_or_data, **kwargs):
        """Handle step selection"""
        try:
            # ListWidget can pass data as first arg (widget_or_data) or in kwargs
            selected_data = widget_or_data if isinstance(widget_or_data, dict) else kwargs.get('selected_data')

            if not selected_data:
                # Might be a widget - try to extract from selection attribute
                if hasattr(widget_or_data, 'selection'):
                    selection = widget_or_data.selection
                    if hasattr(selection, '_collection_data'):
                        selected_data = selection._collection_data
                    elif isinstance(selection, dict):
                        selected_data = selection

                if not selected_data:
                    self.logger.debug("StepBrowser: No selected_data in callback (probably deselection)")
                    return

            # Get the index from _item_id
            index = selected_data.get('_item_id')
            if index is None:
                self.logger.warning("StepBrowser: No _item_id in selected_data")
                return

            self.logger.info(f"StepBrowser: Step selected at index {index}")
            self.current_index = index

            # Notify callback
            if self.on_step_selected:
                self.on_step_selected(index)

        except Exception as e:
            self.logger.error(f"Error handling step selection: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

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
            # Note: selection is read-only in Toga, so we just update our internal state
            # and trigger the callback
            self.logger.debug(f"StepBrowser: Updated current index to {index}")
            if self.on_step_selected:
                self.on_step_selected(index)

    def clear(self):
        """Clear the step browser"""
        self.steps = []
        self.current_index = 0
        self._container.clear()
        self._container.add(self._empty_label)
        self.logger.debug("StepBrowser: Cleared")

    def as_box(self) -> toga.Box:
        """
        Get container for embedding.

        Returns:
            Container box
        """
        return self._container
