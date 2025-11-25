#!/usr/bin/env python3
"""Add provider and model arguments to transcribe commands"""

import re
from pathlib import Path

PLANS_DIR = Path("src/fichero/resources/config_defaults/plans")

FILES = [
    "Default_English.yml",
    "Enhance_Images_and_Catalogue.yml",
    "Segment_and_Catalogue.yml",
    "Quotations.yml",
    "Generic_Catalogue.yml"
]

def add_provider_args(content):
    """Add provider and model arguments after output_folder"""

    lines = content.split('\n')
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]
        result.append(line)

        # Check if this is a transcribe command with output_folder
        if 'output_folder:' in line and i > 0:
            # Look back to see if this is a transcribe command
            lookback = '\n'.join(lines[max(0, i-10):i+1])
            if 'transcribe' in lookback and 'function: "fichero.tools.transcribe.transcribe_batch"' in lookback:
                # Check if provider already exists in next few lines
                has_provider = False
                for j in range(i+1, min(i+5, len(lines))):
                    if 'provider:' in lines[j]:
                        has_provider = True
                        break

                if not has_provider:
                    # Get indentation from current line
                    indent = len(line) - len(line.lstrip())
                    # Add provider and model
                    result.append(' ' * indent + 'provider: "dashscope"')
                    result.append(' ' * indent + 'model: "qwen-vl-max"')

        i += 1

    return '\n'.join(result)

def main():
    for filename in FILES:
        filepath = PLANS_DIR / filename
        if not filepath.exists():
            print(f"⚠️  {filename} not found")
            continue

        print(f"📝 Processing {filename}...")
        content = filepath.read_text()
        updated = add_provider_args(content)

        if content != updated:
            filepath.write_text(updated)
            print(f"✅ Updated {filename}")
        else:
            print(f"ℹ️  No changes for {filename}")

if __name__ == "__main__":
    main()
