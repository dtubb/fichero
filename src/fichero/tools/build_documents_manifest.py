import typer
import srsly
from pathlib import Path
import os
import re

# Always use absolute imports from fichero.tools.utils
from fichero.tools.utils.files import get_image_files, ensure_dirs, get_relative_path
from fichero.tools.utils.image_format import get_supported_extensions, get_supported_extensions_list, InputFormat
from fichero.tools.utils.tool_logger import get_tool_logger

tool_logger = get_tool_logger('build_documents_manifest')

def natural_sort_key(s: str):
    """Sort strings alphanumerically like Finder."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def build_documents_manifest_batch(
    source_folder: Path,
    output_manifest: Path,
    **kwargs
) -> dict:
    """
    Generate the documents manifest listing - importable function
    
    Args:
        source_folder: Directory to scan for files and folders
        output_manifest: Output file path (.jsonl)
        
    Returns:
        Processing statistics dictionary
    """
    # Safely handle the path with special characters and spaces
    source_folder = Path(os.path.expanduser(str(source_folder))).resolve()
    output_manifest = Path(os.path.expanduser(str(output_manifest))).resolve()
    
    tool_logger.progress(f"Scanning directory: {source_folder}")
    
    # Convert to .jsonl extension and ensure it is in the manifests directory
    output_manifest = output_manifest.with_suffix('.jsonl')
    
    # Ensure the directory for the manifest file exists
    ensure_dirs(output_manifest)
    
    entries = []
    
    # Get supported extensions
    supported_extensions = get_supported_extensions()
    supported_list = get_supported_extensions_list()
    
    # Create case-insensitive extension mapping
    ext_map = {ext.lower(): ext for ext in supported_list}
    
    tool_logger.info("Supported image formats:")
    for ext, process_fn in supported_extensions.items():
        tool_logger.info(f"  - {ext} ({process_fn})")
    
    # Get all image files using the utility function
    tool_logger.progress("Scanning for image files...")
    image_files = get_image_files(source_folder)
    tool_logger.info(f"Found {len(image_files)} image files")
    
    # Debug: Print all found files
    tool_logger.debug("Found files:")
    for f in sorted(image_files):
        tool_logger.debug(f"  - {f}")
    
    # Process directories first
    tool_logger.progress("Processing directories...")
    for root, dirs, _ in os.walk(source_folder):
        root_path = Path(root)
        for d in dirs:
            rel_path = root_path.joinpath(d).relative_to(source_folder)
            entries.append({
                "path": str(rel_path),
                "type": "directory"
            })
    
    # Process image files
    tool_logger.progress("Processing image files...")
    for file_path in image_files:
        try:
            rel_path = get_relative_path(file_path, source_folder)
            ext = file_path.suffix.lower()
            
            # Debug: Print file being processed
            tool_logger.debug(f"  Processing: {file_path} (ext: {ext})")
            
            # Verify the extension is supported (case-insensitive)
            if ext not in [e.lower() for e in supported_list]:
                tool_logger.warning(f"Unsupported extension {ext} for file {file_path}")
                continue
                
            # Get the canonical extension (preserving case from supported_list)
            canonical_ext = ext_map.get(ext, ext)
            
            entry = {
                "path": str(rel_path),
                "type": "file",
                "mtime": os.path.getmtime(file_path),
                "size": os.path.getsize(file_path),
                "format": canonical_ext[1:] if canonical_ext.startswith('.') else canonical_ext,
                "process_fn": supported_extensions.get(canonical_ext, 'unknown')
            }
            entries.append(entry)
            tool_logger.debug(f"    Added to manifest: {entry}")
            
        except Exception as e:
            tool_logger.warning(f"Could not process {file_path}: {e}")
    
    # Sort all entries by alphanumeric order of their 'path'
    entries.sort(key=lambda e: natural_sort_key(e["path"]))
    
    # Write the sorted entries to the JSONL file
    srsly.write_jsonl(output_manifest, entries)
    tool_logger.success(f"Saved {len(entries)} entries to {output_manifest}")
    
    # Print summary
    file_count = sum(1 for e in entries if e["type"] == "file")
    dir_count = sum(1 for e in entries if e["type"] == "directory")
    tool_logger.info("Summary:")
    tool_logger.info(f"  - Files: {file_count}")
    tool_logger.info(f"  - Directories: {dir_count}")
    
    # Print format distribution
    formats = {}
    for entry in entries:
        if entry["type"] == "file":
            fmt = entry.get("format", "unknown")
            formats[fmt] = formats.get(fmt, 0) + 1
    
    if formats:
        tool_logger.info("Format distribution:")
        for fmt, count in sorted(formats.items()):
            tool_logger.info(f"  - {fmt}: {count}")
            
    # Print supported extensions for reference
    tool_logger.info(f"Supported extensions: {', '.join(supported_list)}")
    
    # Debug: Print all entries in manifest
    tool_logger.debug("Manifest entries:")
    for entry in entries:
        tool_logger.debug(f"  - {entry}")
    
    return {
        "processed_files": file_count,
        "processed_directories": dir_count,
        "total_entries": len(entries),
        "success": True
    }

def build_documents_manifest(
    documents_dir: Path = typer.Argument(..., help="Directory to scan for files and folders"),
    documents_manifest: Path = typer.Argument(..., help="Output file path (.jsonl)")
):
    """
    Recursively scan the given documents directory and create a JSONL file listing
    all files and subfolders (relative paths only), sorted alphanumerically.
    
    Required, because on a spinning disk, and lots of files, things were too slow.
    """
    return build_documents_manifest_batch(documents_dir, documents_manifest)

if __name__ == "__main__":
    typer.run(build_documents_manifest)