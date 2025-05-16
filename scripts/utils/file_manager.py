"""
File Management Utilities for Fichero Processing Scripts

This module provides common utilities for file and path management across different processing scripts.
Key features:
- Path normalization and validation
- Directory structure management
- File type validation
- Consistent path handling for project assets
"""

import os
import sys
from pathlib import Path
import shutil
import platform
import subprocess
from PIL import Image
from typing import Optional, List, Dict, Union, Tuple
from rich.console import Console
from scripts.utils.logging_utils import rich_log, should_show_progress

console = Console()

class FileManager:
    """Centralized file management for Fichero processing scripts."""
    
    # Supported file types
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.jxl'}
    DOCUMENT_EXTENSIONS = {'.pdf'}
    ALL_SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS
    
    def __init__(self, project_root: Optional[Path] = None):
        """Initialize FileManager with project root directory."""
        self.project_root = self._find_project_root(project_root)
        rich_log("debug", f"Initialized FileManager with project root: {self.project_root}")
    
    def _find_project_root(self, project_root: Optional[Path] = None) -> Path:
        """Find the project root directory."""
        if project_root:
            return Path(project_root).resolve()
        
        # Try to find project root by looking for key directories
        current_dir = Path.cwd()
        while current_dir != current_dir.parent:
            if (current_dir / 'documents').exists() or (current_dir / 'assets').exists():
                return current_dir
            current_dir = current_dir.parent
        
        # If no project root found, use current directory
        return Path.cwd()
    
    def get_asset_path(self, asset_type: str) -> Path:
        """Get the path for a specific asset type (e.g., 'crops', 'splits')."""
        asset_path = self.project_root / 'assets' / asset_type
        asset_path.mkdir(parents=True, exist_ok=True)
        return asset_path
    
    def get_documents_path(self) -> Path:
        """Get the documents directory path."""
        docs_path = self.project_root / 'documents'
        docs_path.mkdir(parents=True, exist_ok=True)
        return docs_path
    
    def get_relative_path(self, file_path: Union[str, Path], base_prefix: str = "") -> Path:
        """Get relative path from a base prefix (e.g., 'documents/', 'crops/')."""
        # Convert to Path if string
        if isinstance(file_path, str):
            file_path = Path(file_path)
        elif isinstance(file_path, list):
            # Handle case where a list is passed
            file_path = Path(str(file_path[0])) if file_path else Path()
        
        # If path contains the prefix, get everything after it
        if base_prefix and base_prefix in str(file_path):
            parts = file_path.parts
            idx = parts.index(base_prefix.rstrip('/'))
            return Path(*parts[idx+1:])
        
        # Otherwise, return the name or relative path
        try:
            return file_path.relative_to(self.project_root)
        except ValueError:
            return Path(file_path.name)
    
    def get_output_path(self, input_path: str, output_folder: str, suffix: str = None) -> Path:
        """
        Get output path maintaining folder hierarchy.
        
        Args:
            input_path: Relative input path from project root
            output_folder: Output folder name (e.g. 'crops', 'ocr')
            suffix: Optional suffix to replace original extension
            
        Returns:
            Path: Output path with maintained hierarchy
        """
        # Convert input_path to Path if it's a string
        input_path = Path(input_path)
        
        # Get the full path structure after 'documents/'
        if 'documents' in input_path.parts:
            doc_idx = input_path.parts.index('documents')
            rel_path = Path(*input_path.parts[doc_idx+1:])
        else:
            rel_path = input_path
            
        # Create the output path in the specified folder with the same structure
        output_path = self.get_asset_path(output_folder) / rel_path
        
        # Apply suffix if provided
        if suffix:
            output_path = output_path.with_suffix(suffix)
            
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        return output_path
    
    def validate_image(self, file_path: Path) -> bool:
        """Validate that a file is a valid image."""
        try:
            with Image.open(file_path) as img:
                img.verify()
            return True
        except Exception as e:
            rich_log("error", f"Invalid image file {file_path}: {str(e)}")
            return False
    
    def copy_file(self, source: Path, dest: Path) -> bool:
        """Copy a file with platform-specific optimizations."""
        try:
            # Create parent directories
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            # Use platform-specific copy method
            if platform.system() == 'Darwin':
                # Use cp -c for instant copy on Mac
                result = subprocess.run(['cp', '-c', str(source), str(dest)], 
                                     capture_output=True, text=True)
                success = result.returncode == 0
            else:
                # Use shutil.copy2 to preserve metadata
                shutil.copy2(source, dest)
                success = True
            
            if success:
                rich_log("debug", f"Copied {source} to {dest}")
            else:
                rich_log("error", f"Failed to copy {source} to {dest}")
            return success
            
        except Exception as e:
            rich_log("error", f"Error copying {source} to {dest}: {str(e)}")
            return False
    
    def move_file(self, source: Path, dest: Path) -> bool:
        """Move a file with platform-specific optimizations."""
        try:
            # Create parent directories
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            # Move the file
            shutil.move(str(source), str(dest))
            rich_log("debug", f"Moved {source} to {dest}")
            return True
            
        except Exception as e:
            rich_log("error", f"Error moving {source} to {dest}: {str(e)}")
            return False
    
    def is_supported_file(self, file_path: Path) -> bool:
        """Check if a file has a supported extension."""
        return file_path.suffix.lower() in self.ALL_SUPPORTED_EXTENSIONS
    
    def scan_directory(self, directory: Path, recursive: bool = True) -> List[Path]:
        """Scan a directory for supported files."""
        directory = Path(directory)
        files = []
        
        if recursive:
            for root, _, filenames in os.walk(directory):
                for filename in filenames:
                    file_path = Path(root) / filename
                    if self.is_supported_file(file_path):
                        files.append(file_path)
        else:
            files = [f for f in directory.iterdir() 
                    if f.is_file() and self.is_supported_file(f)]
        
        return files
    
    def ensure_output_path(self, output_path: Path) -> None:
        """Ensure output path exists and is writable."""
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            # Test write access
            test_file = output_path.parent / '.write_test'
            test_file.touch()
            test_file.unlink()
        except Exception as e:
            rich_log("error", f"Cannot write to output path {output_path}: {str(e)}")
            raise
    
    def clean_filename(self, filename: str) -> str:
        """Clean a filename to ensure it's valid across platforms."""
        # Replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # Remove leading/trailing spaces and dots
        filename = filename.strip('. ')
        
        return filename if filename else 'unnamed' 