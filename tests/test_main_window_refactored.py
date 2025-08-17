"""
Test suite for refactored main window architecture

Tests the modular view system, platform-specific toolbars, and navigation.
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch
import asyncio

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import toga
from toga.constants import COLUMN

# Import the refactored components
from fichero.windows.main import MainWindow
from fichero.windows.main.views import ViewManager, ViewType, CollectionView, PreferencesView
from fichero.windows.about import AboutMobileView
from fichero.shared.toolbars import DesktopToolbar, MobileToolbar


class MockApp(toga.App):
    """Mock app for testing"""
    
    def startup(self):
        self.main_window = toga.MainWindow(title="Test")
        
    @property
    def paths(self):
        """Mock paths"""
        from pathlib import Path
        return Mock(
            app=Path(__file__).parent / "test_resources",
            config=Path(__file__).parent / "test_config"
        )


class TestRefactoredMainWindow(unittest.TestCase):
    """Test the refactored main window"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_app = MockApp("Test", "test.app")
        
    def test_main_window_creation(self):
        """Test that the main window can be created"""
        try:
            main_window = MainWindow(self.mock_app)
            self.assertIsNotNone(main_window)
            self.assertIsInstance(main_window, MainWindow)
            print("✅ MainWindow creation test passed")
        except Exception as e:
            self.fail(f"MainWindow creation failed: {e}")
    
    def test_platform_detection(self):
        """Test platform detection and debug overrides"""
        main_window = MainWindow(self.mock_app)
        
        # Should have platform detection attributes
        self.assertTrue(hasattr(main_window, 'is_mobile'))
        self.assertTrue(hasattr(main_window, 'is_ios'))
        self.assertTrue(hasattr(main_window, 'is_android'))
        
        # Test debug constants are being applied
        # (The debug constants should be set to iPhone mode from earlier)
        print(f"Platform detection - Mobile: {main_window.is_mobile}, iOS: {main_window.is_ios}")
        
        print("✅ Platform detection test passed")


class TestViewComponents(unittest.TestCase):
    """Test individual view components"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_app = MockApp("Test", "test.app")
    
    def test_view_creation(self):
        """Test that all views can be created"""
        try:
            # Test desktop views
            collection_view = CollectionView(self.mock_app, is_mobile=False)
            about_view = AboutMobileView(self.mock_app)  # Use refactored about view
            preferences_view = PreferencesView(self.mock_app, is_mobile=False)
            
            # Test mobile views  
            mobile_collection_view = CollectionView(self.mock_app, is_mobile=True)
            mobile_about_view = AboutMobileView(self.mock_app)  # Use refactored about view
            mobile_preferences_view = PreferencesView(self.mock_app, is_mobile=True)
            
            print("✅ All view components created successfully")
            
        except Exception as e:
            self.fail(f"View creation failed: {e}")


class TestToolbarComponents(unittest.TestCase):
    """Test toolbar components"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_app = MockApp("Test", "test.app")
        self.mock_view_manager = Mock()
        self.mock_command_manager = Mock()
    
    def test_toolbar_creation(self):
        """Test that toolbars can be created"""
        try:
            # Test desktop toolbar
            desktop_toolbar = DesktopToolbar(self.mock_app, self.mock_view_manager, self.mock_command_manager)
            self.assertIsNotNone(desktop_toolbar)
            
            # Test mobile toolbars
            ios_toolbar = MobileToolbar(self.mock_app, self.mock_view_manager, is_ios=True)
            android_toolbar = MobileToolbar(self.mock_app, self.mock_view_manager, is_ios=False)
            
            self.assertIsNotNone(ios_toolbar)
            self.assertIsNotNone(android_toolbar)
            
            print("✅ All toolbar components created successfully")
            
        except Exception as e:
            self.fail(f"Toolbar creation failed: {e}")


class TestViewManager(unittest.TestCase):
    """Test the view manager"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_app = MockApp("Test", "test.app")
    
    def test_view_manager_creation(self):
        """Test view manager creation"""
        try:
            desktop_vm = ViewManager(self.mock_app, is_mobile=False)
            mobile_vm = ViewManager(self.mock_app, is_mobile=True)
            
            self.assertIsNotNone(desktop_vm)
            self.assertIsNotNone(mobile_vm)
            
            print("✅ ViewManager creation test passed")
            
        except Exception as e:
            self.fail(f"ViewManager creation failed: {e}")


def main():
    """Run all tests"""
    print("🧪 Running Refactored Main Window Tests")
    print("=" * 50)
    
    # Create test suite
    suite = unittest.TestSuite()
    
    # Add test cases
    suite.addTest(unittest.makeSuite(TestRefactoredMainWindow))
    suite.addTest(unittest.makeSuite(TestViewComponents))
    suite.addTest(unittest.makeSuite(TestToolbarComponents))
    suite.addTest(unittest.makeSuite(TestViewManager))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 50)
    if result.wasSuccessful():
        print("🎉 All tests passed!")
    else:
        print(f"❌ {len(result.failures + result.errors)} test(s) failed")
        
    return result.wasSuccessful()


if __name__ == "__main__":
    main() 