"""
Internationalization (i18n) module for Fichero

Handles translation setup and management using gettext.
Must be called after Toga app is created to access app.paths.
"""

import gettext
import locale
import logging
from pathlib import Path
from typing import Optional
import toga

logger = logging.getLogger(__name__)


def setup_translations(app: Optional[toga.App] = None) -> bool:
    """
    Setup gettext translations for the application.
    
    Args:
        app: Toga app instance (optional, will use toga.App.app if not provided)
        
    Returns:
        bool: True if translations were loaded successfully, False otherwise
    """
    try:
        # Test if translations are already working
        test_translation = gettext.gettext("description")
        if test_translation != "description":
            logger.info("Translations already working (early setup succeeded)")
            return True
        
        # Get the app instance
        if app is None:
            app = toga.App.app
        
        if app is None:
            logger.warning("No Toga app available for translation setup")
            gettext.install('fichero')
            return False
        
        # Detect system language
        lang = _detect_system_language()
        
        # Use Toga's app path to find translations
        app_root = app.paths.app
        locale_dir = app_root / "resources" / "locale"
        logger.debug(f"Looking for translations in: {locale_dir}")
        
        mo_file = locale_dir / lang / "LC_MESSAGES" / "fichero.mo"
        
        if locale_dir.exists() and mo_file.exists():
            # Load and install translations
            translation = gettext.translation('fichero', str(locale_dir), [lang])
            translation.install()
            logger.info(f"✅ Translations loaded for language: {lang} from {locale_dir}")
            return True
        else:
            # No translations available - install fallback
            gettext.install('fichero')
            logger.warning(f"⚠️ No translation files found for {lang}, using fallback")
            return False
            
    except Exception as e:
        logger.error(f"❌ Failed to setup translations: {e}")
        # Install fallback on any error
        gettext.install('fichero')
        return False


def _detect_system_language() -> str:
    """
    Detect the system language using various methods.
    
    Returns:
        str: Language code (en, es, fr) with 'en' as fallback
    """
    try:
        # Try to get the current locale
        current_locale = locale.getlocale()
        if current_locale and current_locale[0]:
            lang = current_locale[0].split('_')[0].lower()
        else:
            # Fallback to environment variables
            import os
            lang_env = os.environ.get('LANG', '') or os.environ.get('LC_ALL', '')
            if lang_env:
                lang = lang_env.split('_')[0].split('.')[0].lower()
            else:
                lang = 'en'
    except Exception:
        lang = 'en'
    
    # Validate language - only support languages we have translations for
    if lang not in ['en', 'es', 'fr']:
        lang = 'en'
    
    return lang


def get_translation_function():
    """
    Get the current translation function.
    
    Returns:
        callable: The gettext translation function
    """
    return gettext.gettext


# Delayed translation function that can be imported by modules
def _(text: str) -> str:
    """
    Delayed translation function that calls gettext at runtime.
    
    This function can be imported by modules and will use whatever
    translation is currently installed in the gettext module.
    
    Args:
        text: Text to translate
        
    Returns:
        str: Translated text or original text if no translation found
    """
    try:
        return gettext.gettext(text)
    except:
        return text


def reload_translations(app: Optional[toga.App] = None) -> bool:
    """
    Reload translations (useful for language changes).
    
    Args:
        app: Toga app instance (optional)
        
    Returns:
        bool: True if reload was successful
    """
    logger.info("Reloading translations...")
    return setup_translations(app) 