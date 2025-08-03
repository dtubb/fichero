"""
Language detection using Python's locale module.
"""

import locale


def detect_system_language() -> str:
    """Get system language using Python's locale module."""
    try:
        default_locale = locale.getdefaultlocale()
        if default_locale and default_locale[0]:
            return default_locale[0].split('_')[0].lower()
    except:
        pass
    return 'en' 