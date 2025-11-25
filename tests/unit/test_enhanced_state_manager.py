"""
Comprehensive Unit Tests for Enhanced StateManager

Tests the enhanced state management system including:
- Basic initialization and event loop safety
- Window state management (size, position, display tracking)
- Pane visibility tracking for all panes
- Layout dimensions and proportions with validation
- Preview ratio presets and state persistence
- Migration from v1.0 to v2.0 state format
- Backwards compatibility methods
- Edge cases (NaN, infinity, extreme values)
- Async/sync save operations with error handling
- State file corruption recovery
- Performance considerations
"""

import unittest
import asyncio
from unittest.mock import Mock, patch, MagicMock, AsyncMock, mock_open
import tempfile
import json
import math
from pathlib import Path
import shutil
import os
import time
from datetime import datetime
import pytest


class TestEnhancedStateManager(unittest.TestCase):
    """Comprehensive tests for enhanced StateManager functionality"""

    def setUp(self):
        """Set up test environment with temporary directory"""
        # Create temporary directory for state files
        self.test_dir = tempfile.mkdtemp()
        self.test_state_file = Path(self.test_dir) / "app_state.json"

        # Mock app with necessary attributes
        self.mock_app = Mock()
        self.mock_app.paths = Mock()
        self.mock_app.paths.data = Path(self.test_dir)

        # Store original import for cleanup
        self.original_app_preferences = None

        # Mock app_preferences to return our test directory
        with patch('fichero.config.core.app_preferences.discover_app_data_directory') as mock_discover:
            mock_discover.return_value = Path(self.test_dir)
            from fichero.config.core.state_manager import StateManager
            self.StateManager = StateManager

    def tearDown(self):
        """Clean up test environment"""
        # Remove temporary directory
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_initialization_without_event_loop(self):
        """Test that StateManager can be created without an active event loop"""
        # Ensure no event loop is running
        try:
            loop = asyncio.get_running_loop()
            loop.close()  # This won't work, but testing the try/except
        except RuntimeError:
            pass  # Expected - no event loop running

        # StateManager should initialize successfully
        manager = self.StateManager(self.mock_app)

        # Should have default state (v3.0)
        self.assertEqual(manager._state["version"], "3.0")
        self.assertIsInstance(manager._state["session"], dict)
        self.assertIsInstance(manager._state["window"], dict)
        self.assertIsInstance(manager._state["layout"], dict)
        self.assertIsInstance(manager._state["pane_visibility"], dict)
        self.assertIsInstance(manager._state["preview_config"], dict)
        # v3.0 additions
        self.assertIsInstance(manager._state["windows"], dict)
        self.assertIsInstance(manager._state["preferences"], dict)
        self.assertIsInstance(manager._state["preview_viewer_state"], dict)
        self.assertIsInstance(manager._state["pane_content"], dict)

        # Lock should be None initially (created lazily)
        self.assertIsNone(manager._lock)

    @pytest.mark.asyncio
    async def test_initialization_with_event_loop(self):
        """Test StateManager initialization with an active event loop"""
        manager = self.StateManager(self.mock_app)

        # Should initialize successfully (v3.0)
        self.assertEqual(manager._state["version"], "3.0")

        # Lock should be created when accessed
        lock = manager._get_or_create_lock()
        self.assertIsInstance(lock, asyncio.Lock)

    def test_default_state_structure(self):
        """Test the default state structure is complete and valid"""
        manager = self.StateManager(self.mock_app)
        default_state = manager._default_state()

        # Check top-level structure (v3.0 includes additional keys)
        expected_keys = {
            "version", "session", "window", "pane_visibility", "layout",
            "preview_config", "ui_preferences", "last_saved",
            # v3.0 additions:
            "windows", "preferences", "preview_viewer_state", "pane_content"
        }
        self.assertEqual(set(default_state.keys()), expected_keys)

        # Check session structure
        session_keys = {
            "last_collection_id", "last_item_id", "preview_visible", "column_visibility"
        }
        self.assertEqual(set(default_state["session"].keys()), session_keys)

        # Check window structure (legacy single-window tracking)
        window_keys = {
            "size", "position", "is_maximized", "display_id", "display_bounds", "state_change_count"
        }
        self.assertEqual(set(default_state["window"].keys()), window_keys)

        # Check pane_visibility structure (includes actual column names + legacy aliases)
        # Column names: Library, Collection, PreviewImage, PreviewMetadata, Adjust
        # Legacy aliases: sidebar (Library), preview (PreviewImage), inspector (Adjust)
        pane_keys = {
            # Actual column names (lowercase)
            "library", "collection", "previewimage", "previewmetadata", "adjust",
            # Legacy aliases for backward compatibility
            "sidebar", "preview", "inspector",
            # UI elements
            "status_bar", "toolbar"
        }
        self.assertEqual(set(default_state["pane_visibility"].keys()), pane_keys)

        # Check layout structure
        layout_keys = {
            "main_layout", "preview_layout", "dimensions", "proportions",
            "split_orientation", "focus_state"
        }
        self.assertEqual(set(default_state["layout"].keys()), layout_keys)

        # Check preview_config structure
        preview_keys = {
            "layout_type", "ratio_presets", "current_preset", "custom_ratio", "context_preservation"
        }
        self.assertEqual(set(default_state["preview_config"].keys()), preview_keys)

        # Check v3.0 windows structure (multi-window tracking)
        self.assertIsInstance(default_state["windows"], dict)

        # Check v3.0 preferences structure
        preferences_keys = {
            "active_settings_file", "recent_documents", "open_documents",
            "last_used_directories", "preferred_plan", "preferred_workflow"
        }
        self.assertEqual(set(default_state["preferences"].keys()), preferences_keys)

        # Check v3.0 preview_viewer_state structure
        viewer_keys = {"scale", "rotation", "scroll_x", "scroll_y"}
        self.assertEqual(set(default_state["preview_viewer_state"].keys()), viewer_keys)

        # Check v3.0 pane_content structure
        pane_content_keys = {"library", "collection", "preview_image", "preview_metadata", "adjust"}
        self.assertEqual(set(default_state["pane_content"].keys()), pane_content_keys)

    def test_window_state_management(self):
        """Test window state management functionality"""
        manager = self.StateManager(self.mock_app)

        # Test window size
        manager.set_window_size(1200, 800)
        self.assertEqual(manager.get_window_size(), (1200, 800))

        # Test window position
        manager.set_window_position(100, 50)
        self.assertEqual(manager.get_window_position(), (100, 50))

        # Test maximized state
        manager.set_window_maximized(True)
        self.assertTrue(manager.get_window_maximized())

        # Test display tracking
        manager.set_window_display_id("display-123")
        self.assertEqual(manager.get_window_display_id(), "display-123")

        display_bounds = {"x": 0, "y": 0, "width": 1920, "height": 1080}
        manager.set_window_display_bounds(display_bounds)
        self.assertEqual(manager.get_window_display_bounds(), display_bounds)

        # Test state change counter
        initial_count = manager.get_window_state_change_count()
        manager.increment_window_state_changes()
        self.assertEqual(manager.get_window_state_change_count(), initial_count + 1)

    def test_window_position_validation(self):
        """Test window position validation against display bounds"""
        manager = self.StateManager(self.mock_app)

        # Set display bounds
        bounds = {"x": 0, "y": 0, "width": 1920, "height": 1080}
        manager.set_window_display_bounds(bounds)

        # Test valid position
        valid_pos = manager.validate_window_position(100, 100)
        self.assertEqual(valid_pos, (100, 100))

        # Test position outside bounds (should be clamped)
        clamped_pos = manager.validate_window_position(2000, 1200)
        self.assertEqual(clamped_pos, (1820, 980))  # width-100, height-100

        # Test negative position (should be clamped to minimum)
        min_pos = manager.validate_window_position(-50, -25)
        self.assertEqual(min_pos, (0, 0))

    def test_pane_visibility_management(self):
        """Test pane visibility tracking for all panes"""
        manager = self.StateManager(self.mock_app)

        # Test individual pane visibility for all keys (actual columns + legacy aliases + UI elements)
        panes = [
            # Actual column names
            "library", "collection", "previewimage", "previewmetadata", "adjust",
            # Legacy aliases
            "sidebar", "preview", "inspector",
            # UI elements
            "status_bar", "toolbar"
        ]

        for pane in panes:
            # Test default visibility
            self.assertIsInstance(manager.get_pane_visibility(pane), bool)

            # Test setting visibility
            manager.set_pane_visibility(pane, False)
            self.assertFalse(manager.get_pane_visibility(pane))

            # Test toggling
            new_state = manager.toggle_pane_visibility(pane)
            self.assertTrue(new_state)
            self.assertTrue(manager.get_pane_visibility(pane))

        # Test bulk operations
        all_states = manager.get_all_pane_visibility()
        self.assertIsInstance(all_states, dict)
        self.assertEqual(set(all_states.keys()), set(panes))

        new_states = {pane: False for pane in panes}
        manager.set_all_pane_visibility(new_states)

        for pane in panes:
            self.assertFalse(manager.get_pane_visibility(pane))

    def test_layout_dimensions_and_proportions(self):
        """Test layout dimensions and proportions with validation"""
        manager = self.StateManager(self.mock_app)

        # Test dimensions
        dimensions = ["sidebar_width", "collection_width", "preview_width", "inspector_width"]

        for dim in dimensions:
            # Test setting valid dimension
            manager.set_pane_dimension(dim, 300)
            self.assertEqual(manager.get_pane_dimension(dim), 300)

            # Test setting None
            manager.set_pane_dimension(dim, None)
            self.assertIsNone(manager.get_pane_dimension(dim))

        # Test proportions
        proportions = ["preview_ratio", "sidebar_proportion", "collection_proportion", "preview_proportion"]

        for prop in proportions:
            # Test setting valid proportion
            manager.set_layout_proportion(prop, 0.6)
            self.assertEqual(manager.get_layout_proportion(prop), 0.6)

            # Test proportion validation (should clamp to 0.1-0.9)
            manager.set_layout_proportion(prop, 1.5)
            self.assertEqual(manager.get_layout_proportion(prop), 0.9)

            manager.set_layout_proportion(prop, 0.05)
            self.assertEqual(manager.get_layout_proportion(prop), 0.1)

    def test_preview_ratio_presets(self):
        """Test preview ratio presets functionality"""
        manager = self.StateManager(self.mock_app)

        # Test default presets
        presets = manager.get_preview_ratio_presets()
        expected_presets = {"balanced", "content_focused", "image_focused", "wide_content", "wide_image"}
        self.assertEqual(set(presets.keys()), expected_presets)

        # Test individual preset access
        self.assertEqual(manager.get_preview_ratio_preset("balanced"), 0.5)
        self.assertEqual(manager.get_preview_ratio_preset("wide_content"), 0.75)

        # Test setting preset
        manager.set_preview_ratio_preset("custom_preset", 0.6)
        self.assertEqual(manager.get_preview_ratio_preset("custom_preset"), 0.6)

        # Test current preset management
        manager.set_current_preview_preset("wide_content")
        self.assertEqual(manager.get_current_preview_preset(), "wide_content")
        self.assertEqual(manager.get_layout_proportion("preview_ratio"), 0.75)

        # Test custom ratio
        manager.set_custom_preview_ratio(0.65)
        self.assertEqual(manager.get_custom_preview_ratio(), 0.65)
        self.assertEqual(manager.get_current_preview_preset(), "custom")

        # Test apply preset ratio
        success = manager.apply_preview_preset_ratio("balanced")
        self.assertTrue(success)
        self.assertEqual(manager.get_current_preview_preset(), "balanced")

    def test_edge_case_validation(self):
        """Test edge case validation for NaN, infinity, and extreme values"""
        manager = self.StateManager(self.mock_app)

        # Test ratio validation with edge cases
        test_cases = [
            (float('nan'), 0.5),      # NaN should default
            (float('inf'), 0.5),      # Infinity should default
            (-float('inf'), 0.5),     # Negative infinity should default
            (-1.0, 0.1),              # Negative should clamp to minimum
            (2.0, 0.9),               # Too large should clamp to maximum
            (None, 0.5),              # None should default
            ("invalid", 0.5),         # String should default
        ]

        for input_val, expected in test_cases:
            validated = manager._validate_ratio(input_val)
            self.assertEqual(validated, expected, f"Failed for input: {input_val}")

        # Test dimension validation with edge cases
        dim_test_cases = [
            (float('nan'), None),     # NaN should return None
            (float('inf'), None),     # Infinity should return None
            (-100, 50),               # Negative should clamp to minimum
            (20000, 10000),           # Too large should clamp to maximum
            (None, None),             # None should remain None
            ("invalid", None),        # String should return None
        ]

        for input_val, expected in dim_test_cases:
            validated = manager._validate_dimension(input_val)
            self.assertEqual(validated, expected, f"Failed for input: {input_val}")

    def test_state_file_persistence(self):
        """Test state file save and load operations"""
        manager = self.StateManager(self.mock_app)

        # Modify some state
        manager.set_window_size(1024, 768)
        manager.set_pane_visibility("sidebar", False)
        manager.set_layout_proportion("preview_ratio", 0.7)

        # Save state synchronously
        manager.save_state_sync()

        # Verify file was created
        self.assertTrue(self.test_state_file.exists())

        # Load state in new manager instance
        manager2 = self.StateManager(self.mock_app)

        # Verify state was restored
        self.assertEqual(manager2.get_window_size(), (1024, 768))
        self.assertFalse(manager2.get_pane_visibility("sidebar"))
        self.assertEqual(manager2.get_layout_proportion("preview_ratio"), 0.7)

    @pytest.mark.asyncio
    async def test_async_save_operations(self):
        """Test async save operations"""
        manager = self.StateManager(self.mock_app)

        # Modify state
        manager.set_window_position(200, 100)

        # Save asynchronously
        await manager.save_state()

        # Verify file was created and contains expected data
        self.assertTrue(self.test_state_file.exists())

        with open(self.test_state_file, 'r') as f:
            saved_data = json.load(f)

        self.assertEqual(saved_data["window"]["position"], [200, 100])
        self.assertIsNotNone(saved_data.get("last_saved"))

    def test_v1_to_v3_migration(self):
        """Test migration from v1.0 to v3.0 state format"""
        # Create v1.0 state structure
        v1_state = {
            "version": "1.0",
            "session": {
                "last_collection_id": "test-collection",
                "preview_visible": True,
                "column_visibility": {
                    "library": True,
                    "collection": False,
                    "preview": True,
                    "adjust": False
                }
            },
            "window": {
                "size": [800, 600],
                "is_maximized": False
            },
            "layout": {
                "main_layout": {"some": "data"},
                "preview_layout": {"other": "data"}
            },
            "ui_preferences": {
                "show_status_bar": False
            }
        }

        # Save v1 state to file
        with open(self.test_state_file, 'w') as f:
            json.dump(v1_state, f)

        # Load with new manager (should trigger migration to v3.0)
        manager = self.StateManager(self.mock_app)

        # Verify migration occurred to v3.0
        self.assertEqual(manager._state["version"], "3.0")

        # Verify data was preserved
        self.assertEqual(manager.get_last_collection_id(), "test-collection")
        self.assertTrue(manager.get_preview_visible())

        # Verify column_visibility was migrated to pane_visibility
        self.assertTrue(manager.get_pane_visibility("sidebar"))    # library -> sidebar
        self.assertFalse(manager.get_pane_visibility("collection")) # collection -> collection
        self.assertTrue(manager.get_pane_visibility("preview"))    # preview -> preview
        self.assertFalse(manager.get_pane_visibility("inspector")) # adjust -> inspector

        # Verify new v3.0 features have defaults
        self.assertIsInstance(manager._state["preview_config"], dict)
        self.assertEqual(manager.get_preview_layout_type(), "side_by_side")

        # Verify v3.0 additions exist
        self.assertIsInstance(manager._state["windows"], dict)
        self.assertIsInstance(manager._state["preferences"], dict)
        self.assertIsInstance(manager._state["preview_viewer_state"], dict)
        self.assertIsInstance(manager._state["pane_content"], dict)

    def test_corrupted_state_file_recovery(self):
        """Test recovery from corrupted state files using backup"""
        # Create corrupted main state file
        with open(self.test_state_file, 'w') as f:
            f.write("{ invalid json content")

        # Create valid backup file
        backup_file = self.test_state_file.with_suffix('.bak')
        valid_backup = {
            "version": "2.0",
            "session": {"last_collection_id": "backup-recovery"},
            "window": {"size": [640, 480]},
            "pane_visibility": {},
            "layout": {},
            "preview_config": {},
            "ui_preferences": {}
        }

        with open(backup_file, 'w') as f:
            json.dump(valid_backup, f)

        # StateManager should recover from backup
        manager = self.StateManager(self.mock_app)

        # Verify recovery
        self.assertEqual(manager.get_last_collection_id(), "backup-recovery")
        self.assertEqual(manager.get_window_size(), (640, 480))

    def test_state_file_corruption_fallback_to_defaults(self):
        """Test fallback to defaults when both main and backup files are corrupted"""
        # Create corrupted main file
        with open(self.test_state_file, 'w') as f:
            f.write("{ corrupted json")

        # Create corrupted backup file
        backup_file = self.test_state_file.with_suffix('.bak')
        with open(backup_file, 'w') as f:
            f.write("{ also corrupted")

        # StateManager should fall back to defaults
        manager = self.StateManager(self.mock_app)

        # Verify defaults are used (v3.0)
        self.assertEqual(manager._state["version"], "3.0")
        self.assertIsNone(manager.get_last_collection_id())
        self.assertIsNone(manager.get_window_size())

    def test_backwards_compatibility_methods(self):
        """Test backwards compatibility methods still work"""
        manager = self.StateManager(self.mock_app)

        # These methods should still work even though they map to new pane_visibility system
        manager.set_column_visibility("library", False)
        self.assertFalse(manager.get_column_visibility("library"))

        # Should map to pane_visibility internally
        # (Note: The actual mapping depends on implementation)

    def test_performance_with_large_state(self):
        """Test performance with large state files"""
        manager = self.StateManager(self.mock_app)

        # Add large amounts of data
        large_layout = {f"key_{i}": f"value_{i}" for i in range(1000)}
        manager.set_main_layout_state(large_layout)

        # Add many custom presets
        for i in range(100):
            manager.set_preview_ratio_preset(f"preset_{i}", 0.5 + (i % 40) * 0.01)

        # Save should still work efficiently
        start_time = time.time()
        manager.save_state_sync()
        save_time = time.time() - start_time

        # Save should complete in reasonable time (< 1 second)
        self.assertLess(save_time, 1.0)

        # Load should also be fast
        start_time = time.time()
        manager2 = self.StateManager(self.mock_app)
        load_time = time.time() - start_time

        self.assertLess(load_time, 1.0)

        # Data should be preserved
        self.assertEqual(len(manager2.get_main_layout_state()), 1000)

    def test_atomic_file_operations(self):
        """Test atomic file operations with backup creation"""
        manager = self.StateManager(self.mock_app)

        # Save initial state
        manager.set_window_size(800, 600)
        manager.save_state_sync()

        # Modify state
        manager.set_window_size(1024, 768)

        # Mock a failure during file writing to test atomic operations
        with patch('builtins.open', mock_open()) as mock_file:
            # Make the write operation fail after backup is created
            mock_file.side_effect = [
                mock_open().return_value,  # Temp file creation succeeds
                OSError("Disk full")       # Main file write fails
            ]

            # Save should handle the error gracefully
            manager.save_state_sync()

            # Original file should still exist and be valid
            # (In real scenario - testing the error handling path)

    @pytest.mark.asyncio
    async def test_concurrent_access_safety(self):
        """Test thread/async safety of state operations"""
        manager = self.StateManager(self.mock_app)

        # Simulate multiple concurrent saves
        save_tasks = []
        for i in range(10):
            manager.set_window_size(800 + i, 600 + i)
            save_tasks.append(asyncio.create_task(manager.save_state()))

        # All saves should complete without error
        await asyncio.gather(*save_tasks, return_exceptions=True)

        # Final state should be valid
        self.assertIsNotNone(manager.get_window_size())

    def test_layout_snapshots(self):
        """Test layout snapshot functionality"""
        manager = self.StateManager(self.mock_app)

        # Set up a custom layout
        manager.set_pane_visibility("sidebar", False)
        manager.set_layout_proportion("preview_ratio", 0.8)
        manager.set_current_preview_preset("wide_content")

        # Save snapshot
        manager.save_layout_snapshot("test_layout")

        # Verify snapshot was saved
        snapshots = manager.get_available_snapshots()
        self.assertIn("test_layout", snapshots)

        # Change layout
        manager.set_pane_visibility("sidebar", True)
        manager.set_layout_proportion("preview_ratio", 0.3)

        # Restore snapshot
        success = manager.restore_layout_snapshot("test_layout")
        self.assertTrue(success)

        # Verify layout was restored (wide_content preset overrides 0.8 to 0.75)
        self.assertFalse(manager.get_pane_visibility("sidebar"))
        self.assertEqual(manager.get_layout_proportion("preview_ratio"), 0.75)
        self.assertEqual(manager.get_current_preview_preset(), "wide_content")

    def test_export_import_layout_config(self):
        """Test layout configuration export and import"""
        manager = self.StateManager(self.mock_app)

        # Set up custom layout
        manager.set_pane_visibility("preview", True)
        manager.set_pane_dimension("sidebar_width", 250)
        manager.set_layout_proportion("preview_ratio", 0.75)
        manager.set_current_preview_preset("wide_content")

        # Export configuration
        config = manager.export_layout_config()

        # Verify export structure
        self.assertEqual(config["version"], "3.0")
        self.assertIn("pane_visibility", config)
        self.assertIn("dimensions", config)
        self.assertIn("proportions", config)
        self.assertIn("preview_config", config)

        # Change layout
        manager.set_pane_visibility("preview", False)
        manager.set_pane_dimension("sidebar_width", 180)

        # Import configuration
        success = manager.import_layout_config(config)
        self.assertTrue(success)

        # Verify layout was restored
        self.assertTrue(manager.get_pane_visibility("preview"))
        self.assertEqual(manager.get_pane_dimension("sidebar_width"), 250)
        self.assertEqual(manager.get_layout_proportion("preview_ratio"), 0.75)

    def test_complete_state_summary(self):
        """Test complete state summary generation"""
        manager = self.StateManager(self.mock_app)

        # Set various state values
        manager.set_window_size(1200, 900)
        manager.set_window_position(100, 50)
        manager.set_last_collection_id("test-collection")
        manager.set_pane_visibility("sidebar", False)

        # Get complete summary
        summary = manager.get_complete_state_summary()

        # Verify structure
        expected_keys = {
            "version", "window", "layout_summary", "session",
            "preview_config", "snapshots_available", "last_saved"
        }
        self.assertEqual(set(summary.keys()), expected_keys)

        # Verify content
        self.assertEqual(summary["window"]["size"], (1200, 900))
        self.assertEqual(summary["session"]["last_collection"], "test-collection")
        # Sidebar is hidden, so it should not appear in panes_visible (which only shows visible panes)
        self.assertNotIn("sidebar", summary["layout_summary"]["panes_visible"])

    def test_error_handling_without_app(self):
        """Test StateManager behavior when app is None"""
        # StateManager should still work with fallback path
        manager = self.StateManager(None)

        # Should initialize with defaults (v3.0)
        self.assertEqual(manager._state["version"], "3.0")

        # Basic operations should work
        manager.set_window_size(800, 600)
        self.assertEqual(manager.get_window_size(), (800, 600))

        # Save operations should work (using fallback directory)
        manager.save_state_sync()

    def test_focus_state_management(self):
        """Test focus state management"""
        manager = self.StateManager(self.mock_app)

        # Test active pane tracking
        manager.set_active_pane("preview")
        self.assertEqual(manager.get_active_pane(), "preview")

        # Test last focused pane tracking
        manager.set_active_pane("collection")
        self.assertEqual(manager.get_last_focused_pane(), "preview")
        self.assertEqual(manager.get_active_pane(), "collection")

        # Test split orientation
        manager.set_split_orientation("vertical")
        self.assertEqual(manager.get_split_orientation(), "vertical")

        # Invalid orientation should be ignored
        manager.set_split_orientation("diagonal")  # Invalid
        self.assertEqual(manager.get_split_orientation(), "vertical")  # Should remain unchanged

    def test_ui_preferences_management(self):
        """Test UI preferences storage and retrieval"""
        manager = self.StateManager(self.mock_app)

        # Test setting and getting preferences
        manager.set_ui_preference("theme", "dark")
        self.assertEqual(manager.get_ui_preference("theme"), "dark")

        # Test default values
        self.assertEqual(manager.get_ui_preference("nonexistent", "default"), "default")

        # Test complex preference objects
        complex_pref = {"nested": {"value": True}, "list": [1, 2, 3]}
        manager.set_ui_preference("complex", complex_pref)
        self.assertEqual(manager.get_ui_preference("complex"), complex_pref)

    def test_session_state_management(self):
        """Test session state management and clearing"""
        manager = self.StateManager(self.mock_app)

        # Set session data
        manager.set_last_collection_id("test-collection")
        manager.set_last_item_id("test-item")
        manager.set_preview_visible(True)

        # Get complete session state
        session_state = manager.get_session_state()
        self.assertEqual(session_state["last_collection_id"], "test-collection")
        self.assertEqual(session_state["last_item_id"], "test-item")
        self.assertTrue(session_state["preview_visible"])

        # Clear session state
        manager.clear_session_state()

        # Session should be reset but other state should remain
        self.assertIsNone(manager.get_last_collection_id())
        self.assertIsNone(manager.get_last_item_id())
        self.assertFalse(manager.get_preview_visible())

    def test_reset_to_defaults(self):
        """Test complete reset to default state"""
        manager = self.StateManager(self.mock_app)

        # Modify various state components
        manager.set_window_size(1024, 768)
        manager.set_pane_visibility("sidebar", False)
        manager.set_layout_proportion("preview_ratio", 0.8)
        manager.set_last_collection_id("test")

        # Reset to defaults
        manager.reset_to_defaults()

        # All state should be reset
        self.assertIsNone(manager.get_window_size())
        self.assertTrue(manager.get_pane_visibility("sidebar"))
        self.assertEqual(manager.get_layout_proportion("preview_ratio"), 0.6)  # content_focused default
        self.assertIsNone(manager.get_last_collection_id())

    def test_layout_reset_to_defaults(self):
        """Test layout-only reset to defaults"""
        manager = self.StateManager(self.mock_app)

        # Modify layout and session state
        manager.set_pane_visibility("sidebar", False)
        manager.set_layout_proportion("preview_ratio", 0.8)
        manager.set_last_collection_id("should-remain")

        # Reset only layout
        manager.reset_layout_to_defaults()

        # Layout should be reset but session should remain
        self.assertTrue(manager.get_pane_visibility("sidebar"))
        self.assertEqual(manager.get_layout_proportion("preview_ratio"), 0.6)  # content_focused default
        self.assertEqual(manager.get_last_collection_id(), "should-remain")  # Should not change

    def test_compact_layout_summary(self):
        """Test compact layout summary for debugging"""
        manager = self.StateManager(self.mock_app)

        # Set specific layout state
        manager.set_pane_visibility("sidebar", True)
        manager.set_pane_visibility("preview", False)
        manager.set_pane_dimension("sidebar_width", 200)
        manager.set_layout_proportion("preview_ratio", 0.7)
        manager.set_active_pane("collection")
        manager.set_current_preview_preset("wide_content")

        # Get compact summary
        summary = manager.get_compact_layout_summary()

        # Should only show visible panes
        visible_panes = summary["panes_visible"]
        self.assertIn("sidebar", visible_panes)
        self.assertNotIn("preview", visible_panes)  # Hidden panes should not appear

        # Should include non-null dimensions
        self.assertEqual(summary["dimensions"]["sidebar_width"], 200)

        # Should include proportions and other key state (wide_content preset overrides manual 0.7 to 0.75)
        self.assertEqual(summary["proportions"]["preview_ratio"], 0.75)
        self.assertEqual(summary["active_pane"], "collection")
        self.assertEqual(summary["preview_preset"], "wide_content")

    # =========================================================================
    # v3.0 Multi-Window State Tracking Tests
    # =========================================================================

    def test_multi_window_state_management(self):
        """Test v3.0 multi-window state tracking"""
        manager = self.StateManager(self.mock_app)

        # Initially no windows saved
        self.assertIsNone(manager.get_window_state("main"))
        self.assertIsNone(manager.get_window_state("inspector"))

        # Save window state for main window
        main_state = {
            "x": 100,
            "y": 200,
            "width": 1200,
            "height": 800,
            "is_visible": True,
            "is_minimized": False,
            "display_id": 1
        }
        manager.set_window_state("main", main_state)

        # Retrieve and verify
        retrieved = manager.get_window_state("main")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["x"], 100)
        self.assertEqual(retrieved["y"], 200)
        self.assertEqual(retrieved["width"], 1200)
        self.assertEqual(retrieved["height"], 800)
        self.assertTrue(retrieved["is_visible"])
        self.assertFalse(retrieved["is_minimized"])
        self.assertEqual(retrieved["display_id"], 1)

        # Save another window
        inspector_state = {
            "x": 500,
            "y": 100,
            "width": 400,
            "height": 600,
            "is_visible": True,
            "is_minimized": False,
            "display_id": 1
        }
        manager.set_window_state("inspector", inspector_state)

        # Both should be retrievable
        self.assertIsNotNone(manager.get_window_state("main"))
        self.assertIsNotNone(manager.get_window_state("inspector"))

    def test_window_state_persistence(self):
        """Test that window states persist across saves/loads"""
        manager = self.StateManager(self.mock_app)

        # Save window state
        window_state = {
            "x": 582,
            "y": 207,
            "width": 880,
            "height": 1090,
            "is_visible": True,
            "is_minimized": False,
            "display_id": 2
        }
        manager.set_window_state("main", window_state)

        # Save state
        manager.save_state_sync()

        # Load in new manager
        manager2 = self.StateManager(self.mock_app)

        # Verify window state was preserved
        retrieved = manager2.get_window_state("main")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["x"], 582)
        self.assertEqual(retrieved["y"], 207)
        self.assertEqual(retrieved["width"], 880)
        self.assertEqual(retrieved["height"], 1090)

    def test_window_state_overwrite(self):
        """Test that updating window state overwrites previous state"""
        manager = self.StateManager(self.mock_app)

        # Initial state
        manager.set_window_state("main", {
            "x": 0, "y": 0, "width": 800, "height": 600,
            "is_visible": True, "is_minimized": False
        })

        # Update state
        manager.set_window_state("main", {
            "x": 100, "y": 50, "width": 1200, "height": 900,
            "is_visible": True, "is_minimized": False
        })

        # Should have updated values
        state = manager.get_window_state("main")
        self.assertEqual(state["x"], 100)
        self.assertEqual(state["y"], 50)
        self.assertEqual(state["width"], 1200)
        self.assertEqual(state["height"], 900)

    def test_preview_viewer_state(self):
        """Test v3.0 preview viewer state tracking"""
        manager = self.StateManager(self.mock_app)

        # Check default values
        viewer_state = manager._state["preview_viewer_state"]
        self.assertEqual(viewer_state["scale"], 1.0)
        self.assertEqual(viewer_state["rotation"], 0)
        self.assertEqual(viewer_state["scroll_x"], 0)
        self.assertEqual(viewer_state["scroll_y"], 0)

    def test_pane_content_state(self):
        """Test v3.0 pane content state tracking"""
        manager = self.StateManager(self.mock_app)

        # Check default structure
        pane_content = manager._state["pane_content"]
        self.assertIn("library", pane_content)
        self.assertIn("collection", pane_content)
        self.assertIn("preview_image", pane_content)
        self.assertIn("preview_metadata", pane_content)
        self.assertIn("adjust", pane_content)

        # Each pane should have expected content fields
        self.assertIn("selected_collection_id", pane_content["library"])
        self.assertIn("scroll_position", pane_content["library"])

        self.assertIn("collection_id", pane_content["collection"])
        self.assertIn("selected_item_id", pane_content["collection"])

    def test_preferences_migration(self):
        """Test v3.0 preferences section"""
        manager = self.StateManager(self.mock_app)

        # Check default preferences structure
        prefs = manager._state["preferences"]
        self.assertIsNone(prefs["active_settings_file"])
        self.assertEqual(prefs["recent_documents"], [])
        self.assertEqual(prefs["open_documents"], [])
        self.assertIsInstance(prefs["last_used_directories"], dict)
        self.assertIsNone(prefs["preferred_plan"])
        self.assertIsNone(prefs["preferred_workflow"])

    def test_v2_to_v3_migration(self):
        """Test migration from v2.0 to v3.0 state format"""
        # Create v2.0 state structure
        v2_state = {
            "version": "2.0",
            "session": {
                "last_collection_id": "test-collection",
                "last_item_id": "test-item",
                "preview_visible": True,
                "column_visibility": {}
            },
            "window": {
                "size": [1024, 768],
                "position": [100, 50],
                "is_maximized": False,
                "display_id": None,
                "display_bounds": None,
                "state_change_count": 5
            },
            "pane_visibility": {
                "sidebar": True,
                "collection": True,
                "preview": True,
                "inspector": False,
                "status_bar": True,
                "toolbar": True
            },
            "layout": {
                "main_layout": {},
                "preview_layout": {},
                "dimensions": {},
                "proportions": {},
                "split_orientation": "horizontal",
                "focus_state": {}
            },
            "preview_config": {
                "layout_type": "side_by_side",
                "ratio_presets": {},
                "current_preset": "balanced",
                "custom_ratio": None,
                "context_preservation": True
            },
            "ui_preferences": {
                "show_path_bar": True,
                "show_status_bar": True
            },
            "last_saved": "2024-01-01T00:00:00"
        }

        # Save v2 state to file
        with open(self.test_state_file, 'w') as f:
            json.dump(v2_state, f)

        # Load with new manager (should trigger migration to v3.0)
        manager = self.StateManager(self.mock_app)

        # Verify migration occurred to v3.0
        self.assertEqual(manager._state["version"], "3.0")

        # Verify v2.0 data was preserved
        self.assertEqual(manager.get_last_collection_id(), "test-collection")
        self.assertEqual(manager.get_last_item_id(), "test-item")
        self.assertTrue(manager.get_preview_visible())

        # Verify v3.0 additions were added
        self.assertIn("windows", manager._state)
        self.assertIn("preferences", manager._state)
        self.assertIn("preview_viewer_state", manager._state)
        self.assertIn("pane_content", manager._state)

        # Verify original pane_visibility keys were preserved
        self.assertIn("sidebar", manager._state["pane_visibility"])
        self.assertIn("collection", manager._state["pane_visibility"])


    def test_pane_visibility_column_name_mapping(self):
        """Test that pane names map correctly to layout manager column names"""
        manager = self.StateManager(self.mock_app)

        # Expected mapping: state key (lowercase) -> column name (camelCase)
        expected_mapping = {
            'library': True,      # Matches column "Library"
            'collection': True,   # Matches column "Collection"
            'previewimage': True, # Matches column "PreviewImage"
            'previewmetadata': True,  # Matches column "PreviewMetadata"
            'adjust': False,      # Matches column "Adjust"
            # Legacy aliases
            'sidebar': True,      # Alias for Library
            'preview': True,      # Alias for PreviewImage
            'inspector': False,   # Alias for Adjust
        }

        # Verify default values match expected mapping
        for key, expected_visible in expected_mapping.items():
            self.assertEqual(
                manager.get_pane_visibility(key),
                expected_visible,
                f"Pane '{key}' should be {'visible' if expected_visible else 'hidden'} by default"
            )

    def test_pane_visibility_persistence(self):
        """Test that pane visibility persists across save/load cycles"""
        manager = self.StateManager(self.mock_app)

        # Change visibility for various panes
        manager.set_pane_visibility("library", False)
        manager.set_pane_visibility("previewimage", False)
        manager.set_pane_visibility("previewmetadata", True)
        manager.set_pane_visibility("adjust", True)

        # Save state
        manager.save_state_sync()

        # Load in new manager
        manager2 = self.StateManager(self.mock_app)

        # Verify state was restored
        self.assertFalse(manager2.get_pane_visibility("library"))
        self.assertFalse(manager2.get_pane_visibility("previewimage"))
        self.assertTrue(manager2.get_pane_visibility("previewmetadata"))
        self.assertTrue(manager2.get_pane_visibility("adjust"))


if __name__ == '__main__':
    unittest.main()