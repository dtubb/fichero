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
    def prepare_folder(input_folder: Path, output_folder: Path, processing_mode: str = "in_place") -> tuple[Path, Path]:
        """
        Prepare a folder for processing by creating the output structure.

        Args:
            input_folder: Input folder path
            output_folder: Base output folder path
            processing_mode: "in_place" or "copy" (default: "in_place")

        Returns:
            Tuple of (prepared_folder, documents_folder)
        """
        # Create a simple output structure
        folder_name = input_folder.name
        prepared_folder = output_folder / folder_name
        prepared_folder.mkdir(parents=True, exist_ok=True)

        # For in-place mode, use parent; for copy mode, create documents folder
        if processing_mode == "in_place":
            documents_folder = input_folder.parent
        else:
            (prepared_folder / "documents").mkdir(parents=True, exist_ok=True)
            documents_folder = prepared_folder / "documents"

        return prepared_folder, documents_folder 