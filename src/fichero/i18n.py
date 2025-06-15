"""
Internationalization (i18n) support for Fichero
"""

import json
import locale
from pathlib import Path
from typing import Dict, Optional


class TranslationManager:
    """Simple translation manager for Fichero GUI"""
    
    def __init__(self, default_language: str = "en"):
        self.default_language = default_language
        self.current_language = default_language
        self.translations: Dict[str, Dict[str, str]] = {}
        self.resources_path = Path(__file__).parent / "resources" / "languages"
        
        # Load all available languages
        self._load_translations()
        
        # Try to detect and use system default language
        self._detect_system_language()
    
    def _load_translations(self):
        """Load all translation files from the languages directory"""
        try:
            for lang_file in self.resources_path.glob("*.json"):
                lang_code = lang_file.stem  # e.g., "en" from "en.json"
                with open(lang_file, 'r', encoding='utf-8') as f:
                    self.translations[lang_code] = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load translations: {e}")
            # Fallback to basic English translations
            self.translations = {
                "en": {
                    "app_title": "Fichero",
                    "choose_folder": "Choose Folder...",
                    "description": "Document processing and transcription tool",
                    "help": "?",
                    "process": "Process",
                    "folder_icon_label": "📁",
                    "folder_status": "No folder selected"
                }
            }
    
    def _detect_system_language(self):
        """Try to detect system language and set it if available"""
        try:
            system_locale = locale.getdefaultlocale()[0]
            if system_locale:
                # Extract language code (e.g., "en" from "en_US")
                lang_code = system_locale.split('_')[0].lower()
                if lang_code in self.translations:
                    self.current_language = lang_code
        except Exception:
            # If detection fails, stick with default
            pass
    
    def set_language(self, language_code: str):
        """Set the current language"""
        if language_code in self.translations:
            self.current_language = language_code
        else:
            print(f"Warning: Language '{language_code}' not available")
    
    def get(self, key: str, fallback: Optional[str] = None) -> str:
        """Get translated string for the current language"""
        # Try current language first
        if (self.current_language in self.translations and 
            key in self.translations[self.current_language]):
            return self.translations[self.current_language][key]
        
        # Fallback to default language
        if (self.default_language in self.translations and 
            key in self.translations[self.default_language]):
            return self.translations[self.default_language][key]
        
        # Last resort: return the fallback or the key itself
        return fallback or key
    
    def get_available_languages(self) -> Dict[str, str]:
        """Get list of available languages with their display names"""
        language_names = {
            "en": "English",
            "fr": "Français", 
            "es": "Español"
        }
        return {code: language_names.get(code, code.upper()) 
                for code in self.translations.keys()}


# Global translation manager instance
translator = TranslationManager()

# Convenience function for getting translations
def _(key: str, fallback: Optional[str] = None) -> str:
    """Get translated string (shorthand function)"""
    return translator.get(key, fallback) 