from pathlib import Path
from typing import List, Dict, Union
from .image_format import get_supported_extensions_list

def batch_check_files(files_to_check: List[Path], batch_size: int = 100) -> Dict[Path, bool]:
    """Check existence of multiple files in batches to reduce disk seeks"""
    results = {}
    for i in range(0, len(files_to_check), batch_size):
        batch = files_to_check[i:i + batch_size]
        for path in batch:
            results[path] = path.exists()
    return results

def ensure_dirs(path: Path):
    """Ensure all parent directories exist"""
    path.parent.mkdir(parents=True, exist_ok=True)

def get_image_files(folder: Path, patterns: List[str] = None) -> List[Path]:
    """Get all image files in a folder and subfolders"""
    if patterns is None:
        patterns = get_supported_extensions_list()
    files = []
    for pattern in patterns:
        # Handle both with and without dot prefix
        ext = pattern if pattern.startswith('.') else f'.{pattern}'
        # Try all case variations
        files.extend(folder.glob(f"**/*{ext}"))  # lowercase
        files.extend(folder.glob(f"**/*{ext.upper()}"))  # uppercase
        files.extend(folder.glob(f"**/*{ext.capitalize()}"))  # capitalized
        # Also try without the dot for the glob pattern
        ext_no_dot = ext[1:] if ext.startswith('.') else ext
        files.extend(folder.glob(f"**/*.{ext_no_dot}"))  # lowercase
        files.extend(folder.glob(f"**/*.{ext_no_dot.upper()}"))  # uppercase
        files.extend(folder.glob(f"**/*.{ext_no_dot.capitalize()}"))  # capitalized
    return sorted(set(files))  # Remove duplicates and sort

def get_skip_files() -> List[str]:
    """Get list of files to skip processing"""
    return ['']

def get_relative_path(file_path: Union[str, Path], base_folder: Path = None) -> Path:
    """
    Get relative path from documents/ onwards.
    Always returns a relative path, removing any absolute path components.
    """
    file_path = Path(file_path)
    
    # If base_folder is provided, make path relative to it
    if base_folder:
        try:
            return file_path.relative_to(base_folder)
        except ValueError:
            pass
    
    # Try to get path relative to cwd
    try:
        rel_path = file_path.relative_to(Path.cwd())
    except ValueError:
        rel_path = file_path
        
    # Handle documents prefix
    path_str = str(rel_path)
    if 'documents/' in path_str:
        parts = path_str.split('documents/')
        if len(parts) > 1:
            return Path(parts[1])
    return rel_path

def reconstruct_input_path(base_folder: Path, source_path: str) -> Path:
    """Build full input path from base folder and manifest source path"""
    return base_folder / source_path

def get_relative_output_path(source_path: str) -> str:
    """Convert input manifest source path to output path"""
    return source_path
