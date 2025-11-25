"""
Unit tests for StateManager v3.0 features.

Tests the new state management features:
- Multi-window state tracking
- Preferences (migrated from app_preferences.json)
- Preview viewer state (zoom, scroll, rotation)
- Pane content tracking
- Migration from v2.0 to v3.0
"""

import unittest
import tempfile
import json
import os
from pathlib import Path
from unittest.mock import Mock, patch


class TestStateManagerV3MultiWindow(unittest.TestCase):
    """Test multi-window state tracking in StateManager v3.0"""

    def setUp(self):
        """Set up test fixtures"""
        # Create temp directory for test state files
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "app_state.json"

        # Import StateManager
        from fichero.config.core.state_manager import StateManager

        # Create StateManager with mocked app
        self.mock_app = Mock()
        self.mock_app.paths = Mock()
        self.mock_app.paths.data = Path(self.temp_dir)

        # Patch discover_app_data_directory to return our temp dir
        with patch('fichero.config.core.state_manager.StateManager._get_state_file_path',
                   return_value=self.state_file):
            self.state_manager = StateManager(self.mock_app)

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_set_and_get_window_state(self):
        """Test setting and getting window state"""
        window_state = {
            "x": 100,
            "y": 200,
            "width": 1200,
            "height": 800,
            "is_visible": True,
            "is_minimized": False
        }

        self.state_manager.set_window_state("main", window_state)
        retrieved = self.state_manager.get_window_state("main")

        self.assertEqual(retrieved, window_state)

    def test_get_window_state_nonexistent(self):
        """Test getting state for window that doesn't exist"""
        result = self.state_manager.get_window_state("nonexistent")
        self.assertIsNone(result)

    def test_get_all_window_states(self):
        """Test getting all window states"""
        self.state_manager.set_window_state("main", {"x": 100, "y": 100})
        self.state_manager.set_window_state("inspector", {"x": 200, "y": 200})

        all_states = self.state_manager.get_all_window_states()

        self.assertEqual(len(all_states), 2)
        self.assertIn("main", all_states)
        self.assertIn("inspector", all_states)

    def test_clear_window_state(self):
        """Test clearing window state"""
        self.state_manager.set_window_state("main", {"x": 100, "y": 100})
        self.state_manager.clear_window_state("main")

        result = self.state_manager.get_window_state("main")
        self.assertIsNone(result)

    def test_multiple_windows(self):
        """Test tracking multiple windows"""
        windows = ["main", "inspector", "settings", "about", "activity"]

        for i, window_id in enumerate(windows):
            self.state_manager.set_window_state(window_id, {
                "x": i * 100,
                "y": i * 50,
                "width": 800,
                "height": 600
            })

        all_states = self.state_manager.get_all_window_states()
        self.assertEqual(len(all_states), 5)

        # Verify each window has correct state
        for i, window_id in enumerate(windows):
            state = self.state_manager.get_window_state(window_id)
            self.assertEqual(state["x"], i * 100)
            self.assertEqual(state["y"], i * 50)


