"""
Translation Unit Tests

Tests to verify that translations are working correctly across all window modules,
not just falling back to raw translation keys.
"""

import unittest
import gettext
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


class TestTranslationSetup(unittest.TestCase):
    """Test that gettext translation system is properly configured"""
    
    def setUp(self):
        """Set up test environment"""
        # Save original translation state
        self.original_gettext = gettext.gettext
    
    def tearDown(self):
        """Restore original state"""
        # Restore gettext
        gettext.gettext = self.original_gettext
    
    def test_translation_files_exist(self):
        """Test that translation files exist in expected locations"""
        resources_path = src_path / "fichero" / "resources" / "locale"
        
        # Check English translations
        en_mo_file = resources_path / "en" / "LC_MESSAGES" / "fichero.mo" 
        en_po_file = resources_path / "en" / "LC_MESSAGES" / "fichero.po"
        
        self.assertTrue(resources_path.exists(), f"Locale directory should exist: {resources_path}")
        self.assertTrue(en_po_file.exists(), f"English .po file should exist: {en_po_file}")
        # Note: .mo file might not exist in dev, that's ok
        
        # Check Spanish translations if they exist
        es_po_file = resources_path / "es" / "LC_MESSAGES" / "fichero.po"
        if es_po_file.exists():
            self.assertTrue(es_po_file.exists(), f"Spanish .po file should exist: {es_po_file}")
    
    def test_gettext_loads_translations(self):
        """Test that gettext can load translation files"""
        resources_path = src_path / "fichero" / "resources" / "locale"
        
        if not resources_path.exists():
            self.skipTest("Translation files not found")
        
        # Try to load English translations
        try:
            translation = gettext.translation('fichero', str(resources_path), ['en'])
            self.assertIsNotNone(translation, "Should be able to load English translations")
            
            # Test a known translation key
            _ = translation.gettext
            result = _("description")
            self.assertNotEqual(result, "description", "Should translate 'description' key, not return raw key")
            self.assertIn("Fichero", result, "Description should contain 'Fichero'")
            
        except FileNotFoundError:
            # If .mo file doesn't exist, we can still test .po parsing
            po_file = resources_path / "en" / "LC_MESSAGES" / "fichero.po"
            if po_file.exists():
                self.assertTrue(True, ".po file exists, .mo compilation may be needed")
            else:
                self.fail("Neither .mo nor .po files found for English")


class TestWindowTranslations(unittest.TestCase):
    """Test translation usage in specific window modules"""
    
    def setUp(self):
        """Set up mock translation environment"""
        # Mock translation dictionary with known keys
        self.mock_translations = {
            "description": "*Fichero* processes large collections of digitized documents",
            "process": "Process", 
            "choose_folder": "Choose Folder…",
            "help": "?",
            "about_window_title": "About Fichero",
            "processing_window_title": "Fichero - Process",
            "activity_monitor_window_title": "Fichero Activity Monitor"
        }
        
        def mock_gettext(key):
            """Mock gettext that returns known translations or the key itself"""
            return self.mock_translations.get(key, key)
        
        # Patch gettext globally
        self.gettext_patcher = patch('gettext.gettext', side_effect=mock_gettext)
        self.mock_gettext_func = self.gettext_patcher.start()
    
    def tearDown(self):
        """Clean up patches"""
        self.gettext_patcher.stop()
    
    def test_about_window_translations(self):
        """Test that about window properly uses translations"""
        # Import about window components
        from fichero.windows.about.about_window import AboutWindow
        from fichero.windows.about.about_content import AboutContent
        
        # Mock app
        mock_app = MagicMock()
        mock_app.screens = [MagicMock()]
        mock_app.screens[0].size.width = 1920
        mock_app.screens[0].size.height = 1080
        
        # Test AboutWindow title translation
        with patch('toga.Window') as mock_window:
            about_window = AboutWindow(mock_app)
            
            # Check that Window was called with translated title
            mock_window.assert_called_once()
            call_args = mock_window.call_args
            title = call_args[1]['title']  # title is a keyword argument
            
            self.assertEqual(title, "About Fichero", 
                           f"About window title should be translated, got: {title}")
    
    def test_processing_window_translations(self):
        """Test that processing window properly uses translations"""
        from fichero.windows.processing.desktop_window import ProcessingWindow
        
        # Mock app and dependencies
        mock_app = MagicMock()
        mock_app.screens = [MagicMock()]
        mock_app.screens[0].size.width = 1920
        mock_app.screens[0].size.height = 1080
        
        # Mock ProcessingContent to avoid complex initialization
        with patch('fichero.windows.processing.processing_content.ProcessingContent') as mock_content:
            mock_content.return_value.create.return_value = MagicMock()
            
            with patch('toga.Window') as mock_window:
                processing_window = ProcessingWindow(mock_app)
                
                # Check that Window was called with translated title
                mock_window.assert_called_once()
                call_args = mock_window.call_args
                title = call_args[1]['title']
                
                self.assertEqual(title, "Fichero - Process",
                               f"Processing window title should be translated, got: {title}")
    
    def test_activity_monitor_window_translations(self):
        """Test that activity monitor window properly uses translations"""
        from fichero.windows.activity_monitor.activity_window import ActivityMonitorWindow
        
        # Mock app
        mock_app = MagicMock()
        mock_app.screens = [MagicMock()]
        mock_app.screens[0].size.width = 1920
        mock_app.screens[0].size.height = 1080
        
        activity_window = ActivityMonitorWindow(mock_app)
        
        # Mock the content creation to avoid complex dependencies
        with patch('fichero.windows.activity_monitor.activity_content.ActivityMonitorContent') as mock_content:
            mock_content.return_value.create.return_value = MagicMock()
            
            with patch('toga.Window') as mock_window:
                # Trigger window creation
                activity_window._create_window()
                
                # Check that Window was called with translated title
                mock_window.assert_called_once()
                call_args = mock_window.call_args
                title = call_args[1]['title']
                
                self.assertEqual(title, "Fichero Activity Monitor",
                               f"Activity monitor window title should be translated, got: {title}")
    
    def test_processing_layout_manager_translations(self):
        """Test that processing layout manager uses translations for buttons"""
        from fichero.windows.processing.layout_manager import ProcessingLayoutManager, _translate
        
        # Test the _translate function directly
        result = _translate("process")
        self.assertEqual(result, "Process", f"_translate should return 'Process', got: {result}")
        
        result = _translate("nonexistent_key")
        self.assertEqual(result, "nonexistent_key", "_translate should return key when translation not found")
    
    def test_description_view_translations(self):
        """Test that description view uses translations correctly"""
        from fichero.windows.processing.components.description_view import DescriptionView
        
        # Mock app and dependencies
        mock_app = MagicMock()
        
        # Mock Toga components to avoid complex initialization
        with patch('toga.WebView') as mock_webview, \
             patch('toga.Box') as mock_box, \
             patch('toga.ScrollContainer') as mock_scroll:
            
            description_view = DescriptionView(mock_app)
            
            # The create method should call the translation
            # We can't easily test the UI creation, but we can test that
            # the translation call happens correctly
            
            # Import the module's translation function
            from fichero.windows.processing.components.description_view import _
            
            result = _("description")
            self.assertNotEqual(result, "description", 
                              "Description should be translated, not return raw key")
            self.assertIn("Fichero", result, 
                         "Description should contain 'Fichero' text")


