"""
Unit tests for FocusBorder - Universal focus indicator.

Tests the focus border visual indicator system that's used across
all views in the universal navigation system.
"""

import unittest
import toga
from toga.style import Pack
from toga.colors import rgb

from fichero.shared.focus.focus_border import FocusBorder


class TestFocusBorder(unittest.TestCase):
    """Test FocusBorder class"""

    def setUp(self):
        """Set up test fixtures"""
        self.container = toga.Box(style=Pack(direction='column'))
        self.focus_border = FocusBorder(self.container)

    def test_initial_state_unfocused(self):
        """Test focus border starts unfocused"""
        self.assertFalse(self.focus_border.is_focused)

    def test_set_focused_true_applies_border(self):
        """Test set_focused(True) applies border"""
        self.focus_border.set_focused(True)

        self.assertTrue(self.focus_border.is_focused)
        # Toga returns margin as tuple (top, right, bottom, left)
        expected_margin = (FocusBorder.DEFAULT_BORDER_WIDTH,) * 4
        self.assertEqual(self.container.style.margin, expected_margin)
        self.assertIsNotNone(self.container.style.background_color)

    def test_set_focused_false_removes_border(self):
        """Test set_focused(False) removes border"""
        # First apply focus
        self.focus_border.set_focused(True)
        self.assertTrue(self.focus_border.is_focused)

        # Then remove it
        self.focus_border.set_focused(False)

        self.assertFalse(self.focus_border.is_focused)
        # Toga returns margin as tuple even when 0
        self.assertEqual(self.container.style.margin, (0, 0, 0, 0))

    def test_default_focus_color(self):
        """Test default focus color is VSCode blue"""
        self.focus_border.set_focused(True)

        # Default color should be VSCode blue: rgb(0, 122, 204)
        self.assertEqual(self.container.style.background_color, rgb(0, 122, 204))

    def test_custom_focus_color(self):
        """Test custom focus color can be set"""
        custom_color = rgb(255, 0, 0)  # Red
        focus_border = FocusBorder(self.container, color=custom_color)

        focus_border.set_focused(True)

        self.assertEqual(self.container.style.background_color, custom_color)

    def test_custom_border_width(self):
        """Test custom border width can be set"""
        custom_width = 5
        focus_border = FocusBorder(self.container, border_width=custom_width)

        focus_border.set_focused(True)

        self.assertEqual(self.container.style.margin, (custom_width,) * 4)

    def test_toggle_focus(self):
        """Test toggle() switches focus state"""
        # Start unfocused
        self.assertFalse(self.focus_border.is_focused)

        # Toggle to focused
        self.focus_border.toggle()
        self.assertTrue(self.focus_border.is_focused)

        # Toggle back to unfocused
        self.focus_border.toggle()
        self.assertFalse(self.focus_border.is_focused)

    def test_set_focused_idempotent(self):
        """Test set_focused is idempotent (no change if already in state)"""
        # Set focused
        self.focus_border.set_focused(True)
        margin_after_first = self.container.style.margin

        # Set focused again (should be no-op)
        self.focus_border.set_focused(True)
        margin_after_second = self.container.style.margin

        self.assertEqual(margin_after_first, margin_after_second)

    def test_multiple_focus_unfocus_cycles(self):
        """Test multiple focus/unfocus cycles work correctly"""
        for i in range(5):
            # Focus
            self.focus_border.set_focused(True)
            self.assertTrue(self.focus_border.is_focused)
            self.assertEqual(self.container.style.margin, (FocusBorder.DEFAULT_BORDER_WIDTH,) * 4)

            # Unfocus
            self.focus_border.set_focused(False)
            self.assertFalse(self.focus_border.is_focused)
            self.assertEqual(self.container.style.margin, (0, 0, 0, 0))


class TestFocusBorderEdgeCases(unittest.TestCase):
    """Test edge cases and error handling"""

    def test_multiple_containers_independent(self):
        """Test multiple FocusBorder instances are independent"""
        container1 = toga.Box(style=Pack(direction='column'))
        container2 = toga.Box(style=Pack(direction='column'))

        focus1 = FocusBorder(container1)
        focus2 = FocusBorder(container2)

        # Focus first container
        focus1.set_focused(True)

        # Check states are independent
        self.assertTrue(focus1.is_focused)
        self.assertFalse(focus2.is_focused)
        self.assertEqual(container1.style.margin, (FocusBorder.DEFAULT_BORDER_WIDTH,) * 4)
        self.assertEqual(container2.style.margin, (0, 0, 0, 0))

    def test_zero_border_width(self):
        """Test border width of 0 (edge case)"""
        focus_border = FocusBorder(self.container, border_width=0)

        focus_border.set_focused(True)

        # Even with 0 width, background color should be set
        self.assertTrue(focus_border.is_focused)
        self.assertEqual(self.container.style.margin, (0, 0, 0, 0))
        self.assertIsNotNone(self.container.style.background_color)

    def test_large_border_width(self):
        """Test very large border width"""
        large_width = 100
        focus_border = FocusBorder(self.container, border_width=large_width)

        focus_border.set_focused(True)

        self.assertEqual(self.container.style.margin, (large_width,) * 4)

    def setUp(self):
        """Set up test fixtures"""
        self.container = toga.Box(style=Pack(direction='column'))


class TestFocusBorderImport(unittest.TestCase):
    """Test module imports"""

    def test_import_from_module(self):
        """Test FocusBorder can be imported from module"""
        from fichero.shared.focus import FocusBorder as FB
        self.assertIs(FB, FocusBorder)

    def test_import_directly(self):
        """Test FocusBorder can be imported directly"""
        from fichero.shared.focus.focus_border import FocusBorder as FB
        self.assertIs(FB, FocusBorder)


class TestFocusBorderDefaults(unittest.TestCase):
    """Test default values and constants"""

    def test_default_color_constant(self):
        """Test DEFAULT_FOCUS_COLOR constant"""
        self.assertEqual(FocusBorder.DEFAULT_FOCUS_COLOR, rgb(0, 122, 204))

    def test_default_border_width_constant(self):
        """Test DEFAULT_BORDER_WIDTH constant"""
        self.assertEqual(FocusBorder.DEFAULT_BORDER_WIDTH, 2)


if __name__ == '__main__':
    unittest.main()