class TestStateManagerV3Preferences(unittest.TestCase):
    """Test preferences accessors in StateManager v3.0"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "app_state.json"

        from fichero.config.core.state_manager import StateManager

        self.mock_app = Mock()
        self.mock_app.paths = Mock()
        self.mock_app.paths.data = Path(self.temp_dir)

        with patch('fichero.config.core.state_manager.StateManager._get_state_file_path',
                   return_value=self.state_file):
            self.state_manager = StateManager(self.mock_app)

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_active_settings_file(self):
        """Test active settings file getter/setter"""
        self.state_manager.set_active_settings_file("/path/to/settings.yml")
        result = self.state_manager.get_active_settings_file()
        self.assertEqual(result, "/path/to/settings.yml")

    def test_recent_documents(self):
        """Test recent documents management"""
        self.state_manager.add_recent_document("/path/to/doc1.pdf")
        self.state_manager.add_recent_document("/path/to/doc2.pdf")
        self.state_manager.add_recent_document("/path/to/doc3.pdf")

        recent = self.state_manager.get_recent_documents()

        # Most recent should be first
        self.assertEqual(len(recent), 3)
        self.assertEqual(recent[0], "/path/to/doc3.pdf")
        self.assertEqual(recent[1], "/path/to/doc2.pdf")
        self.assertEqual(recent[2], "/path/to/doc1.pdf")

    def test_recent_documents_max_limit(self):
        """Test that recent documents are limited to 10"""
        for i in range(15):
            self.state_manager.add_recent_document(f"/path/to/doc{i}.pdf")

        recent = self.state_manager.get_recent_documents()
        self.assertEqual(len(recent), 10)
        # Most recent should be first (doc14)
        self.assertEqual(recent[0], "/path/to/doc14.pdf")

    def test_recent_documents_no_duplicates(self):
        """Test that adding duplicate moves to front"""
        self.state_manager.add_recent_document("/path/to/doc1.pdf")
        self.state_manager.add_recent_document("/path/to/doc2.pdf")
        self.state_manager.add_recent_document("/path/to/doc1.pdf")  # Re-add doc1

        recent = self.state_manager.get_recent_documents()

        self.assertEqual(len(recent), 2)
        self.assertEqual(recent[0], "/path/to/doc1.pdf")  # doc1 moved to front

    def test_open_documents(self):
        """Test open documents getter/setter"""
        docs = ["/path/to/doc1.pdf", "/path/to/doc2.pdf"]
        self.state_manager.set_open_documents(docs)

        result = self.state_manager.get_open_documents()
        self.assertEqual(result, docs)

    def test_last_used_directory(self):
        """Test last used directory getter/setter"""
        self.state_manager.set_last_used_directory("import", "/home/user/Documents")
        self.state_manager.set_last_used_directory("export", "/home/user/Exports")

        self.assertEqual(
            self.state_manager.get_last_used_directory("import"),
            "/home/user/Documents"
        )
        self.assertEqual(
            self.state_manager.get_last_used_directory("export"),
            "/home/user/Exports"
        )

    def test_preferred_plan(self):
        """Test preferred plan getter/setter"""
        self.state_manager.set_preferred_plan("Transcribe")
        self.assertEqual(self.state_manager.get_preferred_plan(), "Transcribe")

    def test_preferred_workflow(self):
        """Test preferred workflow getter/setter"""
        self.state_manager.set_preferred_workflow("Catalogue")
        self.assertEqual(self.state_manager.get_preferred_workflow(), "Catalogue")


class TestStateManagerV3PreviewViewerState(unittest.TestCase):
    """Test preview viewer state in StateManager v3.0"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "app_state.json"

        from fichero.config.core.state_manager import StateManager

        self.mock_app = Mock()
        self.mock_app.paths = Mock()
        self.mock_app.paths.data = Path(self.temp_dir)

        with patch('fichero.config.core.state_manager.StateManager._get_state_file_path',
                   return_value=self.state_file):
            self.state_manager = StateManager(self.mock_app)

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_default_viewer_state(self):
        """Test getting default viewer state"""
        state = self.state_manager.get_preview_viewer_state()

        self.assertEqual(state["scale"], 1.0)
        self.assertEqual(state["rotation"], 0)
        self.assertEqual(state["scroll_x"], 0)
        self.assertEqual(state["scroll_y"], 0)

    def test_set_viewer_state(self):
        """Test setting viewer state"""
        viewer_state = {
            "scale": 2.5,
            "rotation": 90,
            "scroll_x": 150,
            "scroll_y": 200
        }

        self.state_manager.set_preview_viewer_state(viewer_state)
        result = self.state_manager.get_preview_viewer_state()

        self.assertEqual(result["scale"], 2.5)
        self.assertEqual(result["rotation"], 90)
        self.assertEqual(result["scroll_x"], 150)
        self.assertEqual(result["scroll_y"], 200)

    def test_reset_viewer_state(self):
        """Test resetting viewer state to defaults"""
        # Set custom state
        self.state_manager.set_preview_viewer_state({
            "scale": 3.0,
            "rotation": 180,
            "scroll_x": 500,
            "scroll_y": 600
        })

        # Reset
        self.state_manager.reset_preview_viewer_state()
        result = self.state_manager.get_preview_viewer_state()

        self.assertEqual(result["scale"], 1.0)
        self.assertEqual(result["rotation"], 0)
        self.assertEqual(result["scroll_x"], 0)
        self.assertEqual(result["scroll_y"], 0)


