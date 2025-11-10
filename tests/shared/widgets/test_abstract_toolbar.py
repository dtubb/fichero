"""
Unit tests for AbstractToolbar widget.

Tests toolbar size variants and button management.
"""

import unittest
from unittest.mock import Mock

from src.fichero.shared.widgets import AbstractToolbar, ToolbarSize, ToolbarButton


class TestToolbarButton(unittest.TestCase):
    """Test ToolbarButton configuration."""

    def test_button_creation(self):
        """Test creating a toolbar button."""
        callback = Mock()
        button = ToolbarButton(
            id="test_btn",
            label="Test",
            icon="test.png",
            tooltip="Test tooltip",
            on_press=callback,
            essential=True,
            enabled=True,
        )

        self.assertEqual(button.id, "test_btn")
        self.assertEqual(button.label, "Test")
        self.assertEqual(button.icon, "test.png")
        self.assertEqual(button.tooltip, "Test tooltip")
        self.assertEqual(button.on_press, callback)
        self.assertTrue(button.essential)
        self.assertTrue(button.enabled)

    def test_button_defaults(self):
        """Test button creation with defaults."""
        button = ToolbarButton(id="test", label="Test")

        self.assertEqual(button.tooltip, "Test")  # Defaults to label
        self.assertIsNone(button.icon)
        self.assertIsNone(button.on_press)
        self.assertFalse(button.essential)
        self.assertTrue(button.enabled)


class TestAbstractToolbar(unittest.TestCase):
    """Test AbstractToolbar size variants and button management."""

    def setUp(self):
        """Set up test fixtures."""
        self.buttons = [
            ToolbarButton("save", "Save", essential=True),
            ToolbarButton("open", "Open", essential=True),
            ToolbarButton("settings", "Settings", essential=False),
            ToolbarButton("help", "Help", essential=False),
        ]

    def test_full_size_shows_all_buttons(self):
        """Test that FULL size shows all buttons with labels."""
        toolbar = AbstractToolbar(self.buttons, size=ToolbarSize.FULL)

        self.assertEqual(toolbar.size, ToolbarSize.FULL)
        self.assertEqual(len(toolbar._buttons), 4)  # All buttons visible

    def test_compact_size_shows_all_buttons(self):
        """Test that COMPACT size shows all buttons (icons only)."""
        toolbar = AbstractToolbar(self.buttons, size=ToolbarSize.COMPACT)

        self.assertEqual(toolbar.size, ToolbarSize.COMPACT)
        self.assertEqual(len(toolbar._buttons), 4)  # All buttons visible

    def test_mini_size_shows_essential_only(self):
        """Test that MINI size shows only essential buttons."""
        toolbar = AbstractToolbar(self.buttons, size=ToolbarSize.MINI)

        self.assertEqual(toolbar.size, ToolbarSize.MINI)
        self.assertEqual(len(toolbar._buttons), 2)  # Only essential buttons

        # Verify essential buttons are present
        self.assertIn("save", toolbar._buttons)
        self.assertIn("open", toolbar._buttons)

        # Verify non-essential buttons are absent
        self.assertNotIn("settings", toolbar._buttons)
        self.assertNotIn("help", toolbar._buttons)

    def test_set_size_rebuilds_toolbar(self):
        """Test that changing size rebuilds the toolbar."""
        toolbar = AbstractToolbar(self.buttons, size=ToolbarSize.FULL)

        # Initially FULL, all 4 buttons
        self.assertEqual(len(toolbar._buttons), 4)

        # Change to MINI
        toolbar.set_size(ToolbarSize.MINI)
        self.assertEqual(toolbar.size, ToolbarSize.MINI)
        self.assertEqual(len(toolbar._buttons), 2)  # Only essential

        # Change back to FULL
        toolbar.set_size(ToolbarSize.FULL)
        self.assertEqual(toolbar.size, ToolbarSize.FULL)
        self.assertEqual(len(toolbar._buttons), 4)  # All buttons again

    def test_set_size_no_op_if_same(self):
        """Test that setting the same size doesn't rebuild."""
        toolbar = AbstractToolbar(self.buttons, size=ToolbarSize.FULL)
        original_buttons = toolbar._buttons.copy()

        # Set to same size
        toolbar.set_size(ToolbarSize.FULL)

        # Should still be the same
        self.assertEqual(toolbar.size, ToolbarSize.FULL)

    def test_enable_button(self):
        """Test enabling a button."""
        toolbar = AbstractToolbar(self.buttons)
        button = toolbar.get_button("save")

        # Initially enabled
        self.assertTrue(button.enabled)

        # Disable it
        toolbar.enable_button("save", False)
        self.assertFalse(button.enabled)

        # Re-enable it
        toolbar.enable_button("save", True)
        self.assertTrue(button.enabled)

    def test_disable_button(self):
        """Test disabling a button."""
        toolbar = AbstractToolbar(self.buttons)
        button = toolbar.get_button("save")

        # Disable
        toolbar.disable_button("save")
        self.assertFalse(button.enabled)

    def test_get_button(self):
        """Test retrieving a button by ID."""
        toolbar = AbstractToolbar(self.buttons)

        save_button = toolbar.get_button("save")
        self.assertIsNotNone(save_button)

        # Non-existent button
        missing = toolbar.get_button("nonexistent")
        self.assertIsNone(missing)

    def test_get_button_not_in_mini(self):
        """Test that non-essential buttons are not accessible in MINI mode."""
        toolbar = AbstractToolbar(self.buttons, size=ToolbarSize.MINI)

        # Essential button should exist
        save_button = toolbar.get_button("save")
        self.assertIsNotNone(save_button)

        # Non-essential button should not exist in MINI
        settings_button = toolbar.get_button("settings")
        self.assertIsNone(settings_button)


if __name__ == '__main__':
    unittest.main()
