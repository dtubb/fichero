#!/usr/bin/env python3
"""
Import Audit Script for Fichero iOS Compatibility

Scans all Python files in the codebase to find imports that might not be available
in the iOS build, based on the pyproject.toml dependencies.
"""

import ast
import os
from pathlib import Path
from typing import Dict, List, Set, Tuple
import re

# iOS dependencies from pyproject.toml
IOS_DEPENDENCIES = {
    "toga-core", "toga-iOS", "toga", "python-dotenv", "Pillow", "numpy", 
    "requests", "cryptography", "ruamel.yaml", "pathvalidate", "openai", 
    "dashscope", "std-nslog", "travertino", "fonttools", "rubicon-objc",
    "charset_normalizer", "idna", "urllib3", "certifi", "cffi", "pycparser",
    "aiohttp", "websocket-client", "aiohappyeyeballs", "aiosignal", "attrs",
    "frozenlist", "multidict", "yarl", "async-timeout", "propcache", "anyio",
    "distro", "httpx", "httpcore", "h11", "pydantic", "typing-extensions",
    "exceptiongroup"
}

# Standard library modules that should always be available
STDLIB_MODULES = {
    'abc', 'argparse', 'asyncio', 'base64', 'collections', 'contextlib',
    'copy', 'datetime', 'enum', 'functools', 'gettext', 'glob', 'gzip',
    'hashlib', 'importlib', 'inspect', 'io', 'itertools', 'json', 'locale',
    'logging', 'math', 'operator', 'os', 'pathlib', 'pickle', 'platform',
    'random', 're', 'shutil', 'signal', 'socket', 'stat', 'string', 'subprocess',
    'sys', 'tempfile', 'textwrap', 'threading', 'time', 'traceback', 'typing',
    'types', 'unittest', 'urllib', 'uuid', 'warnings', 'weakref', 'zipfile',
    'queue', 'webbrowser', 'multiprocessing'
}

# Built-in modules
BUILTIN_MODULES = {
    '__builtin__', 'builtins', 'codecs', 'errno', 'fcntl', 'gc', 'imp',
    'marshal', 'posix', 'pwd', 'select', 'site', 'sysconfig', 'thread'
}

