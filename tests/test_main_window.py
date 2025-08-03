"""
Unit tests for MainWindow
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import asyncio
import sys
import os

# Add src to path so we can import fichero modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from fichero.main_window import MainWindow


class TestMainWindow(unittest.TestCase):
    """Test cases for MainWindow"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_app = Mock()
        self.mock_app.paths = Mock()
        self.mock_app.paths.data = Path("/tmp/test_data")
        
        # Mock settings
        self.mock_settings = Mock()
        self.mock_settings.get_setting.return_value = None
        self.mock_app.settings = self.mock_settings
        
        # Mock director
        self.mock_director = Mock()
        self.mock_app.director = self.mock_director
    
    def test_main_window_initialization(self):
        """Test that MainWindow can be initialized"""
        window = MainWindow(self.mock_app)
        
        self.assertIsNotNone(window)
        self.assertEqual(window.app, self.mock_app)
        self.assertIsNone(window.window)
        self.assertFalse(window.is_visible)
        self.assertIsNotNone(window.state)
        self.assertIsNotNone(window.scanner)
    
    def test_show_method(self):
        """Test show method creates window and loads data"""
        window = MainWindow(self.mock_app)
        
        # Mock window creation and set window attribute
        mock_window = Mock()
        with patch.object(window, '_create_window') as mock_create:
            with patch('asyncio.create_task') as mock_create_task:
                # Set window attribute after create_window is called
                def side_effect():
                    window.window = mock_window
                mock_create.side_effect = side_effect
                
                window.show()
                
                # Should create window and load data
                mock_create.assert_called_once()
                mock_create_task.assert_called_once()
                self.assertTrue(window.is_visible)
    
    def test_hide_method(self):
        """Test hide method"""
        window = MainWindow(self.mock_app)
        
        # Mock window
        window.window = Mock()
        window.is_visible = True
        
        window.hide()
        
        # Should hide window
        window.window.hide.assert_called_once()
        self.assertFalse(window.is_visible)
    
    def test_close_method(self):
        """Test close method"""
        window = MainWindow(self.mock_app)
        
        # Mock window
        mock_window = Mock()
        window.window = mock_window
        window.is_visible = True
        
        window.close()
        
        # Should close window and reset state
        mock_window.close.assert_called_once()
        self.assertIsNone(window.window)
        self.assertFalse(window.is_visible)
    
    def test_get_library_path_default(self):
        """Test getting default library path"""
        window = MainWindow(self.mock_app)
        
        # Mock settings to return None (use default)
        self.mock_settings.get_setting.return_value = None
        
        library_path = window._get_library_path()
        
        # Should use Toga app paths
        expected_path = self.mock_app.paths.data / "collections"
        self.assertEqual(library_path, expected_path)
    
    def test_get_library_path_from_settings(self):
        """Test getting library path from settings"""
        window = MainWindow(self.mock_app)
        
        # Mock the window's settings instance
        test_path = "/custom/library/path"
        window.settings = Mock()
        window.settings.get_setting.return_value = test_path
        
        library_path = window._get_library_path()
        
        # Should use path from settings
        self.assertEqual(library_path, Path(test_path))
    
    def test_get_window_size_desktop(self):
        """Test window size for desktop platforms"""
        window = MainWindow(self.mock_app)
        
        # Mock app to not have platform attribute (desktop)
        if hasattr(self.mock_app, 'platform'):
            delattr(self.mock_app, 'platform')
        
        size = window._get_window_size()
        
        # Should return desktop size
        self.assertEqual(size, (1000, 700))
    
    def test_get_window_size_mobile(self):
        """Test window size for mobile platforms"""
        window = MainWindow(self.mock_app)
        
        # Mock app to have mobile platform
        self.mock_app.platform = 'iOS'
        
        size = window._get_window_size()
        
        # Should return mobile size
        self.assertEqual(size, (800, 600))
    
    def test_state_management(self):
        """Test window state management"""
        window = MainWindow(self.mock_app)
        
        # Test initial state
        self.assertEqual(window.state.collection_count, 0)
        self.assertEqual(window.state.filtered_count, 0)
        self.assertEqual(window.state.search_text, "")
        self.assertEqual(window.state.filter_value, "All Collections")
    
    def test_search_filter_update(self):
        """Test search filter updates state"""
        window = MainWindow(self.mock_app)
        
        # Mock search filter component
        window.search_filter = Mock()
        window.search_filter.search_text = "test search"
        
        # Mock collection list to avoid None error
        window.collection_list = Mock()
        window.status_bar = Mock()
        
        # Call search change handler
        window._on_search_change(None)
        
        # State should be updated
        self.assertEqual(window.state.search_text, "test search")
    
    def test_filter_dropdown_update(self):
        """Test filter dropdown updates state"""
        window = MainWindow(self.mock_app)
        
        # Mock search filter component
        window.search_filter = Mock()
        window.search_filter.filter_value = "Processed"
        
        # Mock collection list to avoid None error
        window.collection_list = Mock()
        window.status_bar = Mock()
        
        # Call filter change handler
        window._on_filter_change(None)
        
        # State should be updated
        self.assertEqual(window.state.filter_value, "Processed")
    
    def test_ui_update_from_state(self):
        """Test UI updates from state changes"""
        window = MainWindow(self.mock_app)
        
        # Mock components
        window.collection_list = Mock()
        window.status_bar = Mock()
        
        # Update state
        window.state.set_search_text("test")
        
        # Call UI update
        window._update_ui_from_state()
        
        # Components should be called
        window.collection_list.set_data.assert_called_once()
        window.status_bar.set_count.assert_called_once()
    
    def test_collection_actions(self):
        """Test collection action handlers"""
        window = MainWindow(self.mock_app)
        
        # Mock status bar
        window.status_bar = Mock()
        
        # Mock collection data
        mock_collection = Mock()
        mock_collection.title = "Test Collection"
        
        # Test collection select
        mock_row = Mock()
        mock_row.data = mock_collection
        window._on_collection_select(None, mock_row)
        
        # Status should be updated
        window.status_bar.set_status.assert_called_once()
    
    def test_refresh_handler(self):
        """Test refresh button handler"""
        window = MainWindow(self.mock_app)
        
        # Mock asyncio.create_task to avoid event loop issues
        with patch('asyncio.create_task') as mock_create_task:
            window._on_refresh(None)
            
            # Should call create_task with _load_collection_data
            mock_create_task.assert_called_once()
    
    def test_settings_handler(self):
        """Test settings button handler"""
        window = MainWindow(self.mock_app)
        
        # Mock app menu manager
        window.app.menu_manager = Mock()
        
        # Mock status bar
        window.status_bar = Mock()
        
        # Call settings handler
        window._on_settings(None)
        
        # Should call menu manager settings handler
        window.app.menu_manager._settings_handler.assert_called_once_with(None)
    
    def test_about_handler(self):
        """Test about button handler"""
        window = MainWindow(self.mock_app)
        
        # Mock app menu manager
        window.app.menu_manager = Mock()
        
        # Mock status bar
        window.status_bar = Mock()
        
        # Call about handler
        window._on_about(None)
        
        # Should call menu manager about handler
        window.app.menu_manager._about_handler.assert_called_once_with(None)
    
    def test_window_close_handler(self):
        """Test window close handler"""
        window = MainWindow(self.mock_app)
        
        # Mock hide method
        with patch.object(window, 'hide') as mock_hide:
            result = window._on_close(None)
            
            # Should call hide and return True
            mock_hide.assert_called_once()
            self.assertTrue(result)
    
    def test_closed_property(self):
        """Test closed property"""
        window = MainWindow(self.mock_app)
        
        # Initially not closed (window is None)
        self.assertTrue(window.closed)
        
        # Mock window
        window.window = Mock()
        self.assertFalse(window.closed)
        
        # Set window to None
        window.window = None
        self.assertTrue(window.closed)
    
    def test_error_handling_in_create_window(self):
        """Test error handling in window creation"""
        window = MainWindow(self.mock_app)
        
        # Mock toga.MainWindow to raise an exception
        with patch('toga.MainWindow', side_effect=Exception("Window creation failed")):
            with self.assertRaises(Exception):
                window._create_window()
    
    def test_load_collection_data_error_handling(self):
        """Test error handling in collection data loading"""
        window = MainWindow(self.mock_app)
        
        # Mock scanner to raise an exception
        window.scanner.scan_collections = Mock(side_effect=Exception("Scan failed"))
        window.status_bar = Mock()
        
        # Create event loop for async test
        async def test_async():
            await window._load_collection_data()
            # Should handle error gracefully
            window.status_bar.set_status.assert_called()
        
        # Run the async test
        asyncio.run(test_async())


if __name__ == '__main__':
    unittest.main() 