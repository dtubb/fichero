#!/usr/bin/env python3
"""Update workflow YAML files to use new unified transcribe tool"""

import re
from pathlib import Path

PLANS_DIR = Path("src/fichero/resources/config_defaults/plans")

FILES_TO_UPDATE = [
    "Default_English.yml",
    "Enhance_Images_and_Catalogue.yml",
    "Segment_and_Catalogue.yml",
    "Quotations.yml"
]

def update_transcribe_commands(content):
    """Update transcribe command definitions"""

    # Pattern 1: transcribe_qwen_max with direct call
    pattern1 = r'function: "fichero\.tools\.transcribe_qwen_max\.transcribe_batch"'
    replacement1 = 'function: "fichero.tools.transcribe.transcribe_batch"'
    content = re.sub(pattern1, replacement1, content)

    # Pattern 2: Add provider and model args after output_folder
    # Find blocks with transcribe_qwen_max function calls
    def add_provider_args(match):
        block = match.group(0)
        # Check if provider already exists
        if 'provider:' in block:
            return block

        # Add provider and model after output_folder
        lines = block.split('\n')
        new_lines = []
        for i, line in enumerate(lines):
            new_lines.append(line)
            if 'output_folder:' in line:
                # Get indentation
                indent = len(line) - len(line.lstrip())
                new_lines.append(' ' * indent + 'provider: "dashscope"')
                new_lines.append(' ' * indent + 'model: "qwen-vl-max"')

        return '\n'.join(new_lines)

    # Match command blocks that have transcribe.transcribe_batch
    pattern2 = r'(- name: transcribe.*?\n.*?function: "fichero\.tools\.transcribe\.transcribe_batch".*?\n.*?args:.*?(?=\n  - name:|\nworkflows:|\Z))'
    content = re.sub(pattern2, add_provider_args, content, flags=re.DOTALL)

    return content

def main():
    for filename in FILES_TO_UPDATE:
        filepath = PLANS_DIR / filename

        if not filepath.exists():
            print(f"⚠️  File not found: {filepath}")
            continue

        print(f"📝 Updating {filename}...")

        # Read file
        content = filepath.read_text()

        # Update content
        updated_content = update_transcribe_commands(content)

        # Write back if changed
        if content != updated_content:
            filepath.write_text(updated_content)
            print(f"✅ Updated {filename}")
        else:
            print(f"ℹ️  No changes needed for {filename}")

if __name__ == "__main__":
    main()