class ImportAuditor:
    def __init__(self, src_dir: str = "src/fichero"):
        self.src_dir = Path(src_dir)
        self.imports_found: Dict[str, Set[str]] = {}
        self.problematic_imports: Dict[str, List[str]] = {}
        
    def scan_file(self, file_path: Path) -> Dict[str, Set[str]]:
        """Scan a single Python file for imports"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content)
            imports = set()
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.add(node.module)
            
            return {str(file_path): imports}
            
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            return {str(file_path): set()}
    
    def scan_directory(self) -> None:
        """Scan all Python files in the source directory"""
        print(f"Scanning {self.src_dir} for imports...")
        
        for py_file in self.src_dir.rglob("*.py"):
            if "test" not in str(py_file) and "tests" not in str(py_file):
                file_imports = self.scan_file(py_file)
                self.imports_found.update(file_imports)
    
    def analyze_imports(self) -> None:
        """Analyze imports for iOS compatibility issues"""
        print("\nAnalyzing imports for iOS compatibility...")
        
        all_imports = set()
        for imports in self.imports_found.values():
            all_imports.update(imports)
        
        # Filter out standard library, built-in modules, and internal fichero modules
        external_imports = set()
        internal_fichero_modules = set()
        
        for imp in all_imports:
            if imp.startswith('fichero.') or imp == 'fichero':
                internal_fichero_modules.add(imp)
            elif imp not in STDLIB_MODULES and imp not in BUILTIN_MODULES:
                external_imports.add(imp)
        
        # Check which external imports are not in iOS dependencies
        missing_imports = external_imports - IOS_DEPENDENCIES
        
        print(f"\nTotal unique imports found: {len(all_imports)}")
        print(f"Internal fichero modules: {len(internal_fichero_modules)}")
        print(f"External imports: {len(external_imports)}")
        print(f"Missing from iOS dependencies: {len(missing_imports)}")
        
        if missing_imports:
            print("\n🚨 EXTERNAL IMPORTS MISSING FROM iOS DEPENDENCIES:")
            for imp in sorted(missing_imports):
                print(f"  - {imp}")
                
            # Find which files use these missing imports
            print("\n📁 FILES USING MISSING EXTERNAL IMPORTS:")
            for missing_imp in sorted(missing_imports):
                files_using = []
                for file_path, imports in self.imports_found.items():
                    if missing_imp in imports:
                        files_using.append(file_path)
                
                if files_using:
                    print(f"\n  {missing_imp}:")
                    for file_path in files_using[:5]:  # Show first 5 files
                        print(f"    - {file_path}")
                    if len(files_using) > 5:
                        print(f"    ... and {len(files_using) - 5} more files")
        else:
            print("\n✅ All external imports are covered by iOS dependencies!")
        
        # Show what's actually in iOS dependencies
        print(f"\n📦 iOS DEPENDENCIES ({len(IOS_DEPENDENCIES)} total):")
        for dep in sorted(IOS_DEPENDENCIES):
            print(f"  - {dep}")
    
    def focus_on_main_components(self) -> None:
        """Focus analysis on main window and settings components"""
        print("\n🔍 FOCUSING ON MAIN COMPONENTS:")
        
        main_components = [
            "src/fichero/windows/main",
            "src/fichero/windows/settings", 
            "src/fichero/config/core",
            "src/fichero/app.py"
        ]
        
        for component in main_components:
            component_path = Path(component)
            if component_path.exists():
                print(f"\n📂 {component}:")
                component_imports = set()
                
                if component_path.is_file():
                    # Single file
                    file_imports = self.scan_file(component_path)
                    component_imports.update(list(file_imports.values())[0])
                else:
                    # Directory
                    for py_file in component_path.rglob("*.py"):
                        if "test" not in str(py_file):
                            file_imports = self.scan_file(py_file)
                            component_imports.update(list(file_imports.values())[0])
                
                # Check for missing external imports in this component
                external_imports = set()
                for imp in component_imports:
                    if not imp.startswith('fichero.') and imp != 'fichero' and imp not in STDLIB_MODULES and imp not in BUILTIN_MODULES:
                        external_imports.add(imp)
                
                missing_in_component = external_imports - IOS_DEPENDENCIES
                
                if missing_in_component:
                    print(f"  🚨 Missing external imports: {', '.join(sorted(missing_in_component))}")
                else:
                    print(f"  ✅ All external imports covered")
                
                print(f"  📊 Total imports: {len(component_imports)}")
                print(f"  📊 External imports: {len(external_imports)}")
    
    def check_specific_problematic_imports(self) -> None:
        """Check for specific imports that commonly cause iOS issues"""
        print("\n🔍 CHECKING FOR COMMON iOS PROBLEM IMPORTS:")
        
        problematic_patterns = [
            'typer', 'rich', 'srsly', 'pytesseract', 'opencv', 'cv2', 
            'ultralytics', 'redis', 'celery', 'openpyxl', 'pandas',
            'langchain', 'langchain_ollama', 'rembg'
        ]
        
        for pattern in problematic_patterns:
            files_using = []
            for file_path, imports in self.imports_found.items():
                if any(pattern in imp for imp in imports):
                    files_using.append(file_path)
            
            if files_using:
                print(f"\n  🚨 {pattern}:")
                for file_path in files_using[:3]:  # Show first 3 files
                    print(f"    - {file_path}")
                if len(files_using) > 3:
                    print(f"    ... and {len(files_using) - 3} more files")
            else:
                print(f"  ✅ {pattern}: Not found")
    
    def run_audit(self) -> None:
        """Run the complete import audit"""
        print("🔍 FICHERO IMPORT AUDIT FOR iOS COMPATIBILITY")
        print("=" * 60)
        
        self.scan_directory()
        self.analyze_imports()
        self.focus_on_main_components()
        self.check_specific_problematic_imports()
        
        print("\n" + "=" * 60)
        print("Audit complete!")

if __name__ == "__main__":
    auditor = ImportAuditor()
    auditor.run_audit() 