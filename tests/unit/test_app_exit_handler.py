"""
Unit tests for FicheroApp exit handler.

Tests the on_exit handler mechanism that ensures state is saved when the app closes.
This is CRITICAL for window state persistence - without it, finalize() is never called.

The fix addressed:
- Root cause: finalize() existed but was never connected to Toga's on_exit handler
- Symptom: Window size/position and pane visibility not restoring on app relaunch
- Solution: Added _handle_exit() method and connected it via self.on_exit = self._handle_exit
"""

import unittest
from unittest.mock import Mock, MagicMock, patch, call
import tempfile
import shutil
from pathlib import Path


class TestAppExitHandler(unittest.TestCase):
    """Test the _handle_exit method and on_exit registration"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_handle_exit_calls_finalize(self):
        """Test that _handle_exit calls finalize()"""
        # Create a mock app with finalize method
        mock_app = Mock()
        mock_app.finalize = Mock()
        mock_app._is_gui_only_mode = Mock(return_value=True)

        # Import the method directly to test it
        from fichero.app import FicheroApp

        # Create a mock instance with the _handle_exit method bound
        # We need to call the method as if it were bound to the mock_app
        handle_exit = FicheroApp._handle_exit.__get__(mock_app, FicheroApp)

        # Call the handler
        result = handle_exit(mock_app)

        # Verify finalize was called
        mock_app.finalize.assert_called_once()

        # Verify handler returns True (allows exit)
        self.assertTrue(result)

    def test_handle_exit_returns_true_always(self):
        """Test that _handle_exit always returns True to allow exit"""
        mock_app = Mock()
        mock_app.finalize = Mock()
        mock_app._is_gui_only_mode = Mock(return_value=True)

        from fichero.app import FicheroApp
        handle_exit = FicheroApp._handle_exit.__get__(mock_app, FicheroApp)

        result = handle_exit(mock_app)

        self.assertTrue(result)

    def test_handle_exit_handles_finalize_exception(self):
        """Test that _handle_exit handles exceptions in finalize gracefully"""
        mock_app = Mock()
        mock_app.finalize = Mock(side_effect=Exception("Test error"))
        mock_app._is_gui_only_mode = Mock(return_value=True)

        from fichero.app import FicheroApp
        handle_exit = FicheroApp._handle_exit.__get__(mock_app, FicheroApp)

        # Should not raise exception
        result = handle_exit(mock_app)

        # Should still return True to allow exit
        self.assertTrue(result)

        # Finalize should have been attempted
        mock_app.finalize.assert_called_once()

    def test_handle_exit_accepts_kwargs(self):
        """Test that _handle_exit accepts additional kwargs from Toga"""
        mock_app = Mock()
        mock_app.finalize = Mock()
        mock_app._is_gui_only_mode = Mock(return_value=True)

        from fichero.app import FicheroApp
        handle_exit = FicheroApp._handle_exit.__get__(mock_app, FicheroApp)

        # Toga may pass additional kwargs
        result = handle_exit(mock_app, some_kwarg="value")

        # Should work without error
        self.assertTrue(result)


class TestFinalizeStateSaving(unittest.TestCase):
    """Test that finalize() properly saves state"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_finalize_saves_window_state(self):
        """Test that finalize() saves window state via WindowStateTracker"""
        # Create mock app with all necessary components
        mock_app = Mock()
        mock_app._is_gui_only_mode = Mock(return_value=True)

        # Mock window state tracker
        mock_tracker = Mock()
        mock_app.window_state_tracker = mock_tracker

        # Mock state manager
        mock_state_manager = Mock()
        mock_app.state_manager = mock_state_manager

        # Mock main window wrapper
        mock_app.main_window_wrapper = Mock()
        mock_app.main_window_wrapper._save_window_state = Mock()

        # No other components
        mock_app.initializer = None
        mock_app.view_integration = None

        from fichero.app import FicheroApp
        finalize = FicheroApp.finalize.__get__(mock_app, FicheroApp)

        # Call finalize
        finalize()

        # Verify window state tracker saved all states
        mock_tracker.save_all_states.assert_called_once()

        # Verify state manager persisted to disk
        mock_state_manager.save_state_sync.assert_called_once()

    def test_finalize_saves_main_window_layout(self):
        """Test that finalize() saves main window layout state"""
        mock_app = Mock()
        mock_app._is_gui_only_mode = Mock(return_value=True)
        mock_app.window_state_tracker = Mock()
        mock_app.state_manager = Mock()
        mock_app.initializer = None
        mock_app.view_integration = None

        # Mock main window wrapper with _save_window_state
        mock_main_window = Mock()
        mock_app.main_window_wrapper = mock_main_window

        from fichero.app import FicheroApp
        finalize = FicheroApp.finalize.__get__(mock_app, FicheroApp)

        finalize()

        # Verify main window layout state was saved
        mock_main_window._save_window_state.assert_called_once()

    def test_finalize_handles_missing_components_gracefully(self):
        """Test that finalize() handles missing components gracefully"""
        mock_app = Mock()
        mock_app._is_gui_only_mode = Mock(return_value=True)

        # Set components to None to simulate missing
        mock_app.window_state_tracker = None
        mock_app.state_manager = None
        mock_app.main_window_wrapper = None
        mock_app.initializer = None
        mock_app.view_integration = None

        from fichero.app import FicheroApp
        finalize = FicheroApp.finalize.__get__(mock_app, FicheroApp)

        # Should not raise exception even with missing components
        finalize()


