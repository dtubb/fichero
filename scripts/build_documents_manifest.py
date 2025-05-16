#!/usr/bin/env python3
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

import typer
import re
import urllib.parse
from contextlib import nullcontext
from scripts.utils.jsonl_manager import JSONLManager
from scripts.utils.file_manager import FileManager
from scripts.utils.workflow_progress import create_progress_tracker
from scripts.utils.logging_utils import rich_log, setup_logging
from scripts.utils.step_manifest import StepManifestManager

def natural_sort_key(s: str):
    """Sort strings alphanumerically like Finder."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def build_documents_manifest(
    documents_dir: Path = typer.Argument(..., help="Directory to scan for files and folders"),
    manifest_filename: str = typer.Argument("manifest.jsonl", help="Manifest output filename (relative to project root or absolute)"),
    debug: bool = typer.Option(False, help="Enable debug logging")
):
    """
    Recursively scan the given documents directory and create a JSONL file listing
    all files and subfolders (relative paths only), sorted alphanumerically.
    """
    # Set up logging
    setup_logging(level="DEBUG" if debug or os.environ.get('FICHERO_DEBUG') == '1' else "INFO")
    
    # Initialize file manager with project root
    file_manager = FileManager(project_root)
    documents_dir = Path(os.path.expanduser(str(documents_dir))).resolve()
    
    # If manifest_filename is absolute, use as is; else, make relative to project root
    manifest_path = Path(manifest_filename)
    if not manifest_path.is_absolute():
        manifest_path = project_root / manifest_path
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize StepManifestManager for the build step
    manifest_manager = StepManifestManager(str(manifest_path), "build")
    rich_log("debug", f"Initialized manifest manager with file: {manifest_path}")

    # First, count total files and dirs for progress bar
    total = 0
    for root, dirs, files in os.walk(documents_dir):
        total += len(dirs) + len([f for f in files if file_manager.is_supported_file(Path(f))])

    entries = []
    stats = {"processed": 0, "total": total}

    # Create progress tracker
    workflow_progress, step_progress = create_progress_tracker(
        total_files=total,
        step_name="Building Documents Manifest",
        show_workflow=False
    )

    with step_progress if step_progress else nullcontext():
        for root, dirs, files in os.walk(documents_dir):
            root_path = Path(root)
            for d in dirs:
                rel_path = root_path.joinpath(d).relative_to(documents_dir)
                # Add documents/ prefix to path
                input_path = f"documents/{rel_path}"
                entries.append({"input_path": input_path, "type": "directory"})
                stats["processed"] += 1
                if step_progress:
                    step_progress.update(processed=stats["processed"], **stats)

            for f in files:
                if f.startswith('.'):
                    continue  # Skip hidden/system files
                
                file_path = root_path.joinpath(f)
                if file_manager.is_supported_file(file_path):
                    rel_path = file_path.relative_to(documents_dir)
                    # Add documents/ prefix to path
                    input_path = f"documents/{rel_path}"
                    folder = rel_path.parts[0] if len(rel_path.parts) > 1 else ""
                    try:
                        mtime = os.path.getmtime(file_path)
                        size = os.path.getsize(file_path)
                    except Exception as e:
                        rich_log("error", f"Could not stat {file_path}: {e}")
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
                    if step_progress:
                        step_progress.update(processed=stats["processed"], **stats)

    # Sort all entries by alphanumeric order of their 'input_path'
    entries.sort(key=lambda e: natural_sort_key(e["input_path"]))

    try:
        # Use manifest manager's batch update
        manifest_manager.manifest.batch_update(entries)
        rich_log("info", "Manifest write complete.")
        # Verify the write
        if manifest_path.exists():
            rich_log("info", f"Manifest file size: {manifest_path.stat().st_size} bytes")
            # Verify entries were written
            written_entries = manifest_manager.manifest.all_entries()
            rich_log("info", f"Wrote {len(written_entries)} entries to manifest")
    except Exception as e:
        rich_log("error", f"Exception during manifest write: {e}")
        import traceback
        traceback.print_exc()
    rich_log("info", "Script completed.")

if __name__ == "__main__":
    typer.run(build_documents_manifest)