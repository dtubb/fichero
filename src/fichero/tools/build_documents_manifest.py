import typer
import srsly
from pathlib import Path
import os
import re
from rich.console import Console
from utils.files import get_image_files, ensure_dirs, get_relative_path
from utils.image_format import get_supported_extensions, get_supported_extensions_list, InputFormat

console = Console()

def natural_sort_key(s: str):
    """Sort strings alphanumerically like Finder."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def build_documents_manifest(
    documents_dir: Path = typer.Argument(..., help="Directory to scan for files and folders"),
    documents_manifest: Path = typer.Argument(..., help="Output file path (.jsonl)")
):
    """
    Recursively scan the given documents directory and create a JSONL file listing
    all files and subfolders (relative paths only), sorted alphanumerically.
    
    Required, because on a spinning disk, and lots of files, things were too slow.
    """
    
    # Safely handle the path with special characters and spaces
    documents_dir = Path(os.path.expanduser(str(documents_dir))).resolve()
    documents_manifest = Path(os.path.expanduser(str(documents_manifest))).resolve()
    
    console.print(f"[blue]Scanning directory: {documents_dir}")
    
    # Convert to .jsonl extension and ensure it is in the manifests directory
    documents_manifest = documents_manifest.with_suffix('.jsonl')
    
    # Ensure the directory for the manifest file exists
    ensure_dirs(documents_manifest)
    
    entries = []
    
    # Get supported extensions
    supported_extensions = get_supported_extensions()
    supported_list = get_supported_extensions_list()
    
    # Create case-insensitive extension mapping
    ext_map = {ext.lower(): ext for ext in supported_list}
    
    console.print("[blue]Supported image formats:")
    for ext, process_fn in supported_extensions.items():
        console.print(f"  - {ext} ({process_fn})")
    
    # Get all image files using the utility function
    console.print("\n[blue]Scanning for image files...")
    image_files = get_image_files(documents_dir)
    console.print(f"[green]Found {len(image_files)} image files")
    
    # Debug: Print all found files
    console.print("\n[blue]Found files:")
    for f in sorted(image_files):
        console.print(f"  - {f}")
    
    # Process directories first
    console.print("\n[blue]Processing directories...")
    for root, dirs, _ in os.walk(documents_dir):
        root_path = Path(root)
        for d in dirs:
            rel_path = root_path.joinpath(d).relative_to(documents_dir)
            entries.append({
                "path": str(rel_path),
                "type": "directory"
            })
    
    # Process image files
    console.print("\n[blue]Processing image files...")
    for file_path in image_files:
        try:
            rel_path = get_relative_path(file_path, documents_dir)
            ext = file_path.suffix.lower()
            
            # Debug: Print file being processed
            console.print(f"  Processing: {file_path} (ext: {ext})")
            
            # Verify the extension is supported (case-insensitive)
            if ext not in [e.lower() for e in supported_list]:
                console.print(f"[yellow]Warning: Unsupported extension {ext} for file {file_path}")
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
            console.print(f"    Added to manifest: {entry}")
            
        except Exception as e:
            console.print(f"[yellow]Warning: Could not process {file_path}: {e}")
    
    # Sort all entries by alphanumeric order of their 'path'
    entries.sort(key=lambda e: natural_sort_key(e["path"]))
    
    # Write the sorted entries to the JSONL file
    srsly.write_jsonl(documents_manifest, entries)
    console.print(f"\n[green]Saved {len(entries)} entries to {documents_manifest}")
    
    # Print summary
    file_count = sum(1 for e in entries if e["type"] == "file")
    dir_count = sum(1 for e in entries if e["type"] == "directory")
    console.print(f"\n[blue]Summary:")
    console.print(f"  - Files: {file_count}")
    console.print(f"  - Directories: {dir_count}")
    
    # Print format distribution
    formats = {}
    for entry in entries:
        if entry["type"] == "file":
            fmt = entry.get("format", "unknown")
            formats[fmt] = formats.get(fmt, 0) + 1
    
    if formats:
        console.print(f"\n[blue]Format distribution:")
        for fmt, count in sorted(formats.items()):
            console.print(f"  - {fmt}: {count}")
            
    # Print supported extensions for reference
    console.print(f"\n[blue]Supported extensions: {', '.join(supported_list)}")
    
    # Debug: Print all entries in manifest
    console.print("\n[blue]Manifest entries:")
    for entry in entries:
        console.print(f"  - {entry}")

if __name__ == "__main__":
    typer.run(build_documents_manifest)