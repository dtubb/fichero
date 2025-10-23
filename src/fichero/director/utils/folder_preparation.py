"""
Folder Preparation Utilities

Handles preparing folders for processing by creating output structure and copying files.
"""

import os
import shutil
import logging
import re
import platform
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _try_apfs_clone(src: Path, dst: Path) -> bool:
    """
    Try to use APFS cloning for faster file copying on macOS.
    
    Returns True if cloning succeeded, False if we should fall back to regular copy.
    """
    if platform.system() != "Darwin":  # Only on macOS
        return False
        
    try:
        # Try APFS clone copy - much faster for large files on same volume
        result = subprocess.run(
            ["cp", "-c", str(src), str(dst)],
            capture_output=True,
            text=True,
            timeout=30  # Don't hang on this
        )
        if result.returncode == 0:
            logger.debug(f"APFS cloned: {src.name}")
            return True
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        pass  # Fall back to regular copy
    
        return False


def sanitize_name(name: str, preserve_extension: bool = True) -> str:
    """
    Sanitize a filename or path by replacing problematic characters with hyphens.
    Preserves Unicode characters but replaces filesystem-invalid and problematic characters.
    
    Args:
        name: The filename or path to sanitize
        preserve_extension: If True, preserves file extension separately (for filenames)
    
    Returns:
        Sanitized name
    """
    if preserve_extension:
        # Split into name and extension for files
        base_name, ext = os.path.splitext(name)
    else:
        # For directories/paths, treat as single unit
        base_name, ext = name, ""
    
    # Replace all problematic characters with hyphens
    sanitized = (base_name.replace(',', '-')
                .replace(';', '-')
                .replace('{', '-')
                .replace('}', '-')
                .replace(' ', '-')
                .replace('$', '-')
                .replace('&', '-')
                # Filesystem invalid characters
                .replace('/', '-')
                .replace('\\', '-')
                .replace(':', '-')
                .replace('*', '-')
                .replace('?', '-')
                .replace('"', '-')
                .replace('<', '-')
                .replace('>', '-')
                .replace('|', '-')
                # Other problematic characters
                .replace('#', '-')
                .replace('@', '-')
                .replace('!', '-')
                .replace('~', '-')
                .replace('`', '-')
                .replace('^', '-')
                .replace('+', '-')
                .replace('=', '-')
                .replace('[', '-')
                .replace(']', '-')
                .replace('(', '-')
                          .replace(')', '-')
                          .replace('.', '-'))  # Replace periods with hyphens
    
    # Clean up multiple consecutive hyphens
    sanitized = re.sub(r'-+', '-', sanitized)
    
    # Remove leading/trailing hyphens
    sanitized = sanitized.strip('-')
    
    # Recombine with extension
    final_name = sanitized + ext
    if final_name != name:
        logger.debug(f"Sanitized name: '{name}' -> '{final_name}'")
    
    return final_name


def prepare_folder(input_folder: Path, output_folder: Path, processing_mode: str = "in_place") -> tuple[Path, Path]:
    """
    Prepare a folder for processing by creating the required structure.

    Supports two modes:
    - "in_place": Process files from source location (no copying)
    - "copy": Copy files to output before processing

    Args:
        input_folder: Source folder containing files to process
        output_folder: Base output directory
        processing_mode: "in_place" or "copy" (default: "in_place")

    Returns:
        Tuple of (output_subfolder, documents_folder)
        - output_subfolder: Base folder for outputs (assets, logs)
        - documents_folder: Folder containing source files (either input_folder or copied location)
    """
    logger.info(f"Preparing folder: {input_folder} -> {output_folder} (mode: {processing_mode})")

    # Create output folder with sanitized name
    sanitized_folder_name = sanitize_name(input_folder.name, preserve_extension=False)
    output_subfolder = output_folder / sanitized_folder_name
    output_subfolder.mkdir(parents=True, exist_ok=True)

    # Create required subfolders for outputs
    (output_subfolder / "assets").mkdir(parents=True, exist_ok=True)
    (output_subfolder / "logs").mkdir(parents=True, exist_ok=True)

    if processing_mode == "in_place":
        # In-place mode: No file copying, process from source location
        # Set documents_folder to the actual input folder being processed
        # The workflow executor will pass add_documents_prefix=False to prevent
        # BatchProcessor from adding /documents/ to file paths
        documents_folder = input_folder

        logger.info(f"✓ In-place mode: documents_folder = {documents_folder}")
    else:
        # Copy mode: Copy files to output/documents before processing
        (output_subfolder / "documents").mkdir(parents=True, exist_ok=True)

        # Create the parent folder within documents to preserve original structure
        # Scripts expect documents/OriginalFolderName/... structure
        sanitized_input_name = sanitize_name(input_folder.name, preserve_extension=False)
        parent_folder_in_docs = output_subfolder / "documents" / sanitized_input_name
        parent_folder_in_docs.mkdir(parents=True, exist_ok=True)

        # Copy the entire folder structure to documents/OriginalFolderName/
        def _copy_folder_structure(src_folder: Path, dst_folder: Path):
            """Recursively copy folder structure with sanitized names"""
            for item in src_folder.iterdir():
                # Skip .DS_Store files
                if item.name == '.DS_Store':
                    continue

                if item.is_file():
                    # Copy files with sanitized names
                    sanitized_name = sanitize_name(item.name, preserve_extension=True)
                    dst_path = dst_folder / sanitized_name
                    dst_path.parent.mkdir(parents=True, exist_ok=True)

                    # Skip if file already exists (avoid unnecessary copying)
                    if dst_path.exists():
                        logger.debug(f"Skipped existing file: {item.name} -> {sanitized_name}")
                        continue

                    # Try APFS clone first (fast), fall back to regular copy
                    if not _try_apfs_clone(item, dst_path):
                        shutil.copy2(str(item), str(dst_path))
                        logger.debug(f"Copied file: {item.name} -> {sanitized_name}")
                elif item.is_dir():
                    # Create subdirectory with sanitized name and recurse
                    sanitized_dir_name = sanitize_name(item.name, preserve_extension=False)
                    target_subdir = dst_folder / sanitized_dir_name
                    target_subdir.mkdir(parents=True, exist_ok=True)
                    # Recursively copy contents
                    _copy_folder_structure(item, target_subdir)

        _copy_folder_structure(input_folder, parent_folder_in_docs)
        logger.info(f"✓ Copy mode: Files copied to {parent_folder_in_docs}")
        documents_folder = parent_folder_in_docs

    logger.info(f"Folder preparation completed. Output: {output_subfolder}, Documents: {documents_folder}")
    return output_subfolder, documents_folder 