"""
Language detection utilities and testing helpers for Fichero i18n system
"""

import json
import platform
from pathlib import Path
from typing import Dict, Optional


def test_language_detection() -> Dict[str, str]:
    """Test language detection on the current platform and return results"""
    results = {
        "platform": platform.system(),
        "platform_release": platform.release(),
        "platform_version": platform.version(),
        "detected_language": None,
        "detection_method": None,
        "available_languages": [],
        "fallback_used": False
    }
    
    # Import the new safe platform detection
    try:
        from .platform_locale import detect_system_language, get_language_detection_info
        
        # Get detected language
        results["detected_language"] = detect_system_language()
        
        # Get detailed detection info
        detection_info = get_language_detection_info()
        results["detection_method"] = detection_info.get("detection_method", "unknown")
        results["environment_vars"] = detection_info.get("environment_vars", {})
        
        # Get available languages from i18n system
        from ..ui.i18n import TranslationManager
        tm = TranslationManager()
        results["available_languages"] = list(tm.translations.keys())
        
        # Check if fallback was used (if we couldn't detect from environment/platform-specific methods)
        results["fallback_used"] = results["detection_method"] in ["standard_locale", "failed"]
        
    except Exception as e:
        results["error"] = str(e)
        results["detection_method"] = "error"
    
    return results


def print_language_detection_report():
    """Print a detailed report of language detection capabilities"""
    results = test_language_detection()
    
    print("🌐 Fichero Language Detection Report")
    print("=" * 50)
    
    if results.get("error"):
        print(f"❌ Error: {results['error']}")
        return
    
    print(f"🌐 Detected system language: {results['detected_language'] or 'None'}")
    print(f"Platform: {results['platform']}")
    print(f"Release: {results['platform_release']}")
    print(f"Version: {results['platform_version']}")
    print()
    
    detection_method_names = {
        "environment_LANG": "Environment variable (LANG)",
        "environment_LC_ALL": "Environment variable (LC_ALL)", 
        "macos_defaults": "macOS defaults command",
        "windows_api": "Windows API",
        "standard_locale": "Python locale module",
        "failed": "Detection failed"
    }
    
    method_name = detection_method_names.get(results["detection_method"], results["detection_method"])
    print(f"Detection Method: {method_name}")
    print(f"Detected Language: {results['detected_language'] or 'None'}")
    print(f"Fallback Used: {'Yes' if results['fallback_used'] else 'No'}")
    print(f"Available Languages: {', '.join(results['available_languages'])}")
    print()
    
    # Environment variables
    print("Environment Variables:")
    env_vars = results.get("environment_vars", {})
    for var, value in env_vars.items():
        print(f"  {var}: {value or 'Not set'}")
    print()
    
    # Python locale info
    try:
        import locale
        current_locale = locale.getlocale()
        default_locale = locale.getdefaultlocale()
        print("Python Locale Info:")
        print(f"  Current Locale: {current_locale}")
        print(f"  System Default: {default_locale[0] if default_locale else 'Unknown'}")
        print()
    except Exception:
        pass


def list_available_languages() -> Dict[str, Dict[str, str]]:
    """List all available language files and their details"""
    try:
        from ..ui.i18n import TranslationManager
        tm = TranslationManager()
        
        languages = {}
        for lang_code, translations in tm.translations.items():
            # Get language name from the translations
            lang_name = translations.get("language_name", lang_code.upper())
            languages[lang_code] = {
                "name": lang_name,
                "key_count": len(translations),
                "file_path": str(tm.resources_path / f"{lang_code}.json")
            }
        
        return languages
        
    except Exception as e:
        print(f"Error loading language files: {e}")
        return {}


def print_available_languages():
    """Print a formatted list of available languages"""
    languages = list_available_languages()
    
    if not languages:
        print("❌ No language files found")
        return
    
    print("🌐 Available Language Files:")
    print("-" * 30)
    
    for lang_code, info in languages.items():
        print(f"  {lang_code}: {info['name']} ({info['key_count']} keys)")


def create_language_template(lang_code: str, lang_name: str) -> bool:
    """
    Create a new language file template based on the English file
    
    Args:
        lang_code: Language code (e.g., 'de', 'it')
        lang_name: Language name (e.g., 'German', 'Italian')
    
    Returns:
        True if successful, False otherwise
    """
    try:
        from ..ui.i18n import TranslationManager
        tm = TranslationManager()
        
        # Load English as template
        en_file = tm.resources_path / "en.json"
        if not en_file.exists():
            print(f"❌ English template file not found: {en_file}")
            return False
        
        with open(en_file, 'r', encoding='utf-8') as f:
            en_data = json.load(f)
        
        # Create new language file with English text as placeholders
        new_data = en_data.copy()
        new_data["language_name"] = lang_name
        new_data["language_code"] = lang_code
        
        # Add a note about translation needed
        if "app_name" in new_data:
            new_data["_translation_note"] = f"Please translate all values to {lang_name}. Remove this note when done."
        
        # Save new file
        new_file = tm.resources_path / f"{lang_code}.json"
        with open(new_file, 'w', encoding='utf-8') as f:
            json.dump(new_data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Created language template: {new_file}")
        print(f"   Language: {lang_name} ({lang_code})")
        print(f"   Keys: {len(new_data)}")
        print("   Please edit the file to translate all values.")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating language template: {e}")
        return False


def validate_language_file(lang_code: str) -> bool:
    """
    Validate a language file for completeness and correctness
    
    Args:
        lang_code: Language code to validate
    
    Returns:
        True if valid, False otherwise
    """
    try:
        from ..ui.i18n import TranslationManager
        tm = TranslationManager()
        
        # Check if file exists
        lang_file = tm.resources_path / f"{lang_code}.json"
        if not lang_file.exists():
            print(f"❌ Language file not found: {lang_file}")
            return False
        
        # Load the file
        with open(lang_file, 'r', encoding='utf-8') as f:
            lang_data = json.load(f)
        
        # Load English for comparison
        en_file = tm.resources_path / "en.json"
        with open(en_file, 'r', encoding='utf-8') as f:
            en_data = json.load(f)
        
        # Check for missing keys
        missing_keys = set(en_data.keys()) - set(lang_data.keys())
        extra_keys = set(lang_data.keys()) - set(en_data.keys())
        
        print(f"🔍 Validating {lang_code}.json:")
        print(f"   Total keys: {len(lang_data)}")
        print(f"   Expected keys: {len(en_data)}")
        
        if missing_keys:
            print(f"   ❌ Missing keys ({len(missing_keys)}): {', '.join(sorted(missing_keys))}")
        
        if extra_keys:
            print(f"   ⚠️  Extra keys ({len(extra_keys)}): {', '.join(sorted(extra_keys))}")
        
        if not missing_keys and not extra_keys:
            print("   ✅ All keys present and correct")
            return True
        
        return False
        
    except Exception as e:
        print(f"❌ Error validating language file: {e}")
        return False 