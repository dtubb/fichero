#!/usr/bin/env python3
import asyncio
from pathlib import Path
import typer
from PIL import Image
import io
from pdf2image import convert_from_path
import aiofiles
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from functools import partial
import tempfile
import os
import psutil
import time
import re
import json
from contextlib import nullcontext
from scripts.utils.jsonl_manager import JSONLManager
from scripts.utils.file_manager import FileManager
from scripts.utils.workflow_progress import create_progress_tracker
from scripts.utils.logging_utils import rich_log, setup_logging
import logging

# Global process pool for CPU-intensive tasks
process_pool = ProcessPoolExecutor(max_workers=os.cpu_count() or 1)

def natural_sort_key(s: str):
    """Sort strings alphanumerically like Finder."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def convert_pdf_to_images(pdf_path: Path, dpi: int = 300) -> list[Image.Image]:
    """Convert PDF to images using pdf2image."""
    try:
        # Create a temporary directory for pdf2image
        with tempfile.TemporaryDirectory() as temp_dir:
            # Convert PDF to images
            images = convert_from_path(
                pdf_path,
                dpi=dpi,
                output_folder=temp_dir,
                fmt='jpeg',
                thread_count=os.cpu_count() or 1,
                use_pdftocairo=True,
                grayscale=False
            )
            return images
    except Exception as e:
        rich_log("error", f"Error converting PDF {pdf_path}: {str(e)}")
        return []

def convert_image_to_jpg(input_path: Path, output_path: Path) -> bool:
    """Convert a single image to JPG format."""
    try:
        with Image.open(input_path) as img:
            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Save as JPG with maximum quality
            img.save(output_path, 'JPEG', quality=100)
            return True
    except Exception as e:
        rich_log("error", f"Error converting image {input_path}: {str(e)}")
        return False

async def convert_to_jpg(
    input_dir: Path = typer.Argument(..., help="Directory to scan for files and folders"),
    output_dir: Path = typer.Argument(..., help="Directory to write converted JPG files to"),
    dpi: int = typer.Option(300, help="DPI for PDF conversion")
):
    """
    Recursively scan the given input directory and convert all supported image files to JPG format.
    Uses FileManager for file operations.
    """
    
    # Initialize managers
    file_manager = FileManager(input_dir.parent)
    input_dir = Path(os.path.expanduser(str(input_dir))).resolve()
    output_dir = Path(os.path.expanduser(str(output_dir))).resolve()
    
    # First, count total files for progress bar
    total = 0
    for root, dirs, files in os.walk(input_dir):
        total += len([f for f in files if file_manager.is_supported_file(Path(f))])

    stats = {"processed": 0, "total": total}

    # Create progress tracker
    workflow_progress, step_progress = create_progress_tracker(
        total_files=total,
        step_name="Converting to JPG",
        show_workflow=False
    )

    with step_progress if step_progress else nullcontext():
        for root, dirs, files in os.walk(input_dir):
            root_path = Path(root)
            for f in files:
                if f.startswith('.'):
                    continue  # Skip hidden/system files
                
                file_path = root_path.joinpath(f)
                if file_manager.is_supported_file(file_path):
                    rel_path = file_path.relative_to(input_dir)
                    
                    # Create output path
                    output_path = output_dir / rel_path.with_suffix('.jpg')
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    try:
                        # Convert to JPG
                        with Image.open(file_path) as img:
                            # Convert to RGB if needed
                            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                                background = Image.new('RGB', img.size, (255, 255, 255))
                                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                                img = background
                            elif img.mode != 'RGB':
                                img = img.convert('RGB')
                            
                            # Save as JPG
                            img.save(output_path, 'JPEG', quality=95)
                        
                        # Delete original file after successful conversion
                        try:
                            os.remove(file_path)
                            rich_log("debug", f"Deleted original file: {file_path}")
                        except Exception as e:
                            rich_log("warning", f"Failed to delete original file {file_path}: {e}")
                            
                    except Exception as e:
                        rich_log("error", f"Error converting {file_path}: {e}")
                        continue
                    
                    stats["processed"] += 1
                    if step_progress:
                        step_progress.update(processed=stats["processed"], **stats)

    rich_log("info", "Conversion complete.")

def main(
    input_folder: str = typer.Argument(..., help="Input folder containing files to convert"),
    output_folder: str = typer.Argument(..., help="Output folder for converted JPG files"),
    dpi: int = typer.Option(300, help="DPI for PDF conversion"),
    debug: bool = typer.Option(False, help="Enable debug logging")
):
    """Convert various file formats to JPG format."""
    # Set up logging
    setup_logging(level="DEBUG" if debug or os.environ.get('FICHERO_DEBUG') == '1' else "INFO")
    
    try:
        asyncio.run(convert_to_jpg(Path(input_folder), Path(output_folder), dpi))
    finally:
        process_pool.shutdown()

if __name__ == "__main__":
    typer.run(main) 