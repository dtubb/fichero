# Fichero Internationalization (i18n) Guide

Fichero now includes a comprehensive cross-platform internationalization system that automatically detects the user's system language on first run and provides a fallback to user settings.

## Supported Platforms

The i18n system works across all platforms that Toga supports:

- **macOS**: Uses PyObjC Foundation framework for native language detection
- **iOS**: Uses PyObjC Foundation framework (same as macOS)
- **Windows**: Uses Windows Registry and API for language detection
- **Linux**: Uses environment variables and system files
- **Android**: Uses Java Locale API through jnius and system properties
- **Fallback**: Standard Python locale module for any other platform

## How It Works

### Detection Priority

1. **Settings First**: If the user has previously selected a language in settings, that takes priority
2. **System Detection**: If no setting exists, the system language is auto-detected
3. **Fallback**: If detection fails, defaults to English ("en")

### Platform-Specific Detection

#### macOS/iOS
- Uses PyObjC `Foundation.NSLocale` for native language detection
- Falls back to environment variables (`LANG`, `LC_ALL`, `LC_CTYPE`)
- Then uses Python's locale module

#### Android
- Uses jnius to access Java `Locale.getDefault()`
- Reads Android system properties via `getprop persist.sys.locale`
- Falls back to environment variables

#### Windows
- Reads from Windows Registry (`HKEY_CURRENT_USER\Control Panel\International`)
- Uses Windows API `GetUserDefaultLCID()`
- Falls back to Python's locale module

#### Linux
- Checks environment variables (`LC_ALL`, `LC_CTYPE`, `LANG`, `LANGUAGE`)
- Reads from `/etc/default/locale`
- Uses `locale` command output
- Falls back to Python's locale module

## Testing Language Detection

Run the test script to see what language is detected on your platform:

```bash
python test_language_detection.py
```

Or test programmatically:

```python
from fichero.utils.language_utils import print_language_detection_report
print_language_detection_report()
```

## Available Languages

Currently supported languages:
- **en**: English
- **fr**: Français (French) 
- **es**: Español (Spanish)

## Adding New Languages

### Method 1: Using the Utility

```python
from fichero.utils.language_utils import create_language_template
create_language_template('de', 'German')
```

This creates a template file with all the English strings marked for translation.

### Method 2: Manual Creation

1. Copy `src/fichero/resources/languages/en.json`
2. Rename to your language code (e.g., `de.json` for German)
3. Translate all the values while keeping the keys the same
4. Test with your language detection

### Language Codes

Use standard ISO 639-1 language codes:
- `de` - German
- `it` - Italian  
- `ja` - Japanese
- `ko` - Korean
- `zh` - Chinese
- `pt` - Portuguese
- `ru` - Russian
- `ar` - Arabic

## Mobile Platform Setup

For enhanced mobile detection, install the optional dependencies:

```bash
# For Android detection (on Android devices)
pip install "fichero[mobile-i18n]"

# This includes:
# - jnius>=1.1.0 (Android Java bridge)
# - pyobjc-framework-Foundation (iOS/macOS Foundation framework)
```

## Usage in Code

### Basic Translation

```python
from fichero.ui.i18n import _

# Get translated string
text = _("choose_folder")  # Returns "Choose Folder…" in English
```

### With Fallback

```python
from fichero.ui.i18n import _

# Provide fallback text
text = _("unknown_key", "Default Text")
```

### Managing Languages

```python
from fichero.ui.i18n import get_translator

translator = get_translator()

# Get current language
current = translator.current_language

# Set language manually
translator.set_language('fr')

# Get available languages
languages = translator.get_available_languages()
# Returns: {'en': 'English', 'fr': 'Français', 'es': 'Español'}

# Update from settings (when settings change)
translator.update_from_settings()
```

## Settings Integration

The language system integrates with Fichero's settings system:

- User language preference is stored in `preferences.language`
- Settings take priority over system detection
- Changes update immediately when settings are saved

## Debugging Detection Issues

If language detection isn't working on your platform:

1. Run the test script: `python test_language_detection.py`
2. Check the detection report for errors
3. Verify environment variables are set correctly
4. For mobile platforms, ensure optional dependencies are installed
5. Check that your language file exists in `src/fichero/resources/languages/`

## Architecture

The i18n system is organized as:

- `src/fichero/ui/i18n.py` - Main translation manager
- `src/fichero/resources/languages/` - Language files
- `src/fichero/utils/language_utils.py` - Testing and management utilities
- `test_language_detection.py` - Standalone test script

The system is designed to be:
- **Cross-platform**: Works on all Toga-supported platforms
- **Automatic**: Detects system language on first run
- **Configurable**: User can override in settings
- **Extensible**: Easy to add new languages
- **Robust**: Multiple fallback mechanisms 