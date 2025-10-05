from pathlib import Path
from datetime import datetime
from typing import Callable, Any
from fichero.tools.utils.image_format import get_supported_extensions_list
from fichero.tools.utils.files import get_relative_path, ensure_dirs

# Support both standalone CLI usage and workflow executor imports
try:
    # When imported by workflow executor (absolute imports work)
    from fichero.tools.utils.tool_logger import get_tool_logger
except ImportError:
    # When run as standalone script (relative imports work)
    from tool_logger import get_tool_logger

tool_logger = get_tool_logger('processor')

def process_file(
    file_path: str,
    output_folder: Path,
    process_fn: Callable[[Path, Path], Any],
    file_types: dict = None
) -> dict:
    """Generic file processor with robust error handling"""
    file_path = Path(file_path)  # Ensure file_path is a Path object
    
    # Get relative path using utility function
    rel_path = get_relative_path(file_path)
    
    # Create output path
    out_path = output_folder / "documents" / rel_path
    
    manifest_entry = {
        "source": str(rel_path),  # Store just the relative path
        "outputs": [],  # Will be populated with actual output paths
        "processed_at": datetime.now().isoformat(),
        "success": False,
        "details": {}
    }
    
    try:
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # PATCH: Accept file if file_types is provided and extension is in file_types
        # Also accept files without extensions (they might be valid images)
        if file_types and file_path.suffix.lower() not in file_types and file_path.suffix:
            raise ValueError(f"Unsupported file type: {file_path.suffix}")
        
        # Ensure output directory exists using utility function
        ensure_dirs(out_path)
        
        # For skipped files, keep the expected output path
        if out_path.exists():
            # Get the relative path for the output file (not the input file)
            output_rel_path = get_relative_path(out_path)
            manifest_entry.update({
                "success": True,
                "skipped": True,
                "outputs": [str(output_rel_path)]  # Use actual output path for skipped files
            })
            return manifest_entry
        
        # Process only if file doesn't exist
        result = process_fn(file_path, out_path)
        if isinstance(result, dict):
            # Use the outputs directly from the result
            # The process_fn should return the correct output paths
            manifest_entry.update(result)
        manifest_entry["success"] = True
        
        return manifest_entry
        
    except Exception as e:
        tool_logger.error(f"Error processing {file_path}: {str(e)}")
        manifest_entry["error"] = f"{type(e).__name__}: {str(e)}"
        return manifest_entry
