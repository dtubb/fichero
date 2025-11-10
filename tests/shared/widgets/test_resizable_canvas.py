"""
Unit tests for ResizableCanvas widget.

Tests drag handle creation and state management.
"""

import unittest
from unittest.mock import Mock

from src.fichero.shared.widgets import ResizableCanvas, Orientation, create_resize_handle


class TestResizableCanvas(unittest.TestCase):
    """Test ResizableCanvas drag handle widget."""

    def test_horizontal_orientation(self):
        """Test creating a horizontal drag handle (vertical divider)."""
        handle = ResizableCanvas(orientation=Orientation.HORIZONTAL)

        self.assertEqual(handle.orientation, Orientation.HORIZONTAL)
        self.assertIsNotNone(handle.widget)
        self.assertFalse(handle.is_dragging)

    def test_vertical_orientation(self):
        """Test creating a vertical drag handle (horizontal divider)."""
        handle = ResizableCanvas(orientation=Orientation.VERTICAL)

        self.assertEqual(handle.orientation, Orientation.VERTICAL)
        self.assertIsNotNone(handle.widget)
        self.assertFalse(handle.is_dragging)

    def test_default_orientation(self):
        """Test default orientation is HORIZONTAL."""
        handle = ResizableCanvas()

        self.assertEqual(handle.orientation, Orientation.HORIZONTAL)

    def test_resize_callback(self):
        """Test that resize callback is stored."""
        callback = Mock()
        handle = ResizableCanvas(on_resize=callback)

        self.assertEqual(handle.on_resize, callback)

    def test_min_size_configuration(self):
        """Test configuring minimum size."""
        handle = ResizableCanvas(min_size=200)

        self.assertEqual(handle.min_size, 200)

    def test_set_hover_state(self):
        """Test setting hover state changes color."""
        handle = ResizableCanvas()

        # Set hover
        handle.set_hover(True)
        self.assertEqual(
            handle.widget.style.background_color,
            ResizableCanvas.HANDLE_HOVER_COLOR
        )

        # Clear hover
        handle.set_hover(False)
        self.assertEqual(
            handle.widget.style.background_color,
            ResizableCanvas.HANDLE_COLOR
        )

    def test_set_active_state(self):
        """Test setting active/dragging state."""
        handle = ResizableCanvas()

        # Set active
        handle.set_active(True)
        self.assertTrue(handle.is_dragging)
        self.assertEqual(
            handle.widget.style.background_color,
            ResizableCanvas.HANDLE_ACTIVE_COLOR
        )

        # Clear active
        handle.set_active(False)
        self.assertFalse(handle.is_dragging)
        self.assertEqual(
            handle.widget.style.background_color,
            ResizableCanvas.HANDLE_COLOR
        )

    def test_start_drag(self):
        """Test starting a drag operation."""
        handle = ResizableCanvas()

        handle.start_drag(100, 200)

        self.assertTrue(handle.is_dragging)
        self.assertEqual(handle._drag_start_pos, (100, 200))
        self.assertEqual(
            handle.widget.style.background_color,
            ResizableCanvas.HANDLE_ACTIVE_COLOR
        )

    def test_end_drag(self):
        """Test ending a drag operation."""
        handle = ResizableCanvas()

        # Start drag first
        handle.start_drag(100, 200)
        self.assertTrue(handle.is_dragging)

        # End drag
        handle.end_drag()

        self.assertFalse(handle.is_dragging)
        self.assertIsNone(handle._drag_start_pos)
        self.assertEqual(
            handle.widget.style.background_color,
            ResizableCanvas.HANDLE_COLOR
        )

    def test_update_drag_horizontal(self):
        """Test updating drag with horizontal movement."""
        callback = Mock()
        handle = ResizableCanvas(
            orientation=Orientation.HORIZONTAL,
            on_resize=callback
        )

        # Start drag
        handle.start_drag(100, 200)

        # Move 50 pixels right
        handle.update_drag(150, 200)

        # Callback should be called with delta of 50
        callback.assert_called_once_with(50)

    def test_update_drag_vertical(self):
        """Test updating drag with vertical movement."""
        callback = Mock()
        handle = ResizableCanvas(
            orientation=Orientation.VERTICAL,
            on_resize=callback
        )

        # Start drag
        handle.start_drag(100, 200)

        # Move 30 pixels down
        handle.update_drag(100, 230)

        # Callback should be called with delta of 30
        callback.assert_called_once_with(30)

    def test_update_drag_no_op_when_not_dragging(self):
        """Test that update_drag does nothing when not dragging."""
        callback = Mock()
        handle = ResizableCanvas(on_resize=callback)

        # Update without starting drag
        handle.update_drag(150, 200)

        # Callback should not be called
        callback.assert_not_called()

    def test_impl_property(self):
        """Test that impl property returns the widget."""
        handle = ResizableCanvas()

        self.assertEqual(handle.impl, handle.widget)


class TestCreateResizeHandle(unittest.TestCase):
    """Test convenience function for creating resize handles."""

    def test_create_resize_handle_default(self):
        """Test creating handle with default orientation."""
        handle = create_resize_handle()

        self.assertIsInstance(handle, ResizableCanvas)
        self.assertEqual(handle.orientation, Orientation.HORIZONTAL)

    def test_create_resize_handle_vertical(self):
        """Test creating vertical handle."""
        handle = create_resize_handle(orientation=Orientation.VERTICAL)

        self.assertIsInstance(handle, ResizableCanvas)
        self.assertEqual(handle.orientation, Orientation.VERTICAL)

    def test_create_resize_handle_with_callback(self):
        """Test creating handle with resize callback."""
        callback = Mock()
        handle = create_resize_handle(on_resize=callback)

        self.assertEqual(handle.on_resize, callback)


if __name__ == '__main__':
    unittest.main()
