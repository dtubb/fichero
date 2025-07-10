"""
Cross-platform locale detection utility for Fichero

Simple, safe locale detection that avoids memory management issues.
Focuses on environment variables and Python's locale module for reliability.
"""

import locale
import os
import platform
from typing import Optional


def detect_system_language() -> Optional[str]:
    """
    Detect the system language across all platforms.
    
    Uses safe, reliable methods to avoid memory management issues.
    
    Returns:
        Language code (e.g., 'en', 'fr') or None if detection fails
    """
    try:
        system = platform.system()
        
        # Platform-specific detection first (more reliable for native OS settings)
        if system == "Darwin":
            # macOS/iOS - prioritize system settings over environment
            lang = _detect_macos_safe()
            if lang:
                return lang
        elif system == "Windows":
            lang = _detect_windows_safe()
            if lang:
                return lang
        elif system == "Linux":
            lang = _detect_linux_safe()
            if lang:
                return lang
        
        # Fallback to environment variables (works on all platforms)
        lang = _detect_from_environment()
        if lang:
            return lang
            
        # Final fallback to standard locale
        return _detect_standard_locale()
            
    except Exception:
        # If all detection fails, return None
        return None


def _detect_from_environment() -> Optional[str]:
    """Detect language from environment variables (works on all platforms)"""
    try:
        # Check common locale environment variables
        env_vars = ['LANG', 'LC_ALL', 'LC_CTYPE', 'LANGUAGE']
        
        for env_var in env_vars:
            locale_string = os.environ.get(env_var)
            if locale_string and locale_string != 'C' and locale_string != 'POSIX':
                # Extract language code from locale string
                # Examples: en_US.UTF-8 -> en, fr_FR -> fr, zh_CN.UTF-8 -> zh
                lang_code = locale_string.split('_')[0].split('.')[0].split(':')[0].lower()
                if lang_code and lang_code != 'c':
                    return lang_code
        
        return None
    except Exception:
        return None


