#!/usr/bin/env python3
"""
Check that all Python imports are covered by pyproject.toml dependencies.

Usage:
    python scripts/check_dependencies.py
"""

import ast
import re
import sys
from pathlib import Path
from typing import Set

# Mapping of import names to package names (for cases where they differ)
IMPORT_TO_PACKAGE = {
    "PIL": "Pillow",
    "cv2": "opencv-python-headless",
    "skimage": "scikit-image",
    "yaml": "pyyaml",
    "dotenv": "python-dotenv",
    "multipart": "python-multipart",
    "dateutil": "python-dateutil",
    "bidi": "python-bidi",
    "jwt": "pyjwt",
    "fitz": "PyMuPDF",
    "langchain_core": "langchain-core",
    "langchain_mcp_adapters": "langchain-mcp-adapters",
    "langchain_ollama": "langchain-ollama",
    "langchain_openai": "langchain-openai",
    "langchain_anthropic": "langchain-anthropic",
    "langchain_google_genai": "langchain-google-genai",
    "langchain_community": "langchain-community",
    "langchain_mistralai": "langchain-mistralai",
    "langchain_cohere": "langchain-cohere",
    "langchain_aws": "langchain-aws",
    "langchain_text_splitters": "langchain-text-splitters",
    "langgraph": "langgraph",
    "pydantic_settings": "pydantic-settings",
    "Vision": "pyobjc-framework-Vision",
    "Quartz": "pyobjc-framework-Quartz",
    "Foundation": "pyobjc-framework-Cocoa",
    "AppKit": "pyobjc-framework-Cocoa",
    # Packages that are optional or not needed in production
    "rubicon": "SKIP",  # Not used
    "Speech": "SKIP",  # macOS framework, not used
    "whisper": "SKIP",  # Commented out in pyproject.toml
    "rawpy": "SKIP",  # Optional RAW image support
}

# Python stdlib modules (don't need to be in pyproject.toml)
STDLIB_MODULES = {
    "__future__", "abc", "argparse", "ast", "asyncio", "base64", "collections",
    "concurrent", "contextlib", "copy", "ctypes", "dataclasses", "datetime",
    "enum", "fnmatch", "functools", "hashlib", "io", "json", "logging",
    "mimetypes", "operator", "os", "pathlib", "pickle", "platform", "re",
    "shutil", "socket", "sqlite3", "ssl", "stat", "string", "struct",
    "subprocess", "sys", "tempfile", "threading", "time", "traceback",
    "types", "typing", "unicodedata", "unittest", "urllib", "uuid", "warnings",
    "weakref", "xml", "zipfile", "zlib",
}


def extract_imports_from_file(filepath: Path) -> Set[str]:
    """Extract top-level import names from a Python file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError):
        return set()

    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # Get top-level package (e.g., "langchain_core" from "langchain_core.messages")
                imports.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                # Get top-level package
                imports.add(node.module.split('.')[0])

    return imports


def get_all_imports(source_dirs: list[Path]) -> Set[str]:
    """Get all unique imports from all Python files."""
    all_imports = set()
    for source_dir in source_dirs:
        for py_file in source_dir.rglob("*.py"):
            all_imports.update(extract_imports_from_file(py_file))
    return all_imports


def normalize_package_name(name: str) -> str:
    """Normalize package name (e.g., remove version constraints)."""
    # Remove version specifiers
    for char in ['>', '<', '=', '[', '!']:
        if char in name:
            name = name.split(char)[0]
    return name.strip().lower().replace('_', '-')


def get_pyproject_packages(pyproject_path: Path) -> Set[str]:
    """Extract package names from pyproject.toml."""
    with open(pyproject_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    packages = set()
    in_array = False
    bracket_depth = 0

    for line in lines:
        stripped = line.strip()

        # Check if we're entering a dependency array
        if ('requires = [' in line or 'dependencies = [' in line):
            in_array = True
            bracket_depth = line.count('[') - line.count(']')

        if in_array:
            # Track bracket depth
            bracket_depth += line.count('[') - line.count(']')

            # Extract package names (quoted strings)
            if '"' in line and not stripped.startswith('#'):
                match = re.search(r'"([^"]+)"', line)
                if match:
                    pkg = match.group(1)
                    packages.add(normalize_package_name(pkg))

            # Check if we've closed the array
            if bracket_depth == 0:
                in_array = False

    return packages


def main():
    project_root = Path(__file__).parent.parent
    source_dirs = [
        project_root / "src" / "fichero",
        project_root / "src" / "fichero_backend",
    ]

    print("🔍 Scanning Python files for imports...")
    all_imports = get_all_imports(source_dirs)

    # Filter out stdlib and local imports
    third_party_imports = {
        imp for imp in all_imports
        if imp not in STDLIB_MODULES and not imp.startswith('fichero')
    }

    print(f"   Found {len(third_party_imports)} third-party imports\n")

    # Map imports to package names
    required_packages = set()
    for imp in third_party_imports:
        pkg = IMPORT_TO_PACKAGE.get(imp, imp.replace('_', '-'))
        # Skip packages marked as SKIP
        if pkg != "SKIP":
            required_packages.add(normalize_package_name(pkg))

    print("📦 Reading pyproject.toml...")
    pyproject_path = project_root / "pyproject.toml"
    declared_packages = get_pyproject_packages(pyproject_path)
    print(f"   Found {len(declared_packages)} declared packages\n")

    # Find missing packages
    missing = required_packages - declared_packages

    if missing:
        print("❌ Missing packages in pyproject.toml:")
        print("=" * 60)
        for pkg in sorted(missing):
            # Find which import requires this package
            original_imports = [
                imp for imp in third_party_imports
                if normalize_package_name(IMPORT_TO_PACKAGE.get(imp, imp.replace('_', '-'))) == pkg
            ]
            print(f"  • {pkg:30s} (imported as: {', '.join(original_imports)})")
        print("=" * 60)
        print(f"\nTotal missing: {len(missing)}")
        print("\nAdd these to both sections in pyproject.toml:")
        print("  [tool.briefcase.app.fichero-backend] requires")
        print("  [project] dependencies")
        return 1
    else:
        print("✅ All imports are covered by pyproject.toml dependencies!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
