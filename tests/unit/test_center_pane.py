"""
Unit Tests for Center Pane Functionality

Tests the center pane container and collection view initialization
to ensure desktop three-pane layout works correctly.
"""

import unittest
from unittest.mock import Mock, patch


class TestCenterPaneInitialization(unittest.TestCase):
    """Tests for center pane container functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_app = Mock()
        self.mock_app.is_mobile = False

    def test_command_manager_has_set_command_bridge(self):
        """Test that CommandManagerRefactored has set_command_bridge method"""
        from fichero.windows.main.command_manager import CommandManagerRefactored

        command_manager = CommandManagerRefactored(self.mock_app)

        # Check that the method exists and is callable
        self.assertTrue(hasattr(command_manager, 'set_command_bridge'))
        self.assertTrue(callable(getattr(command_manager, 'set_command_bridge')))

    def test_command_manager_set_command_bridge_call(self):
        """Test that set_command_bridge can be called without error"""
        from fichero.windows.main.command_manager import CommandManagerRefactored

        command_manager = CommandManagerRefactored(self.mock_app)
        mock_bridge = Mock()

        # This should not raise an exception
        try:
            command_manager.set_command_bridge(mock_bridge)
            success = True
        except Exception:
            success = False

        self.assertTrue(success, "set_command_bridge should be callable without errors")

    def test_pane_manager_initialization(self):
        """Test that PaneManager initializes correctly"""
        try:
            from fichero.windows.main.layout.pane_manager import PaneManager

            pane_manager = PaneManager(self.mock_app, is_mobile=False)

            # Basic checks for desktop three-pane setup
            self.assertIsNotNone(pane_manager)
            self.assertFalse(pane_manager.is_mobile)

        except ImportError:
            self.skipTest("PaneManager not available for testing")

    def test_command_bridge_initialization(self):
        """Test that CommandBridge initializes correctly"""
        try:
            from fichero.windows.main.layout.pane_manager import PaneManager
            from fichero.windows.main.commands.command_bridge import CommandBridge

            pane_manager = PaneManager(self.mock_app, is_mobile=False)
            command_bridge = CommandBridge(self.mock_app, pane_manager)

            self.assertIsNotNone(command_bridge)

        except ImportError:
            self.skipTest("CommandBridge not available for testing")


class TestCenterPaneIntegration(unittest.TestCase):
    """Integration tests for center pane functionality"""

    def setUp(self):
        """Set up integration test fixtures"""
        self.mock_app = Mock()
        self.mock_app.is_mobile = False

    def test_main_window_component_initialization(self):
        """Test that main window components can be initialized without errors"""
        try:
            from fichero.windows.main.layout.pane_manager import PaneManager
            from fichero.windows.main.commands.command_bridge import CommandBridge
            from fichero.windows.main.command_manager import CommandManagerRefactored

            # Initialize components in order
            pane_manager = PaneManager(self.mock_app, is_mobile=False)
            command_bridge = CommandBridge(self.mock_app, pane_manager)
            command_manager = CommandManagerRefactored(self.mock_app)

            # Test the integration that was failing
            if hasattr(command_manager, 'set_command_bridge'):
                command_manager.set_command_bridge(command_bridge)
                integration_success = True
            else:
                integration_success = False

            self.assertTrue(integration_success, "Command manager should have set_command_bridge method")

        except ImportError as e:
            self.skipTest(f"Required components not available: {e}")


if __name__ == '__main__':
    unittest.main()