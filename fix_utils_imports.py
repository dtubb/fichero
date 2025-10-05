#!/usr/bin/env python3
"""
Fix all utils module internal imports to use fichero.tools.utils.* paths
"""
import re
from pathlib import Path

# Map of incorrect imports to correct imports
IMPORT_FIXES = {
    'from fichero.batch import': 'from fichero.tools.utils.batch import',
    'from fichero.tool_logger import': 'from fichero.tools.utils.tool_logger import',
    'from fichero.manifest import': 'from fichero.tools.utils.manifest import',
    'from fichero.image_format import': 'from fichero.tools.utils.image_format import',
    'from fichero.segment_handler import': 'from fichero.tools.utils.segment_handler import',
    'from fichero.files import': 'from fichero.tools.utils.files import',
    'from fichero.api_keys import': 'from fichero.tools.utils.api_keys import',
    'from fichero.processor import': 'from fichero.tools.utils.processor import',
    'from fichero.progress import': 'from fichero.tools.utils.progress import',
    'from fichero.hierarchy import': 'from fichero.tools.utils.hierarchy import',
    'from fichero.llm_utils import': 'from fichero.tools.utils.llm_utils import',
}

def fix_imports_in_file(file_path: Path) -> int:
    """Fix imports in a single file. Returns number of fixes made."""
    content = file_path.read_text()
    original_content = content
    fixes_made = 0

    for old_import, new_import in IMPORT_FIXES.items():
        if old_import in content:
            # Count occurrences before replacing
            count_before = content.count(old_import)
            content = content.replace(old_import, new_import)
            fixes_made += count_before

    if content != original_content:
        file_path.write_text(content)
        print(f"✅ Fixed {fixes_made} imports in {file_path.name}")
        return fixes_made
    else:
        print(f"⏭️  No fixes needed in {file_path.name}")
        return 0

def main():
    utils_dir = Path('src/fichero/tools/utils')
    total_fixes = 0
    files_fixed = 0

    print("🔧 Fixing utils internal imports...\n")

    for util_file in sorted(utils_dir.glob('*.py')):
        fixes = fix_imports_in_file(util_file)
        if fixes > 0:
            files_fixed += 1
            total_fixes += fixes

    print(f"\n✅ Complete! Fixed {total_fixes} imports in {files_fixed} files")

if __name__ == '__main__':
    main()