class TestStateManagerV3PaneContent(unittest.TestCase):
    """Test pane content tracking in StateManager v3.0"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "app_state.json"

        from fichero.config.core.state_manager import StateManager

        self.mock_app = Mock()
        self.mock_app.paths = Mock()
        self.mock_app.paths.data = Path(self.temp_dir)

        with patch('fichero.config.core.state_manager.StateManager._get_state_file_path',
                   return_value=self.state_file):
            self.state_manager = StateManager(self.mock_app)

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_pane_content_defaults(self):
        """Test getting default pane content"""
        library_content = self.state_manager.get_pane_content("library")

        self.assertIsNone(library_content.get("selected_collection_id"))
        self.assertEqual(library_content.get("scroll_position"), 0)

    def test_set_library_selected_collection(self):
        """Test setting library selected collection"""
        self.state_manager.set_library_selected_collection("collection-123")

        content = self.state_manager.get_library_pane_content()
        self.assertEqual(content["selected_collection_id"], "collection-123")

    def test_set_collection_pane_state(self):
        """Test setting collection pane state"""
        self.state_manager.set_collection_pane_state("collection-123", "item-456")

        content = self.state_manager.get_collection_pane_content()
        self.assertEqual(content["collection_id"], "collection-123")
        self.assertEqual(content["selected_item_id"], "item-456")

    def test_set_preview_item_id(self):
        """Test setting preview item ID (updates both panes)"""
        self.state_manager.set_preview_item_id("item-789")

        image_content = self.state_manager.get_pane_content("preview_image")
        metadata_content = self.state_manager.get_pane_content("preview_metadata")

        self.assertEqual(image_content["item_id"], "item-789")
        self.assertEqual(metadata_content["item_id"], "item-789")

    def test_set_adjust_pane_state(self):
        """Test setting adjust pane state"""
        self.state_manager.set_adjust_pane_state("item-123", "transcription")

        content = self.state_manager.get_adjust_pane_content()
        self.assertEqual(content["item_id"], "item-123")
        self.assertEqual(content["active_tab"], "transcription")

    def test_pane_scroll_position(self):
        """Test setting and getting pane scroll positions"""
        self.state_manager.set_pane_scroll_position("collection", 500)
        self.state_manager.set_pane_scroll_position("preview_metadata", 200)

        self.assertEqual(
            self.state_manager.get_pane_scroll_position("collection"),
            500
        )
        self.assertEqual(
            self.state_manager.get_pane_scroll_position("preview_metadata"),
            200
        )

    def test_update_pane_content(self):
        """Test updating specific fields in pane content"""
        self.state_manager.update_pane_content(
            "collection",
            collection_id="col-1",
            selected_item_id="item-1",
            scroll_position=100
        )

        content = self.state_manager.get_pane_content("collection")
        self.assertEqual(content["collection_id"], "col-1")
        self.assertEqual(content["selected_item_id"], "item-1")
        self.assertEqual(content["scroll_position"], 100)


class TestStateManagerV3Migration(unittest.TestCase):
    """Test migration from v2.0 to v3.0"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "app_state.json"
        self.prefs_file = Path(self.temp_dir) / "app_preferences.json"

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_migrate_from_v2_adds_new_sections(self):
        """Test that migration from v2.0 adds new v3.0 sections"""
        # Create v2.0 state file
        v2_state = {
            "version": "2.0",
            "session": {
                "last_collection_id": "col-123",
                "last_item_id": "item-456"
            },
            "window": {"size": [1200, 800]},
            "pane_visibility": {"sidebar": True, "collection": True}
        }

        with open(self.state_file, 'w') as f:
            json.dump(v2_state, f)

        # Load with StateManager (should trigger migration)
        from fichero.config.core.state_manager import StateManager

        mock_app = Mock()
        mock_app.paths = Mock()
        mock_app.paths.data = Path(self.temp_dir)

        with patch('fichero.config.core.state_manager.StateManager._get_state_file_path',
                   return_value=self.state_file):
            state_manager = StateManager(mock_app)

        # Check new sections were added
        self.assertIsNotNone(state_manager.get_all_window_states())
        self.assertIsNotNone(state_manager.get_preview_viewer_state())
        self.assertIsNotNone(state_manager.get_pane_content("library"))

        # Check existing data preserved
        self.assertEqual(state_manager.get_last_collection_id(), "col-123")
        self.assertEqual(state_manager.get_last_item_id(), "item-456")

    def test_migrate_app_preferences(self):
        """Test migration of app_preferences.json"""
        # Create v2.0 state file
        v2_state = {"version": "2.0", "session": {}}
        with open(self.state_file, 'w') as f:
            json.dump(v2_state, f)

        # Create app_preferences.json
        old_prefs = {
            "active_settings_file": "/path/to/settings.yml",
            "recent_documents": ["/doc1.pdf", "/doc2.pdf"],
            "preferred_plan": "Transcribe",
            "window_positions": {
                "main": {"x": 100, "y": 100, "width": 1200, "height": 800}
            }
        }
        with open(self.prefs_file, 'w') as f:
            json.dump(old_prefs, f)

        # Load with StateManager (should migrate preferences)
        from fichero.config.core.state_manager import StateManager

        mock_app = Mock()
        mock_app.paths = Mock()
        mock_app.paths.data = Path(self.temp_dir)

        with patch('fichero.config.core.state_manager.StateManager._get_state_file_path',
                   return_value=self.state_file):
            state_manager = StateManager(mock_app)

        # Check preferences were migrated
        self.assertEqual(
            state_manager.get_active_settings_file(),
            "/path/to/settings.yml"
        )
        self.assertEqual(
            state_manager.get_recent_documents(),
            ["/doc1.pdf", "/doc2.pdf"]
        )
        self.assertEqual(state_manager.get_preferred_plan(), "Transcribe")

        # Check window positions were migrated
        main_window_state = state_manager.get_window_state("main")
        self.assertIsNotNone(main_window_state)
        self.assertEqual(main_window_state["x"], 100)

        # Check old file was renamed
        self.assertFalse(self.prefs_file.exists())
        migrated_file = self.prefs_file.with_suffix('.json.migrated')
        self.assertTrue(migrated_file.exists())


