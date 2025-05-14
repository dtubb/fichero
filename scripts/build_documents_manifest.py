import typer
from pathlib import Path
import os
import re
import urllib.parse  # Add this for URL encoding/decoding
from utils.jsonl_manager import JSONLManager
from utils.progress import ProgressTracker

def natural_sort_key(s: str):
    """Sort strings alphanumerically like Finder."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def build_documents_manifest(
    documents_dir: Path = typer.Argument(..., help="Directory to scan for files and folders"),
    manifest_filename: str = typer.Argument("manifest.jsonl", help="Manifest output filename (relative to project root or absolute)")
):
    """
    Recursively scan the given documents directory and create a JSONL file listing
    all files and subfolders (relative paths only), sorted alphanumerically.
    Now uses JSONLManager for safe, central manifest creation.
    Manifest is written to the given output path (default: manifest.jsonl).
    Shows a progress bar while scanning files.
    """
    
    documents_dir = Path(os.path.expanduser(str(documents_dir))).resolve()
    # If manifest_filename is absolute, use as is; else, make relative to project root
    manifest_path = Path(manifest_filename)
    if not manifest_path.is_absolute():
        # Get the project root (parent of documents_dir)
        project_root = documents_dir.parent
        manifest_path = project_root / manifest_path
    # print(f"[DEBUG] Using manifest path: {manifest_path}")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    # First, count total files and dirs for progress bar
    total = 0
    # print(f"[DEBUG] Scanning directory: {documents_dir}")
    for root, dirs, files in os.walk(documents_dir):
        # print(f"[DEBUG] Scanning: {root}")
        # print(f"[DEBUG] Found directories: {dirs}")
        # print(f"[DEBUG] Found files: {files}")
        total += len(dirs) + len([f for f in files if f.lower().endswith((
            '.pdf', '.jpg', '.jpeg', '.tif', '.tiff', '.png', '.jxl'))])
    # print(f"[DEBUG] Total files and dirs to process: {total}")

    manager = JSONLManager(str(manifest_path))
    entries = []
    stats = {"processed": 0, "total": total}

    tracker = ProgressTracker(total=total, task_name="Scanning files", progress_fields=stats)
    with tracker.progress:
        for root, dirs, files in os.walk(documents_dir):
            root_path = Path(root)
            # print(f"[DEBUG] Processing directory: {root_path}")
            for d in dirs:
                rel_path = root_path.joinpath(d).relative_to(documents_dir)
                # Add documents/ prefix to path
                input_path = f"documents/{rel_path}"
                entries.append({"input_path": input_path, "type": "directory"})
                stats["processed"] += 1
                tracker.progress.update(tracker.task, advance=1, **stats)
            for f in files:
                if f.startswith('.'):
                    # print(f"[DEBUG] Skipping hidden file: {f}")
                    continue  # Skip hidden/system files
                if f.lower().endswith((
                    '.pdf', '.jpg', '.jpeg', '.tif', '.tiff', '.png', '.jxl')):
                    file_path = root_path.joinpath(f)
                    rel_path = file_path.relative_to(documents_dir)
                    # Add documents/ prefix to path
                    input_path = f"documents/{rel_path}"
                    folder = rel_path.parts[0] if len(rel_path.parts) > 1 else ""
                    try:
                        mtime = os.path.getmtime(file_path)
                        size = os.path.getsize(file_path)
                    except Exception as e:
                        print(f"[ERROR] Could not stat {file_path}: {e}")
                        continue
                    entries.append({
                        "input_path": input_path,
                        "folder": folder,
                        "type": "file",
                        "mtime": mtime,
                        "size": size,
                        "status": "pending",
                        "crop_status": "pending",
                        "crop_outputs": [],
                        "crop_details": {}
                    })
                    stats["processed"] += 1
                    tracker.progress.update(tracker.task, advance=1, **stats)

    # Sort all entries by alphanumeric order of their 'input_path'
    entries.sort(key=lambda e: natural_sort_key(e["input_path"]))

    # print(f"About to write manifest to {manifest_path} ...")
    # print(f"Number of entries collected: {len(entries)}")
    # if entries:
    #     print(f"First entry example: {entries[0]}")
    try:
        manager.batch_update(entries)
        print("Manifest write complete.")
        # Verify the write
        if manifest_path.exists():
            print(f"Manifest file size: {manifest_path.stat().st_size} bytes")
    except Exception as e:
        print(f"Exception during manifest write: {e}")
        import traceback
        traceback.print_exc()
    print("Script completed.")

if __name__ == "__main__":
    typer.run(build_documents_manifest)