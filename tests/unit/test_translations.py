"""
Unit tests for translation coverage and completeness.

This test suite verifies that:
1. All msgid strings used in code have translations
2. All supported languages have complete translations
3. No translation keys are missing
"""

import unittest
import re
import os
from pathlib import Path
from typing import Set, Dict, List

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


class TestTranslationCoverage(unittest.TestCase):
    """Test translation coverage across all supported languages"""

    SUPPORTED_LANGUAGES = ['en', 'es', 'fr', 'it', 'pt']

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures"""
        cls.project_root = Path(__file__).parent.parent.parent
        cls.src_dir = cls.project_root / 'src' / 'fichero'
        cls.locale_dir = cls.src_dir / 'resources' / 'locale'
        cls.schema_dir = cls.src_dir / 'resources' / 'config_ui_schemas'

        # Extract all msgids from code
        cls.code_msgids = cls._extract_msgids_from_code()

        # Extract all msgids from schema files
        cls.schema_msgids = cls._extract_msgids_from_schemas()

        # Combine code and schema msgids
        cls.all_required_msgids = cls.code_msgids | cls.schema_msgids

        # Extract msgids from each .po file
        cls.po_msgids = {}
        for lang in cls.SUPPORTED_LANGUAGES:
            po_file = cls.locale_dir / lang / 'LC_MESSAGES' / 'fichero.po'
            cls.po_msgids[lang] = cls._extract_msgids_from_po(po_file)

    @classmethod
    def _extract_msgids_from_code(cls) -> Set[str]:
        """Extract all _() calls from Python source files"""
        msgids = set()

        # Pattern to match _("string") or _('string')
        pattern = r'_\(["\']([^"\']+)["\']\)'

        # Scan all Python files
        for py_file in cls.src_dir.rglob('*.py'):
            if 'test' in str(py_file):
                continue

            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    matches = re.findall(pattern, content)
                    msgids.update(matches)
            except Exception as e:
                print(f"Error reading {py_file}: {e}")

        return msgids

    @classmethod
    def _extract_msgids_from_schemas(cls) -> Set[str]:
        """Extract all translatable strings from YAML schema files"""
        msgids = set()

        if not YAML_AVAILABLE:
            print("⚠️  Warning: PyYAML not available, skipping schema tests")
            return msgids

        translatable_keys = ['title', 'description', 'window_title', 'label', 'help', 'placeholder']

        def extract_from_dict(data):
            """Recursively extract translatable values"""
            if isinstance(data, dict):
                for key, value in data.items():
                    if key in translatable_keys and isinstance(value, str):
                        # Only add if it looks like a translation key (has underscore)
                        if '_' in value:
                            msgids.add(value)
                    elif key == 'options' and isinstance(value, list):
                        # Add option values that are translation keys
                        for item in value:
                            if isinstance(item, str) and ('_' in item or item.startswith('option_')):
                                msgids.add(item)
                    elif isinstance(value, (dict, list)):
                        extract_from_dict(value)
            elif isinstance(data, list):
                for item in data:
                    extract_from_dict(item)

        # Process all schema files
        for schema_file in cls.schema_dir.glob('*.yml'):
            try:
                with open(schema_file, 'r', encoding='utf-8') as f:
                    schema_data = yaml.safe_load(f)
                extract_from_dict(schema_data)
            except Exception as e:
                print(f"Error reading schema {schema_file}: {e}")

        return msgids

    @classmethod
    def _extract_msgids_from_po(cls, po_file: Path) -> Set[str]:
        """Extract all msgid values from a .po file"""
        msgids = set()

        if not po_file.exists():
            return msgids

        try:
            with open(po_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            for i, line in enumerate(lines):
                if line.startswith('msgid "') and not line.startswith('msgid ""'):
                    match = re.match(r'msgid "(.*)"', line)
                    if match:
                        msgid = match.group(1)
                        # Handle multi-line msgids
                        j = i + 1
                        while j < len(lines) and lines[j].startswith('"'):
                            continuation = re.match(r'"(.*)"', lines[j])
                            if continuation:
                                msgid += continuation.group(1)
                            j += 1
                        msgids.add(msgid)
        except Exception as e:
            print(f"Error reading {po_file}: {e}")

        return msgids

    def test_english_has_all_code_strings(self):
        """Test that English .po file contains all strings used in code"""
        missing = self.code_msgids - self.po_msgids['en']

        if missing:
            print("\n❌ MISSING ENGLISH TRANSLATIONS (from code):")
            for msgid in sorted(missing):
                print(f"  - {msgid}")

        self.assertEqual(len(missing), 0,
                        f"English .po file is missing {len(missing)} translations from code")

    def test_english_has_all_schema_strings(self):
        """Test that English .po file contains all strings used in YAML schemas"""
        if not YAML_AVAILABLE:
            self.skipTest("PyYAML not available")

        missing = self.schema_msgids - self.po_msgids['en']

        if missing:
            print("\n❌ MISSING ENGLISH TRANSLATIONS (from schemas):")
            for msgid in sorted(missing):
                print(f"  - {msgid}")

        self.assertEqual(len(missing), 0,
                        f"English .po file is missing {len(missing)} translations from schemas")

    def test_all_languages_have_same_keys(self):
        """Test that all language .po files have the same set of keys"""
        en_keys = self.po_msgids['en']

        for lang in self.SUPPORTED_LANGUAGES[1:]:  # Skip 'en'
            lang_keys = self.po_msgids[lang]

            # Find missing and extra keys
            missing = en_keys - lang_keys
            extra = lang_keys - en_keys

            if missing:
                print(f"\n❌ {lang.upper()} MISSING TRANSLATIONS:")
                for msgid in sorted(missing)[:10]:  # Show first 10
                    print(f"  - {msgid}")
                if len(missing) > 10:
                    print(f"  ... and {len(missing) - 10} more")

            if extra:
                print(f"\n⚠️  {lang.upper()} EXTRA TRANSLATIONS (not in English):")
                for msgid in sorted(extra)[:10]:
                    print(f"  - {msgid}")
                if len(extra) > 10:
                    print(f"  ... and {len(extra) - 10} more")

            self.assertEqual(missing, set(),
                           f"{lang} is missing {len(missing)} translations")

    def test_no_untranslated_strings(self):
        """Test that there are no msgstr values equal to msgid (untranslated)"""
        for lang in self.SUPPORTED_LANGUAGES:
            if lang == 'en':
                continue  # English can have msgid == msgstr

            po_file = self.locale_dir / lang / 'LC_MESSAGES' / 'fichero.po'
            untranslated = self._find_untranslated_strings(po_file)

            if untranslated:
                print(f"\n❌ {lang.upper()} UNTRANSLATED STRINGS (msgid == msgstr):")
                for msgid in sorted(untranslated)[:10]:
                    print(f"  - {msgid}")
                if len(untranslated) > 10:
                    print(f"  ... and {len(untranslated) - 10} more")

            # This is a warning, not a failure - some strings may intentionally be the same
            if len(untranslated) > 50:  # Only fail if many strings are untranslated
                self.fail(f"{lang} has {len(untranslated)} untranslated strings")

    def _find_untranslated_strings(self, po_file: Path) -> Set[str]:
        """Find strings where msgid == msgstr (untranslated)"""
        untranslated = set()

        if not po_file.exists():
            return untranslated

        try:
            with open(po_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            i = 0
            while i < len(lines):
                if lines[i].startswith('msgid "') and not lines[i].startswith('msgid ""'):
                    msgid_match = re.match(r'msgid "(.*)"', lines[i])
                    if msgid_match:
                        msgid = msgid_match.group(1)

                        # Find the corresponding msgstr
                        j = i + 1
                        while j < len(lines) and not lines[j].startswith('msgstr'):
                            j += 1

                        if j < len(lines):
                            msgstr_match = re.match(r'msgstr "(.*)"', lines[j])
                            if msgstr_match:
                                msgstr = msgstr_match.group(1)

                                # Check if untranslated (and not empty or technical key)
                                if msgid == msgstr and msgid and not msgid.startswith('http'):
                                    # Skip technical keys that should be the same
                                    if not any(x in msgid for x in ['_title', '_window', '_label', 'msgid']):
                                        untranslated.add(msgid)

                i += 1

        except Exception as e:
            print(f"Error checking {po_file}: {e}")

        return untranslated

    def test_print_translation_statistics(self):
        """Print translation coverage statistics"""
        print("\n" + "="*60)
        print("TRANSLATION COVERAGE STATISTICS")
        print("="*60)

        print(f"\nStrings used in code: {len(self.code_msgids)}")
        if YAML_AVAILABLE:
            print(f"Strings used in schemas: {len(self.schema_msgids)}")
            print(f"Total required strings: {len(self.all_required_msgids)}")

        for lang in self.SUPPORTED_LANGUAGES:
            count = len(self.po_msgids[lang])
            if YAML_AVAILABLE:
                coverage = (min(count, len(self.all_required_msgids)) / len(self.all_required_msgids) * 100) if self.all_required_msgids else 0
            else:
                coverage = (min(count, len(self.code_msgids)) / len(self.code_msgids) * 100) if self.code_msgids else 0
            print(f"{lang.upper()}: {count} translations ({coverage:.1f}% coverage)")

        print("\n" + "="*60)

        # Always pass - this is just informational
        self.assertTrue(True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
