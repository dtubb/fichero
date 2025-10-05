#!/usr/bin/env python3
"""
Fix all tool imports to use fichero.tools.utils.* paths
"""
import re
from pathlib import Path

# Map of incorrect imports to correct imports
IMPORT_FIXES = {
    'from utils.batch import': 'from fichero.tools.utils.batch import',
    'from utils.processor import': 'from fichero.tools.utils.processor import',
    'from utils.segment_handler import': 'from fichero.tools.utils.segment_handler import',
    'from utils.files import': 'from fichero.tools.utils.files import',
    'from utils.manifest import': 'from fichero.tools.utils.manifest import',
    'from utils.tool_logger import': 'from fichero.tools.utils.tool_logger import',
    'from utils.image_format import': 'from fichero.tools.utils.image_format import',
    'from utils.parallel_batch_processor import': 'from fichero.tools.utils.parallel_batch_processor import',
    'from utils.progress import': 'from fichero.tools.utils.progress import',
    'from utils.llm_utils import': 'from fichero.tools.utils.llm_utils import',
    'from utils.hierarchy import': 'from fichero.tools.utils.hierarchy import',
    'from utils.api_keys import': 'from fichero.tools.utils.api_keys import',
}

def fix_imports_in_file(file_path: Path) -> int:
    """Fix imports in a single file. Returns number of fixes made."""
    content = file_path.read_text()
    original_content = content
    fixes_made = 0

    for old_import, new_import in IMPORT_FIXES.items():
        if old_import in content:
            content = content.replace(old_import, new_import)
            fixes_made += content.count(new_import) - original_content.count(new_import)

    if content != original_content:
        file_path.write_text(content)
        print(f"✅ Fixed {fixes_made} imports in {file_path.name}")
        return fixes_made
    else:
        print(f"⏭️  No fixes needed in {file_path.name}")
        return 0

def main():
    tools_dir = Path('src/fichero/tools')
    total_fixes = 0
    files_fixed = 0

    print("🔧 Fixing tool imports...\n")

    for tool_file in sorted(tools_dir.glob('*.py')):
        if tool_file.name == '__init__.py':
            continue

        fixes = fix_imports_in_file(tool_file)
        if fixes > 0:
            files_fixed += 1
            total_fixes += fixes

    print(f"\n✅ Complete! Fixed {total_fixes} imports in {files_fixed} files")

if __name__ == '__main__':
    main()