class TestWindowStateTracker(unittest.TestCase):
    """Test WindowStateTracker class"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "app_state.json"

        from fichero.config.core.state_manager import StateManager

        self.mock_app = Mock()
        self.mock_app.paths = Mock()
        self.mock_app.paths.data = Path(self.temp_dir)

        with patch('fichero.config.core.state_manager.StateManager._get_state_file_path',
                   return_value=self.state_file):
            self.state_manager = StateManager(self.mock_app)

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_window_state_dataclass(self):
        """Test WindowState dataclass"""
        from fichero.shared.utils.window_state_tracker import WindowState

        state = WindowState(
            x=100,
            y=200,
            width=1200,
            height=800,
            is_visible=True,
            is_minimized=False,
            display_id=12345
        )

        self.assertEqual(state.x, 100)
        self.assertEqual(state.y, 200)
        self.assertEqual(state.width, 1200)
        self.assertEqual(state.height, 800)
        self.assertTrue(state.is_visible)
        self.assertFalse(state.is_minimized)
        self.assertEqual(state.display_id, 12345)

    def test_window_state_to_dict(self):
        """Test WindowState.to_dict()"""
        from fichero.shared.utils.window_state_tracker import WindowState

        state = WindowState(x=100, y=200, width=800, height=600)
        state_dict = state.to_dict()

        self.assertIsInstance(state_dict, dict)
        self.assertEqual(state_dict["x"], 100)
        self.assertEqual(state_dict["y"], 200)
        self.assertEqual(state_dict["width"], 800)
        self.assertEqual(state_dict["height"], 600)

    def test_window_state_from_dict(self):
        """Test WindowState.from_dict()"""
        from fichero.shared.utils.window_state_tracker import WindowState

        data = {
            "x": 100,
            "y": 200,
            "width": 1200,
            "height": 800,
            "is_visible": True,
            "is_minimized": False
        }

        state = WindowState.from_dict(data)

        self.assertEqual(state.x, 100)
        self.assertEqual(state.y, 200)
        self.assertEqual(state.width, 1200)
        self.assertEqual(state.height, 800)

    def test_tracker_initialization(self):
        """Test WindowStateTracker initialization"""
        from fichero.shared.utils.window_state_tracker import WindowStateTracker

        tracker = WindowStateTracker(self.state_manager)

        self.assertEqual(len(tracker.get_tracked_window_ids()), 0)

    def test_tracker_register_mock_window(self):
        """Test registering a mock window"""
        from fichero.shared.utils.window_state_tracker import WindowStateTracker

        tracker = WindowStateTracker(self.state_manager)

        # Create a mock Toga window
        mock_window = Mock()
        mock_window.position = (100, 200)
        mock_window.size = (800, 600)
        mock_window.visible = True

        tracker.register_window("test_window", mock_window, restore=False)

        self.assertIn("test_window", tracker.get_tracked_window_ids())

    def test_tracker_get_toga_state(self):
        """Test getting state via Toga APIs (non-macOS fallback)"""
        from fichero.shared.utils.window_state_tracker import WindowStateTracker

        tracker = WindowStateTracker(self.state_manager)

        # Create mock window without native impl
        mock_window = Mock()
        mock_window.position = (100, 200)
        mock_window.size = (800, 600)
        mock_window.visible = True

        # Remove _impl attribute to force Toga fallback
        del mock_window._impl

        tracker.register_window("test_window", mock_window, restore=False)
        state = tracker.get_window_state("test_window")

        self.assertIsNotNone(state)
        self.assertEqual(state.x, 100)
        self.assertEqual(state.y, 200)
        self.assertEqual(state.width, 800)
        self.assertEqual(state.height, 600)

    def test_tracker_save_all_states(self):
        """Test saving all window states"""
        from fichero.shared.utils.window_state_tracker import WindowStateTracker

        tracker = WindowStateTracker(self.state_manager)

        # Keep references to prevent garbage collection (uses weak refs internally)
        mock_windows = []

        # Register multiple windows
        for i, window_id in enumerate(["main", "inspector", "settings"]):
            mock_window = Mock()
            mock_window.position = (i * 100, i * 50)
            mock_window.size = (800 + i * 100, 600 + i * 50)
            mock_window.visible = True
            del mock_window._impl
            mock_windows.append(mock_window)  # Keep reference
            tracker.register_window(window_id, mock_window, restore=False)

        tracker.save_all_states()

        # Verify states were saved to state_manager
        self.assertIsNotNone(self.state_manager.get_window_state("main"))
        self.assertIsNotNone(self.state_manager.get_window_state("inspector"))
        self.assertIsNotNone(self.state_manager.get_window_state("settings"))


class TestStateManagerStatePersistence(unittest.TestCase):
    """Test state persistence across saves/loads"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "app_state.json"

    def tearDown(self):
        """Clean up test fixtures"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_state_persists_after_save(self):
        """Test that state persists after save and reload"""
        from fichero.config.core.state_manager import StateManager

        mock_app = Mock()
        mock_app.paths = Mock()
        mock_app.paths.data = Path(self.temp_dir)

        # Create first instance and set state
        with patch('fichero.config.core.state_manager.StateManager._get_state_file_path',
                   return_value=self.state_file):
            sm1 = StateManager(mock_app)

        sm1.set_window_state("main", {"x": 100, "y": 200, "width": 1200, "height": 800})
        sm1.set_preview_viewer_state({"scale": 2.0, "rotation": 90, "scroll_x": 50, "scroll_y": 100})
        sm1.set_preferred_plan("Transcribe")
        sm1._save_state_sync()

        # Create second instance and verify state was restored
        with patch('fichero.config.core.state_manager.StateManager._get_state_file_path',
                   return_value=self.state_file):
            sm2 = StateManager(mock_app)

        self.assertEqual(sm2.get_window_state("main")["x"], 100)
        self.assertEqual(sm2.get_preview_viewer_state()["scale"], 2.0)
        self.assertEqual(sm2.get_preferred_plan(), "Transcribe")


if __name__ == '__main__':
    unittest.main()
