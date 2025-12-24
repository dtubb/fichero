from pathlib import Path
from typing import List, Dict, Union
from fichero.tools.utils.image_format import get_supported_extensions_list

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
    
    # Get all files recursively first
    all_files = list(folder.rglob("*"))
    
    # Then filter by extension
    for file_path in all_files:
        if not file_path.is_file():
            continue
            
        # Get extension in lowercase for comparison
        ext = file_path.suffix.lower()
        
        # Check if extension matches any pattern (case-insensitive)
        if any(ext == pattern.lower() or ext == f".{pattern.lower()}" for pattern in patterns):
            files.append(file_path)
            
    return sorted(set(files))  # Remove duplicates and sort

def get_skip_files() -> List[str]:
    """Get list of files to skip processing"""
    return ['']

def get_relative_path(file_path: Union[str, Path], base_folder: Path = None) -> Path:
    """
    Get relative path from documents/ or _staging/ onwards.
    Always returns a relative path, removing any absolute path components.
    Handles special characters in paths consistently.
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

    # Handle common base folders by working with Path objects
    # Look for: documents/, _staging/, or just return the filename if it's in one of these
    parts = rel_path.parts
    # Create lowercase version of parts for case-insensitive matching
    # This handles Documents/documents/DOCUMENTS etc.
    parts_lower = tuple(p.lower() for p in parts)

    # Check for known folder markers (documents, _staging, assets, processing folders)
    # Find the DEEPEST/LAST marker to strip the most path context
    # Use case-insensitive matching to handle Documents vs documents
    folder_markers = ['documents', '_staging', 'assets', 'crops', 'split', 'rotated', 'enhanced', 'background_removed', 'segmented']
    deepest_marker_index = -1
    for marker in folder_markers:
        # Search through all parts (case-insensitive) and find the LAST occurrence
        for i, part_lower in enumerate(parts_lower):
            if part_lower == marker:
                if i > deepest_marker_index:
                    deepest_marker_index = i

    # If we found a marker, return everything after the deepest one
    if deepest_marker_index >= 0 and deepest_marker_index < len(parts) - 1:
        return Path(*parts[deepest_marker_index + 1:])

    # If still absolute, just return the filename (last resort)
    if rel_path.is_absolute():
        return Path(rel_path.name)

    return rel_path

def reconstruct_input_path(base_folder: Path, source_path: str) -> Path:
    """
    Build full input path from base folder and manifest source path.
    Handles special characters in paths consistently.
    """
    # Convert source_path to Path to handle special characters properly
    source_path = Path(source_path)
    return base_folder / source_path

def get_relative_output_path(source_path: str) -> str:
    """Convert input manifest source path to output path"""
    return source_path
