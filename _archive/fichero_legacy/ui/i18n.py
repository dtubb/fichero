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

    Priority order:
    1. FICHERO_LANG environment variable (highest priority)
    2. System locale
    3. LANG/LC_ALL environment variables
    4. Default to 'en' (English)

    Returns:
        str: Language code (en, es, fr, it, pt) with 'en' as fallback
    """
    import os

    try:
        # 1. Check FICHERO_LANG environment variable first (highest priority)
        fichero_lang = os.environ.get('FICHERO_LANG', '').strip().lower()
        if fichero_lang and fichero_lang in ['en', 'es', 'fr', 'it', 'pt']:
            logger.info(f"Using language from FICHERO_LANG: {fichero_lang}")
            return fichero_lang

        # 2. Try to get the current locale
        current_locale = locale.getlocale()
        if current_locale and current_locale[0]:
            lang = current_locale[0].split('_')[0].lower()
        else:
            # 3. Fallback to environment variables
            lang_env = os.environ.get('LANG', '') or os.environ.get('LC_ALL', '')
            if lang_env:
                lang = lang_env.split('_')[0].split('.')[0].lower()
            else:
                # 4. Default to English
                lang = 'en'
    except Exception:
        # Default to English
        lang = 'en'

    # Validate language - only support languages we have translations for
    if lang not in ['en', 'es', 'fr', 'it', 'pt']:
        lang = 'en'  # Default to English

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

    Uses the builtin _ installed by translation.install() if available,
    otherwise falls back to gettext.gettext().

    Args:
        text: Text to translate

    Returns:
        str: Translated text or original text if no translation found
    """
    import builtins
    try:
        # Use the builtin _ installed by translation.install()
        builtin_gettext = getattr(builtins, '_', None)
        if builtin_gettext is not None:
            return builtin_gettext(text)
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