class TestOnExitRegistration(unittest.TestCase):
    """Test that on_exit handler is properly registered"""

    def test_exit_handler_exists(self):
        """Test that _handle_exit method exists on FicheroApp"""
        from fichero.app import FicheroApp

        self.assertTrue(hasattr(FicheroApp, '_handle_exit'))
        self.assertTrue(callable(getattr(FicheroApp, '_handle_exit')))

    def test_handle_exit_signature(self):
        """Test that _handle_exit has correct signature for Toga on_exit"""
        from fichero.app import FicheroApp
        import inspect

        sig = inspect.signature(FicheroApp._handle_exit)
        params = list(sig.parameters.keys())

        # Should accept self, app, and **kwargs
        self.assertIn('self', params)
        self.assertIn('app', params)
        self.assertIn('kwargs', params)

    def test_handle_exit_docstring(self):
        """Test that _handle_exit has informative docstring"""
        from fichero.app import FicheroApp

        docstring = FicheroApp._handle_exit.__doc__
        self.assertIsNotNone(docstring)
        self.assertIn('on_exit', docstring.lower())


class TestStateManagerIntegration(unittest.TestCase):
    """Integration tests for state manager with exit handler"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "app_state.json"

    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_state_file_created_on_save(self):
        """Test that app_state.json is created when state is saved"""
        from fichero.config.core.state_manager import StateManager

        mock_app = Mock()
        mock_app.paths = Mock()
        mock_app.paths.data = Path(self.temp_dir)

        with patch('fichero.config.core.state_manager.StateManager._get_state_file_path',
                   return_value=self.state_file):
            state_manager = StateManager(mock_app)

        # Set some state
        state_manager.set_window_state("main", {
            "x": 100, "y": 200, "width": 1200, "height": 800
        })
        state_manager.set_pane_visibility("library", False)
        state_manager.set_pane_visibility("adjust", True)

        # Save state
        state_manager.save_state_sync()

        # Verify file was created
        self.assertTrue(self.state_file.exists())

        # Verify content
        import json
        with open(self.state_file) as f:
            saved_state = json.load(f)

        self.assertEqual(saved_state["windows"]["main"]["x"], 100)
        self.assertFalse(saved_state["pane_visibility"]["library"])
        self.assertTrue(saved_state["pane_visibility"]["adjust"])

    def test_state_restored_on_load(self):
        """Test that state is restored when StateManager loads"""
        from fichero.config.core.state_manager import StateManager

        mock_app = Mock()
        mock_app.paths = Mock()
        mock_app.paths.data = Path(self.temp_dir)

        # Create first instance and save state
        with patch('fichero.config.core.state_manager.StateManager._get_state_file_path',
                   return_value=self.state_file):
            sm1 = StateManager(mock_app)

        sm1.set_window_state("main", {"x": 500, "y": 300, "width": 1400, "height": 900})
        sm1.set_pane_visibility("previewimage", False)
        sm1.set_pane_visibility("previewmetadata", False)
        sm1.save_state_sync()

        # Create second instance - should load saved state
        with patch('fichero.config.core.state_manager.StateManager._get_state_file_path',
                   return_value=self.state_file):
            sm2 = StateManager(mock_app)

        # Verify state was restored
        main_state = sm2.get_window_state("main")
        self.assertEqual(main_state["x"], 500)
        self.assertEqual(main_state["y"], 300)
        self.assertEqual(main_state["width"], 1400)
        self.assertEqual(main_state["height"], 900)

        self.assertFalse(sm2.get_pane_visibility("previewimage"))
        self.assertFalse(sm2.get_pane_visibility("previewmetadata"))


class TestWindowStateTrackerIntegration(unittest.TestCase):
    """Integration tests for WindowStateTracker with exit handler"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "app_state.json"

    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_tracker_saves_to_state_manager(self):
        """Test that WindowStateTracker saves state to StateManager"""
        from fichero.config.core.state_manager import StateManager
        from fichero.shared.utils.window_state_tracker import WindowStateTracker

        mock_app = Mock()
        mock_app.paths = Mock()
        mock_app.paths.data = Path(self.temp_dir)

        with patch('fichero.config.core.state_manager.StateManager._get_state_file_path',
                   return_value=self.state_file):
            state_manager = StateManager(mock_app)

        tracker = WindowStateTracker(state_manager)

        # Create mock window
        mock_window = Mock()
        mock_window.position = (100, 200)
        mock_window.size = (800, 600)
        mock_window.visible = True
        del mock_window._impl  # Force Toga fallback

        # Register and save
        tracker.register_window("test", mock_window, restore=False)
        tracker.save_window_state("test", persist_to_disk=False)

        # Verify state was saved to state manager
        saved_state = state_manager.get_window_state("test")
        self.assertIsNotNone(saved_state)
        self.assertEqual(saved_state["x"], 100)
        self.assertEqual(saved_state["y"], 200)
        self.assertEqual(saved_state["width"], 800)
        self.assertEqual(saved_state["height"], 600)


if __name__ == '__main__':
    unittest.main()
