"""
Folder Preparation Utilities

Utilities for preparing folders for document processing.
"""

from pathlib import Path
from typing import Dict, Any

# Import the actual implementation from the director utils
try:
    from fichero.director.utils.folder_preparation import prepare_folder
except ImportError:
    # Fallback implementation if the director utils are not available
    def prepare_folder(input_folder: Path, output_folder: Path) -> Path:
        """
        Prepare a folder for processing by creating the output structure.
        
        Args:
            input_folder: Input folder path
            output_folder: Base output folder path
            
        Returns:
            Prepared folder path
        """
        # Create a simple output structure
        folder_name = input_folder.name
        prepared_folder = output_folder / folder_name
        prepared_folder.mkdir(parents=True, exist_ok=True)
        
        return prepared_folder 