def _detect_macos_safe() -> Optional[str]:
    """Safe macOS language detection without PyObjC memory issues"""
    try:
        # Method 1: Check macOS defaults command (if available)
        try:
            import subprocess
            result = subprocess.run(
                ['defaults', 'read', '-g', 'AppleLocale'],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                locale_string = result.stdout.strip()
                lang_code = locale_string.split('_')[0].lower()
                if lang_code:
                    return lang_code
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        # Method 2: Check for AppleLanguages (parse the array properly)
        try:
            import subprocess
            result = subprocess.run(
                ['defaults', 'read', '-g', 'AppleLanguages'],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                # AppleLanguages returns array like ("en-US", "fr-FR")
                output = result.stdout.strip()
                
                # Parse the array to get the first language
                # Remove parentheses and quotes, split by comma
                if output.startswith('(') and output.endswith(')'):
                    content = output[1:-1].strip()
                    if content:
                        # Split by comma and get first item
                        languages = [lang.strip().strip('"\'') for lang in content.split(',')]
                        if languages and languages[0]:
                            # Extract language code from format like "es-CA" -> "es"
                            first_lang = languages[0].split('-')[0].split('_')[0].lower()
                            if first_lang:
                                return first_lang
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        # Fallback to standard locale
        return _detect_standard_locale()
        
    except Exception:
        return None


def _detect_windows_safe() -> Optional[str]:
    """Safe Windows language detection"""
    try:
        # Method 1: Check Windows locale using ctypes (safer than registry)
        try:
            import ctypes
            # Get the user's default locale
            lcid = ctypes.windll.kernel32.GetUserDefaultLCID()
            
            # Extract primary language ID (lower 10 bits)
            lang_id = lcid & 0x3FF
            
            # Map common language IDs to ISO codes
            lang_map = {
                0x09: 'en',   # English
                0x0c: 'fr',   # French  
                0x07: 'de',   # German
                0x0a: 'es',   # Spanish
                0x10: 'it',   # Italian
                0x11: 'ja',   # Japanese
                0x12: 'ko',   # Korean
                0x04: 'zh',   # Chinese (Simplified)
                0x0404: 'zh', # Chinese (Traditional)
                0x13: 'nl',   # Dutch
                0x14: 'no',   # Norwegian
                0x15: 'pl',   # Polish
                0x16: 'pt',   # Portuguese
                0x19: 'ru',   # Russian
            }
            
            if lang_id in lang_map:
                return lang_map[lang_id]
                
        except (ImportError, AttributeError):
            pass
        
        # Fallback to standard locale
        return _detect_standard_locale()
        
    except Exception:
        return None


def _detect_linux_safe() -> Optional[str]:
    """Safe Linux language detection"""
    try:
        # Method 1: Try locale command
        try:
            import subprocess
            result = subprocess.run(['locale'], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if line.startswith('LANG='):
                        locale_string = line.split('=', 1)[1].strip().strip('"\'')
                        lang_code = locale_string.split('_')[0].split('.')[0].lower()
                        if lang_code and lang_code != 'c':
                            return lang_code
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        # Method 2: Check system locale files
        try:
            with open('/etc/default/locale', 'r') as f:
                for line in f:
                    if line.startswith('LANG='):
                        locale_string = line.split('=', 1)[1].strip().strip('"\'')
                        lang_code = locale_string.split('_')[0].split('.')[0].lower()
                        if lang_code and lang_code != 'c':
                            return lang_code
        except (FileNotFoundError, PermissionError):
            pass
        
        # Fallback to standard locale
        return _detect_standard_locale()
        
    except Exception:
        return None


def _detect_standard_locale() -> Optional[str]:
    """Fallback detection using Python's locale module"""
    try:
        # Try to get the default locale
        try:
            default_locale = locale.getdefaultlocale()
            if default_locale and default_locale[0]:
                lang_code = default_locale[0].split('_')[0].lower()
                if lang_code and lang_code != 'c':
                    return lang_code
        except (locale.Error, ValueError):
            pass
        
        # Try getlocale
        try:
            current_locale = locale.getlocale()
            if current_locale and current_locale[0]:
                lang_code = current_locale[0].split('_')[0].lower()
                if lang_code and lang_code != 'c':
                    return lang_code
        except (locale.Error, ValueError):
            pass
        
        return None
        
    except Exception:
        return None


def get_language_detection_info() -> dict:
    """
    Get detailed information about language detection for debugging.
    
    Returns:
        Dictionary with platform info and detected language
    """
    try:
        info = {
            'platform': platform.system(),
            'platform_release': platform.release(),
            'detected_language': detect_system_language(),
            'environment_vars': {},
            'detection_method': 'unknown'
        }
        
        # Get environment variables
        env_vars = ['LANG', 'LC_ALL', 'LC_CTYPE', 'LANGUAGE']
        for var in env_vars:
            info['environment_vars'][var] = os.environ.get(var)
        
        # Determine detection method by testing each method in order of priority
        if info['platform'] == 'Darwin':
            # Test macOS detection first
            macos_result = _detect_macos_safe()
            if macos_result:
                info['detection_method'] = 'macos_defaults'
            elif info['environment_vars'].get('LANG'):
                info['detection_method'] = 'environment_LANG'
            elif info['environment_vars'].get('LC_ALL'):
                info['detection_method'] = 'environment_LC_ALL'
            else:
                info['detection_method'] = 'standard_locale'
        elif info['platform'] == 'Windows':
            # Test Windows detection first
            windows_result = _detect_windows_safe()
            if windows_result:
                info['detection_method'] = 'windows_api'
            elif info['environment_vars'].get('LANG'):
                info['detection_method'] = 'environment_LANG'
            elif info['environment_vars'].get('LC_ALL'):
                info['detection_method'] = 'environment_LC_ALL'
            else:
                info['detection_method'] = 'standard_locale'
        else:
            # Linux or other platforms
            if info['environment_vars'].get('LANG'):
                info['detection_method'] = 'environment_LANG'
            elif info['environment_vars'].get('LC_ALL'):
                info['detection_method'] = 'environment_LC_ALL'
            else:
                info['detection_method'] = 'standard_locale'
        
        return info
        
    except Exception as e:
        return {
            'platform': 'unknown',
            'detected_language': None,
            'error': str(e),
            'detection_method': 'failed'
        } 