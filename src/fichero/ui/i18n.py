"""
Internationalization (i18n) support for Fichero
"""

import json
from pathlib import Path
from typing import Dict, Optional, List


class TranslationManager:
    """Simple translation manager for Fichero GUI"""
    
    def __init__(self, default_language: str = "en", app=None):
        self.default_language = default_language
        self.current_language = default_language
        self.app = app
        self.translations: Dict[str, Dict[str, str]] = {}
        self.resources_path = Path(__file__).parent.parent / "resources" / "languages"
        self._settings_load_attempted = False
        
        # Load all available languages
        self._load_translations()
        
        # Try to set language from settings, fallback to system detection
        self._initialize_language()
    
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
    
    def _initialize_language(self):
        """Initialize language from settings, fallback to system detection"""
        # Try to get language from settings first
        if self._set_language_from_settings():
            return
        
        # Fallback to system detection
        self._detect_system_language()
    
    def _set_language_from_settings(self) -> bool:
        """Try to set language from app settings"""
        self._settings_load_attempted = True
        
        try:
            if not self.app:
                return False
                
            # Import here to avoid circular dependency
            from ..config.core.settings import get_app_settings
            settings = get_app_settings(self.app)
            
            # Get language preference from settings
            preferences = settings.settings.get("preferences", {})
            lang_code = preferences.get("language", "").lower()
            
            # Handle "system" setting - trigger auto-detection
            if lang_code == "system":
                self._detect_system_language()
                return True
            
            # Handle specific language codes
            if lang_code and lang_code in self.translations:
                self.current_language = lang_code
                return True
                
        except Exception as e:
            pass
        
        return False
    
    def _detect_system_language(self):
        """Detect system language using the platform locale utility"""
        try:
            # Use the dedicated platform locale detection utility
            from ..utils.platform_locale import detect_system_language
            
            detected_lang = detect_system_language()
            
            # Apply detected language if available
            if detected_lang and detected_lang in self.translations:
                self.current_language = detected_lang
                print(f"🌐 Detected system language: {detected_lang}")
            else:
                print(f"🌐 System language '{detected_lang}' not available, using default: {self.default_language}")
                
        except Exception as e:
            print(f"⚠️ Language detection failed: {e}")
            # If detection fails, stick with default

    def set_language(self, language_code: str):
        """Set the current language"""
        if language_code in self.translations:
            self.current_language = language_code
        else:
            print(f"Warning: Language '{language_code}' not available")
    
    def update_from_settings(self):
        """Update language from current settings (useful when settings change)"""
        if self._set_language_from_settings():
            print(f"🌐 Language updated from settings: {self.current_language}")
        else:
            print("⚠️ Could not update language from settings")
    
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
    
    def get_language_options_for_ui(self) -> List[str]:
        """Get language options for UI dropdown with translated labels"""
        try:
            options = []
            
            # Add "System" as first option (Mac way)
            system_label = self.get("language_system", "System")
            options.append("system")  # Value is still "system" for settings
            
            # Add available languages
            for lang_code in sorted(self.translations.keys()):
                options.append(lang_code)
                
            return options
            
        except Exception as e:
            # Fallback
            return ["system", "en", "es", "fr"]
    
    def get_language_display_name(self, lang_code: str) -> str:
        """Get the display name for a language code"""
        if lang_code == "system":
            return self.get("language_system", "System")
        
        # Try to get translated name from current language
        display_key = f"language_{lang_code}"
        display_name = self.get(display_key, None)
        
        if display_name:
            return display_name
        
        # Fallback to basic names
        fallback_names = {
            "en": "English",
            "es": "Español", 
            "fr": "Français"
        }
        
        return fallback_names.get(lang_code, lang_code.upper())


# Global translation manager instance
translator = None

def set_global_translator(translator_instance):
    """Set the global translator instance (called by app during startup)"""
    global translator
    old_language = translator.current_language if translator else "en"
    translator = translator_instance
    
    # If the language changed, log it
    if translator.current_language != old_language:
        print(f"🌐 Language updated: {old_language} → {translator.current_language}")

def get_translator():
    """Get the global translator instance"""
    global translator
    if translator is None:
        # Fallback for cases where app hasn't initialized yet
        translator = TranslationManager()
    return translator

def get_global_translator():
    """Get the global translator instance (convenience function)"""
    return get_translator()

# Convenience function for getting translations
def _(key: str, fallback: Optional[str] = None) -> str:
    """Get translated string (shorthand function)"""
    translator_instance = get_translator()
    
    # If we have an app but haven't tried loading from settings yet, or we're still using default language, try once
    if (translator_instance.app and 
        not translator_instance._settings_load_attempted and
        translator_instance.current_language == translator_instance.default_language):
        translator_instance._set_language_from_settings()
    
    return translator_instance.get(key, fallback)

def update_language_from_settings():
    """Update the global translator language from current settings"""
    if translator:
        translator.update_from_settings()

# Initialize fallback translator
translator = TranslationManager() 