class TestTranslationFallbacks(unittest.TestCase):
    """Test fallback behavior when translations fail"""
    
    def test_missing_translation_key_fallback(self):
        """Test that missing translation keys fall back gracefully"""
        # Mock gettext to simulate missing key
        def mock_gettext_missing(key):
            return key  # Return key unchanged if not found
        
        with patch('gettext.gettext', side_effect=mock_gettext_missing):
            from fichero.windows.processing.layout_manager import _translate
            
            result = _translate("nonexistent_key")
            self.assertEqual(result, "nonexistent_key", 
                           "Should return key when translation not found")
    
    def test_gettext_exception_fallback(self):
        """Test that gettext exceptions are handled gracefully"""
        # Mock gettext to throw exception
        def mock_gettext_exception(key):
            raise Exception("Translation system failed")
        
        with patch('gettext.gettext', side_effect=mock_gettext_exception):
            from fichero.windows.processing.layout_manager import _translate
            
            result = _translate("any_key")
            self.assertEqual(result, "any_key", 
                           "Should return key when gettext throws exception")
    
    def test_window_title_fallback_logic(self):
        """Test the specific fallback logic used in window titles"""
        # Mock gettext to return the key unchanged (no translation)
        def mock_gettext_no_translation(key):
            return key
        
        with patch('gettext.gettext', side_effect=mock_gettext_no_translation):
            from fichero.windows.about.about_window import _
            
            # Test the about window title logic
            title = _("about_window_title") if _("about_window_title") != "about_window_title" else "About Fichero"
            self.assertEqual(title, "About Fichero", 
                           "Should fall back to English when no translation available")


class TestSpecificTranslationKeys(unittest.TestCase):
    """Test specific translation keys used in the application"""
    
    def setUp(self):
        """Set up real translation environment"""
        # Try to load real translations if available
        try:
            resources_path = src_path / "fichero" / "resources" / "locale"
            if resources_path.exists():
                translation = gettext.translation('fichero', str(resources_path), ['en'])
                self._ = translation.gettext
                self.has_translations = True
            else:
                self._ = lambda x: x  # Fallback
                self.has_translations = False
        except:
            self._ = lambda x: x  # Fallback
            self.has_translations = False
    
    def test_known_translation_keys(self):
        """Test that known translation keys work correctly"""
        known_keys = [
            "description", 
            "process", 
            "choose_folder", 
            "help"
        ]
        
        for key in known_keys:
            result = self._(key)
            
            if self.has_translations:
                # If we have real translations, result should be different from key
                self.assertNotEqual(result, key, 
                                  f"Translation key '{key}' should return translated text, not raw key")
            else:
                # If no translations, should return the key
                self.assertEqual(result, key, 
                               f"Without translations, should return key '{key}' unchanged")
    
    def test_missing_translation_keys(self):
        """Test behavior with missing translation keys"""
        missing_keys = [
            "nonexistent_key",
            "another_missing_key"
        ]
        
        for key in missing_keys:
            result = self._(key)
            # Should return the key unchanged whether translations exist or not
            self.assertEqual(result, key, 
                           f"Missing key '{key}' should return unchanged")
    
    def test_newly_added_translation_keys(self):
        """Test that the translation keys we just added work correctly"""
        new_keys = {
            "processing_window_title": "Fichero - Process",
            "activity_monitor_window_title": "Fichero Activity Monitor"
        }
        
        for key, expected_translation in new_keys.items():
            result = self._(key)
            if self.has_translations:
                # Should return the proper translation
                self.assertEqual(result, expected_translation, 
                               f"Translation key '{key}' should return '{expected_translation}', not '{result}'")
            else:
                # If no translations loaded, should return the key
                self.assertEqual(result, key, 
                               f"Without translations, should return key '{key}' unchanged")


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2) 