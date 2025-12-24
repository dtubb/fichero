"""
Unit tests for preview pane toggle functionality.

Tests the smart behavior of toggling image and metadata panes independently:
- Image and metadata can be toggled independently
- At least one preview pane must always be visible
- Info pane auto-hides when both preview panes are hidden
- Info pane cannot be shown when both preview panes are hidden
- Width ratios only work when both panes are visible
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))


class MockSlot:
    """Mock slot for layout manager"""
    def __init__(self, name, is_visible=True):
        self.name = name
        self.is_visible = is_visible
        self.container = Mock()
        self.container.style = Mock()
        self.container.style.flex = 1
        self.slot_id = name


class MockLayoutManager:
    """Mock layout manager with column visibility tracking"""
    def __init__(self):
        self.slots = {
            "Library": MockSlot("Library", True),
            "Collection": MockSlot("Collection", True),
            "PreviewImage": MockSlot("PreviewImage", True),
            "PreviewMetadata": MockSlot("PreviewMetadata", True),
            "Adjust": MockSlot("Adjust", True)
        }

    def _find_slot_by_name(self, name):
        return self.slots.get(name)

    def toggle_column(self, name):
        """Toggle column visibility and return new state"""
        slot = self.slots.get(name)
        if slot:
            slot.is_visible = not slot.is_visible
            return slot.is_visible
        return False

    def show_column(self, name):
        """Show a column"""
        slot = self.slots.get(name)
        if slot:
            slot.is_visible = True

    def hide_column(self, name):
        """Hide a column"""
        slot = self.slots.get(name)
        if slot:
            slot.is_visible = False


class TestPreviewPaneToggles(unittest.TestCase):
    """Test preview pane toggle functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.layout_manager = MockLayoutManager()

        # Create mock navigation controller
        self.nav_controller = Mock()
        self.nav_controller.layout_manager = self.layout_manager

        # Create mock main window
        self.window = Mock()
        self.window.is_mobile = False
        self.window.navigation_controller = self.nav_controller
        self.window._update_toolbar_menu_checkmarks = Mock()

        # Import the actual methods
        from fichero.windows.main.main_window import MainWindow
        self.window._toggle_preview_image_pane = lambda w: MainWindow._toggle_preview_image_pane(self.window, w)
        self.window._toggle_preview_metadata_pane = lambda w: MainWindow._toggle_preview_metadata_pane(self.window, w)
        self.window._toggle_inspector_pane = lambda w: MainWindow._toggle_inspector_pane(self.window, w)
        self.window._cycle_preview_ratios = lambda w: MainWindow._cycle_preview_ratios(self.window, w)
        self.window._apply_preview_ratio = lambda p, w: MainWindow._apply_preview_ratio(self.window, p, w)

        # Mock state manager
        self.window.app = Mock()
        self.window.app.state_manager = Mock()
        self.window.app.state_manager.get_current_preview_preset = Mock(return_value="wide_content")
        self.window.app.state_manager.set_current_preview_preset = Mock()

    def test_toggle_image_both_visible(self):
        """Test toggling image when both panes are visible"""
        # Both visible initially
        self.assertTrue(self.layout_manager.slots["PreviewImage"].is_visible)
        self.assertTrue(self.layout_manager.slots["PreviewMetadata"].is_visible)

        # Toggle image off
        self.window._toggle_preview_image_pane(None)

        # Image should be hidden, metadata still visible
        self.assertFalse(self.layout_manager.slots["PreviewImage"].is_visible)
        self.assertTrue(self.layout_manager.slots["PreviewMetadata"].is_visible)

    def test_toggle_image_prevents_both_hidden(self):
        """Test that toggling image shows metadata if both would be hidden"""
        # Hide metadata first
        self.layout_manager.slots["PreviewMetadata"].is_visible = False

        # Toggle image (would hide both)
        self.window._toggle_preview_image_pane(None)

        # Metadata should be shown automatically
        self.assertTrue(self.layout_manager.slots["PreviewMetadata"].is_visible)

    def test_toggle_metadata_both_visible(self):
        """Test toggling metadata when both panes are visible"""
        # Both visible initially
        self.assertTrue(self.layout_manager.slots["PreviewImage"].is_visible)
        self.assertTrue(self.layout_manager.slots["PreviewMetadata"].is_visible)

        # Toggle metadata off
        self.window._toggle_preview_metadata_pane(None)

        # Metadata should be hidden, image still visible
        self.assertTrue(self.layout_manager.slots["PreviewImage"].is_visible)
        self.assertFalse(self.layout_manager.slots["PreviewMetadata"].is_visible)

    def test_toggle_metadata_prevents_both_hidden(self):
        """Test that toggling metadata shows image if both would be hidden"""
        # Hide image first
        self.layout_manager.slots["PreviewImage"].is_visible = False

        # Toggle metadata (would hide both)
        self.window._toggle_preview_metadata_pane(None)

        # Image should be shown automatically
        self.assertTrue(self.layout_manager.slots["PreviewImage"].is_visible)

    def test_info_pane_hides_when_both_preview_hidden(self):
        """Test that Info pane auto-hides when both preview panes are hidden"""
        # Start with metadata hidden
        self.layout_manager.slots["PreviewMetadata"].is_visible = False

        # Toggle image off (would hide both, metadata shown, Info should hide)
        self.window._toggle_preview_image_pane(None)

        # Info should be hidden (even though metadata was shown)
        # This tests the "both were hidden" scenario
        self.assertFalse(self.layout_manager.slots["Adjust"].is_visible)

    def test_info_toggle_blocked_when_both_preview_hidden(self):
        """Test that Info pane cannot be toggled when both preview panes are hidden"""
        # Hide both preview panes
        self.layout_manager.slots["PreviewImage"].is_visible = False
        self.layout_manager.slots["PreviewMetadata"].is_visible = False
        self.layout_manager.slots["Adjust"].is_visible = False

        # Try to toggle Info
        self.window._toggle_inspector_pane(None)

        # Info should remain hidden
        self.assertFalse(self.layout_manager.slots["Adjust"].is_visible)

    def test_info_toggle_works_when_one_preview_visible(self):
        """Test that Info pane can be toggled when at least one preview pane is visible"""
        # Hide metadata, keep image visible
        self.layout_manager.slots["PreviewMetadata"].is_visible = False
        self.layout_manager.slots["Adjust"].is_visible = True

        # Toggle Info off
        self.window._toggle_inspector_pane(None)

        # Info should be hidden
        self.assertFalse(self.layout_manager.slots["Adjust"].is_visible)

        # Toggle Info back on
        self.window._toggle_inspector_pane(None)

        # Info should be visible
        self.assertTrue(self.layout_manager.slots["Adjust"].is_visible)

    def test_cycle_ratios_requires_both_visible(self):
        """Test that cycling ratios only works when both preview panes are visible"""
        # Hide metadata
        self.layout_manager.slots["PreviewMetadata"].is_visible = False

        # Try to cycle ratios
        self.window._cycle_preview_ratios(None)

        # State manager should not be called (ratio not applied)
        self.window.app.state_manager.set_current_preview_preset.assert_not_called()

    def test_cycle_ratios_works_when_both_visible(self):
        """Test that cycling ratios works when both preview panes are visible"""
        # Both visible
        self.assertTrue(self.layout_manager.slots["PreviewImage"].is_visible)
        self.assertTrue(self.layout_manager.slots["PreviewMetadata"].is_visible)

        # Cycle ratios (should go from wide_content to wide_image)
        self.window._cycle_preview_ratios(None)

        # State manager should be called with next preset
        self.window.app.state_manager.set_current_preview_preset.assert_called_once_with("wide_image")

    def test_apply_ratio_requires_both_visible(self):
        """Test that applying ratios only works when both preview panes are visible"""
        # Hide image
        self.layout_manager.slots["PreviewImage"].is_visible = False

        # Try to apply ratio
        self.window._apply_preview_ratio("balanced", None)

        # Flex should not be modified (container style not touched)
        # We can't easily test this without more mocking, but the method should return early
        # The state manager would be called only if successful
        self.window.app.state_manager.set_current_preview_preset.assert_not_called()

    def test_apply_ratio_works_when_both_visible(self):
        """Test that applying ratios works when both preview panes are visible"""
        # Both visible
        self.assertTrue(self.layout_manager.slots["PreviewImage"].is_visible)
        self.assertTrue(self.layout_manager.slots["PreviewMetadata"].is_visible)

        # Apply balanced ratio
        self.window._apply_preview_ratio("balanced", None)

        # Flex values should be set (50/50)
        image_slot = self.layout_manager.slots["PreviewImage"]
        metadata_slot = self.layout_manager.slots["PreviewMetadata"]
        self.assertEqual(image_slot.container.style.flex, 50)
        self.assertEqual(metadata_slot.container.style.flex, 50)

        # State manager should be updated
        self.window.app.state_manager.set_current_preview_preset.assert_called_once_with("balanced")

    def test_cycle_ratios_order(self):
        """Test that ratios cycle in correct order: wide_image -> balanced -> wide_content"""
        # Start at wide_image
        self.window.app.state_manager.get_current_preview_preset.return_value = "wide_image"
        self.window._cycle_preview_ratios(None)
        self.window.app.state_manager.set_current_preview_preset.assert_called_with("balanced")

        # Reset and test balanced -> wide_content
        self.window.app.state_manager.set_current_preview_preset.reset_mock()
        self.window.app.state_manager.get_current_preview_preset.return_value = "balanced"
        self.window._cycle_preview_ratios(None)
        self.window.app.state_manager.set_current_preview_preset.assert_called_with("wide_content")

        # Reset and test wide_content -> wide_image (wrap around)
        self.window.app.state_manager.set_current_preview_preset.reset_mock()
        self.window.app.state_manager.get_current_preview_preset.return_value = "wide_content"
        self.window._cycle_preview_ratios(None)
        self.window.app.state_manager.set_current_preview_preset.assert_called_with("wide_image")


if __name__ == '__main__':
    unittest.main()
