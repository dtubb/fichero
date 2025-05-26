from pathlib import Path
from PIL import Image
from typing import Dict, Union
import shutil
import os
import json
import tempfile
from rich.console import Console
from .image_format import check_cjxl_installed, save_as_jxl, load_image
from .files import get_relative_path, ensure_dirs
import subprocess

console = Console()

class SegmentHandler:
    """Handles loading, saving, and path management for image segments"""
    
    @staticmethod
    def exists(path: Union[str, Path], base_folder: Path = None) -> bool:
        """Check if segment exists"""
        if base_folder:
            full_path = base_folder / Path(path)
        else:
            full_path = Path(path)
        return full_path.exists()

    @staticmethod
    def check_segment_exists(source_path: Path, segment_index: int) -> bool:
        """Check if a specific segment exists"""
        paths = SegmentHandler.get_segment_paths(source_path)
        segment_name = SegmentHandler.make_segment_name(source_path.stem, segment_index)
        segment_path = paths["segments_folder"] / segment_name
        return segment_path.exists()

    @staticmethod
    def load_segment(segment_path: Union[str, Path], base_folder: Path = None) -> Image.Image:
        """Load a segment image with proper path resolution, including JXL support"""
        try:
            if base_folder:
                full_path = base_folder / Path(segment_path)
            else:
                full_path = Path(segment_path)
                
            if not full_path.exists():
                raise FileNotFoundError(f"Segment not found: {full_path}")
            
            # Use load_image to handle various formats
            image, metadata = load_image(full_path)
            return image
            
        except Exception as e:
            raise Exception(f"Error loading segment {segment_path}: {str(e)}")

    @staticmethod
    def save_segment_output(
        output: str,
        out_path: Path,
        extension: str = '.md'
    ) -> Dict:
        """Save segment output and return manifest entry"""
        out_path = out_path.with_suffix(extension)
        
        # Ensure parent directory exists
        ensure_dirs(out_path)
        
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(output)
            
        # Get relative path
        rel_path = get_relative_path(out_path)
            
        return {
            "outputs": [str(rel_path)],
            "source": str(rel_path)
        }

    @staticmethod
    def get_relative_path(file_path: Path) -> Path:
        """
        Get relative path from documents/ onwards.
        Always returns a relative path, removing any absolute path components.
        """
        return get_relative_path(file_path)

    @staticmethod
    def get_segment_paths(source_path: Path) -> Dict:
        """
        Get segment folder and file paths.
        Returns paths relative to the documents folder.
        """
        # Get relative path first
        rel_path = get_relative_path(source_path)
        
        if source_path.suffix:  # If it's a file
            segments_folder = source_path.parent / f"{source_path.stem}_segments"
        else:  # If it's a directory
            segments_folder = source_path / f"{source_path.name}_segments"
            
        return {
            "segments_folder": segments_folder,
            "parent_path": rel_path
        }

    @staticmethod 
    def make_segment_name(base_name: str, segment_index: int) -> str:
        """
        Create standardized segment filename.
        Uses shorter format: segment_XXX.jpg where XXX is the zero-padded index.
        """
        return f"segment_{segment_index:03d}.jpg"

    @staticmethod
    def is_processing(folder: Path) -> bool:
        """Check if a folder is currently being processed"""
        lock_file = folder / ".processing"
        return lock_file.exists()

    @staticmethod
    def start_processing(folder: Path) -> None:
        """Mark folder as being processed"""
        # Ensure folder exists before creating lock file
        ensure_dirs(folder)
        lock_file = folder / ".processing"
        lock_file.touch()

    @staticmethod
    def finish_processing(folder: Path) -> None:
        """Mark folder as finished processing"""
        lock_file = folder / ".processing"
        if lock_file.exists():
            lock_file.unlink()

    @staticmethod
    def is_complete(folder: Path) -> bool:
        """Check if a folder was completely processed"""
        done_file = folder / ".done"
        return done_file.exists() and not SegmentHandler.is_processing(folder)

    @staticmethod
    def mark_complete(folder: Path, metadata: dict = None) -> None:
        """Mark folder as completely processed"""
        done_file = folder / ".done"
        if metadata:
            with open(done_file, 'w') as f:
                json.dump(metadata, f)
        else:
            done_file.touch()

    @staticmethod
    def process_safely(folder: Path, process_fn, metadata: dict = None):
        """Process a folder with safety checks"""
        try:
            # Create folder first
            ensure_dirs(folder)

            # If already complete and not processing, skip
            if SegmentHandler.is_complete(folder):
                console.print(f"[yellow]Skipping completed folder: {folder}")
                return True

            # If interrupted mid-processing, clean up folder contents but keep folder
            if SegmentHandler.is_processing(folder):
                console.print(f"[yellow]Cleaning up interrupted processing: {folder}")
                for item in folder.glob("*"):
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)

            # Start processing
            SegmentHandler.start_processing(folder)
            try:
                result = process_fn()
                SegmentHandler.mark_complete(folder, metadata)
                return result
            finally:
                SegmentHandler.finish_processing(folder)
        except Exception as e:
            console.print(f"[red]Error in process_safely: {e}")
            # Don't delete folder on error, but remove processing flag
            if folder.exists() and SegmentHandler.is_processing(folder):
                SegmentHandler.finish_processing(folder)
            raise
