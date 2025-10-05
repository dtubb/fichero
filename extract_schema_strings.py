#!/usr/bin/env python3
"""Extract all translatable strings from YAML schema files."""

import yaml
from pathlib import Path

schema_dir = Path('src/fichero/resources/config_ui_schemas')
schema_files = list(schema_dir.glob('*.yml'))

all_strings = set()

def extract_translatable_fields(data, parent_key=''):
    """Recursively extract translatable field values."""
    translatable_keys = [
        'title', 'description', 'window_title', 'label',
        'help', 'placeholder', 'options'
    ]

    if isinstance(data, dict):
        for key, value in data.items():
            if key in translatable_keys:
                if isinstance(value, str):
                    all_strings.add(value)
                elif isinstance(value, list):
                    # For options lists, add each item
                    for item in value:
                        if isinstance(item, str):
                            all_strings.add(item)
            elif isinstance(value, (dict, list)):
                extract_translatable_fields(value, key)
    elif isinstance(data, list):
        for item in data:
            extract_translatable_fields(item, parent_key)

print("Extracting translatable strings from schema files...\n")

for schema_file in sorted(schema_files):
    print(f"Reading {schema_file.name}...")
    with open(schema_file, 'r') as f:
        schema_data = yaml.safe_load(f)
    extract_translatable_fields(schema_data)

# Filter out non-translation keys (raw values vs keys)
# Translation keys typically contain underscores or specific patterns
translation_keys = sorted([s for s in all_strings if '_' in s or s.startswith('option_')])
non_keys = sorted([s for s in all_strings if '_' not in s and not s.startswith('option_')])

print(f"\nFound {len(translation_keys)} translation keys:")
for key in translation_keys:
    print(f"  {key}")

print(f"\nFound {len(non_keys)} hardcoded strings (may need translation):")
for key in non_keys:
    print(f"  {key}")

# Save to file for testing
with open('schema_translation_keys.txt', 'w') as f:
    for key in translation_keys:
        f.write(f"{key}\n")

print(f"\nTranslation keys saved to schema_translation_keys.txt")
