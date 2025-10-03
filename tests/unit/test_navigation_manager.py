"""
Unit tests for NavigationManager

Tests the mobile platform detection fix and NavigationController integration.
"""

import unittest
from unittest.mock import MagicMock, patch
import os
import logging

# Set up logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TestNavigationManager(unittest.TestCase):
    """Test suite for NavigationManager class"""

    def setUp(self):
        """Set up test environment"""
        self.app = MagicMock()
        self.app.library_service = MagicMock()

    def test_detect_mobile_platform_with_environment_variable_true(self):
        """Test mobile detection with FORCE_MOBILE_UI=true"""
        with patch.dict(os.environ, {'FORCE_MOBILE_UI': 'true'}):
            from fichero.shared.navigation.navigation_manager import NavigationManager

            manager = NavigationManager(self.app)
            result = manager._detect_mobile_platform()

            self.assertTrue(result)

    def test_detect_mobile_platform_with_environment_variable_false(self):
        """Test mobile detection with FORCE_MOBILE_UI=false"""
        with patch.dict(os.environ, {'FORCE_MOBILE_UI': 'false'}):
            from fichero.shared.navigation.navigation_manager import NavigationManager

            manager = NavigationManager(self.app)
            result = manager._detect_mobile_platform()

            self.assertFalse(result)

    def test_detect_mobile_platform_with_environment_variable_1(self):
        """Test mobile detection with FORCE_MOBILE_UI=1"""
        with patch.dict(os.environ, {'FORCE_MOBILE_UI': '1'}):
            from fichero.shared.navigation.navigation_manager import NavigationManager

            manager = NavigationManager(self.app)
            result = manager._detect_mobile_platform()

            self.assertTrue(result)

    def test_detect_mobile_platform_with_ios_platform(self):
        """Test mobile detection with iOS platform"""
        # Remove environment variable
        with patch.dict(os.environ, {}, clear=True):
            with patch('toga.platform.current_platform', 'iOS'):
                from fichero.shared.navigation.navigation_manager import NavigationManager

                manager = NavigationManager(self.app)
                result = manager._detect_mobile_platform()

                self.assertTrue(result)

    def test_detect_mobile_platform_with_android_platform(self):
        """Test mobile detection with android platform"""
        # Remove environment variable
        with patch.dict(os.environ, {}, clear=True):
            with patch('toga.platform.current_platform', 'android'):
                from fichero.shared.navigation.navigation_manager import NavigationManager

                manager = NavigationManager(self.app)
                result = manager._detect_mobile_platform()

                self.assertTrue(result)

    def test_detect_mobile_platform_with_desktop_platform(self):
        """Test mobile detection with macOS (desktop) platform"""
        # Remove environment variable
        with patch.dict(os.environ, {}, clear=True):
            with patch('toga.platform.current_platform', 'macOS'):
                from fichero.shared.navigation.navigation_manager import NavigationManager

                manager = NavigationManager(self.app)
                result = manager._detect_mobile_platform()

                self.assertFalse(result)

    def test_detect_mobile_platform_exception_handling(self):
        """Test mobile detection with exception during platform detection"""
        # Remove environment variable
        with patch.dict(os.environ, {}, clear=True):
            with patch('toga.platform.current_platform', side_effect=Exception("Test error")):
                from fichero.shared.navigation.navigation_manager import NavigationManager

                manager = NavigationManager(self.app)
                result = manager._detect_mobile_platform()

                # Should default to False (desktop) on exception
                self.assertFalse(result)

    def test_navigation_controller_initialization_with_mobile_true(self):
        """Test that NavigationController is initialized with correct mobile value (True)"""
        with patch.dict(os.environ, {'FORCE_MOBILE_UI': 'true'}):
            from fichero.shared.navigation.navigation_manager import NavigationManager

            manager = NavigationManager(self.app)
            success = manager.initialize()

            self.assertTrue(success)
            self.assertIsNotNone(manager.navigation_controller)
            # Check that NavigationController was initialized with mobile=True
            self.assertTrue(manager.navigation_controller.is_mobile)

    def test_navigation_controller_initialization_with_mobile_false(self):
        """Test that NavigationController is initialized with correct mobile value (False)"""
        with patch.dict(os.environ, {'FORCE_MOBILE_UI': 'false'}):
            from fichero.shared.navigation.navigation_manager import NavigationManager

            manager = NavigationManager(self.app)
            success = manager.initialize()

            self.assertTrue(success)
            self.assertIsNotNone(manager.navigation_controller)
            # Check that NavigationController was initialized with mobile=False
            self.assertFalse(manager.navigation_controller.is_mobile)

    def test_initialization_failure_without_library_service(self):
        """Test initialization failure when library_service is not available"""
        app_without_service = MagicMock()
        del app_without_service.library_service

        from fichero.shared.navigation.navigation_manager import NavigationManager

        manager = NavigationManager(app_without_service)
        success = manager.initialize()

        self.assertFalse(success)
        self.assertIsNone(manager.navigation_controller)

    def test_viewmodels_initialization(self):
        """Test that ViewModels are properly initialized"""
        with patch.dict(os.environ, {'FORCE_MOBILE_UI': 'true'}):
            from fichero.shared.navigation.navigation_manager import NavigationManager

            manager = NavigationManager(self.app)
            success = manager.initialize()

            self.assertTrue(success)
            self.assertIsNotNone(manager.library_viewmodel)
            self.assertIsNotNone(manager.collection_viewmodel)

    def test_get_navigation_controller(self):
        """Test getting the navigation controller"""
        with patch.dict(os.environ, {'FORCE_MOBILE_UI': 'true'}):
            from fichero.shared.navigation.navigation_manager import NavigationManager

            manager = NavigationManager(self.app)
            manager.initialize()

            controller = manager.get_navigation_controller()

            self.assertIsNotNone(controller)
            self.assertEqual(controller, manager.navigation_controller)

    def test_get_navigation_controller_before_initialization(self):
        """Test getting navigation controller before initialization"""
        from fichero.shared.navigation.navigation_manager import NavigationManager

        manager = NavigationManager(self.app)
        controller = manager.get_navigation_controller()

        self.assertIsNone(controller)


if __name__ == '__main__':
    unittest.main()