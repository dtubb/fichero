"""
Resizable canvas with draggable handles for pane splitting.

Provides visual handles that can be dragged to resize panes in both
horizontal and vertical orientations.
"""

import logging
from enum import Enum
from typing import Optional, Callable

import toga
from toga.style.pack import Pack
from toga.colors import rgb


logger = logging.getLogger(__name__)


class Orientation(Enum):
    """Orientation for resize handles."""
    HORIZONTAL = "horizontal"  # Vertical divider, horizontal drag
    VERTICAL = "vertical"  # Horizontal divider, vertical drag


class ResizableCanvas:
    """
    A draggable resize handle for splitting panes.

    Creates a visual divider between two panes that can be dragged to
    adjust their relative sizes. Supports both horizontal and vertical
    orientations.

    Example:
        # Create a vertical divider (horizontal drag)
        handle = ResizableCanvas(
            orientation=Orientation.HORIZONTAL,
            on_resize=lambda delta: adjust_pane_sizes(delta)
        )

        # Add to layout between panes
        container.add(left_pane)
        container.add(handle.widget)
        container.add(right_pane)
    """

    # Visual constants
    HANDLE_SIZE = 6  # Width/height of the handle in pixels
    HANDLE_COLOR = rgb(180, 180, 180)  # Light gray
    HANDLE_HOVER_COLOR = rgb(100, 149, 237)  # Cornflower blue
    HANDLE_ACTIVE_COLOR = rgb(65, 105, 225)  # Royal blue

    def __init__(
        self,
        orientation: Orientation = Orientation.HORIZONTAL,
        on_resize: Optional[Callable[[int], None]] = None,
        min_size: int = 100,
        style: Optional[Pack] = None,
    ):
        """
        Initialize the resizable canvas.

        Args:
            orientation: HORIZONTAL (vertical divider) or VERTICAL (horizontal divider)
            on_resize: Callback when handle is dragged (receives delta in pixels)
            min_size: Minimum size for panes in pixels
            style: Optional Toga Pack style for the handle
        """
        self.orientation = orientation
        self.on_resize = on_resize
        self.min_size = min_size

        # Drag state
        self._is_dragging = False
        self._drag_start_pos = None

        # Create the handle widget
        self.widget = self._create_handle(style)

        logger.debug(f"ResizableCanvas created with {orientation.value} orientation")

    def _create_handle(self, style: Optional[Pack] = None) -> toga.Box:
        """
        Create the visual handle widget.

        Note: In Toga 0.5.2, we don't have full mouse event support for Canvas.
        As a temporary solution, we create a colored Box as a visual divider.
        Full drag functionality will be implemented when Toga adds better
        mouse event handling (expected in future versions).

        For now, this creates a static divider that shows where panes split.
        """
        if style is None:
            if self.orientation == Orientation.HORIZONTAL:
                # Vertical divider (narrow width, full height)
                style = Pack(
                    width=self.HANDLE_SIZE,
                    background_color=self.HANDLE_COLOR,
                )
            else:
                # Horizontal divider (full width, narrow height)
                style = Pack(
                    height=self.HANDLE_SIZE,
                    background_color=self.HANDLE_COLOR,
                )

        handle_box = toga.Box(style=style)

        # TODO: Add mouse event handlers when Toga supports them
        # For now, this is a static visual divider
        # Future implementation will add:
        # - on_mouse_enter: Change to HANDLE_HOVER_COLOR
        # - on_mouse_leave: Change back to HANDLE_COLOR
        # - on_mouse_down: Set _is_dragging, store _drag_start_pos
        # - on_mouse_move: Calculate delta, call on_resize callback
        # - on_mouse_up: Clear _is_dragging

        return handle_box

    def set_hover(self, is_hover: bool) -> None:
        """
        Set hover state (for future use).

        Args:
            is_hover: True if mouse is hovering over handle
        """
        if is_hover:
            self.widget.style.background_color = self.HANDLE_HOVER_COLOR
        else:
            self.widget.style.background_color = self.HANDLE_COLOR

    def set_active(self, is_active: bool) -> None:
        """
        Set active/dragging state.

        Args:
            is_active: True if handle is being dragged
        """
        self._is_dragging = is_active

        if is_active:
            self.widget.style.background_color = self.HANDLE_ACTIVE_COLOR
        else:
            self.widget.style.background_color = self.HANDLE_COLOR

    def start_drag(self, x: int, y: int) -> None:
        """
        Start a drag operation.

        Args:
            x: Mouse X position
            y: Mouse Y position
        """
        self._is_dragging = True
        self._drag_start_pos = (x, y)
        self.set_active(True)
        logger.debug(f"Drag started at ({x}, {y})")

    def update_drag(self, x: int, y: int) -> None:
        """
        Update drag position and call resize callback.

        Args:
            x: Current mouse X position
            y: Current mouse Y position
        """
        if not self._is_dragging or not self._drag_start_pos:
            return

        start_x, start_y = self._drag_start_pos

        if self.orientation == Orientation.HORIZONTAL:
            # Horizontal drag (vertical divider)
            delta = x - start_x
        else:
            # Vertical drag (horizontal divider)
            delta = y - start_y

        # Call resize callback with delta
        if self.on_resize and abs(delta) > 0:
            self.on_resize(delta)

        # Update start position for next delta calculation
        self._drag_start_pos = (x, y)

    def end_drag(self) -> None:
        """End the current drag operation."""
        self._is_dragging = False
        self._drag_start_pos = None
        self.set_active(False)
        logger.debug("Drag ended")

    @property
    def is_dragging(self) -> bool:
        """Check if handle is currently being dragged."""
        return self._is_dragging

    @property
    def impl(self) -> toga.Box:
        """Get the underlying Toga widget implementation."""
        return self.widget


# Convenience function for creating resize handles
def create_resize_handle(
    orientation: Orientation = Orientation.HORIZONTAL,
    on_resize: Optional[Callable[[int], None]] = None,
) -> ResizableCanvas:
    """
    Create a resize handle with default settings.

    Args:
        orientation: HORIZONTAL (vertical divider) or VERTICAL (horizontal divider)
        on_resize: Callback when handle is dragged (receives delta in pixels)

    Returns:
        ResizableCanvas instance
    """
    return ResizableCanvas(orientation=orientation, on_resize=on_resize)
