"""
Image Editor

Editor for image outputs (prepared images, etc.)
"""

from pathlib import Path
from typing import Any, Dict

from .base_editor import BaseToolEditor


class ImageEditor(BaseToolEditor):
    """
    Editor for image output files.

    Currently provides:
    - Metadata viewing
    - Basic image info

    Future:
    - Rotation adjustment
    - Crop parameter editing
    - EXIF data editing
    """

    tool_name = "image"
    supported_extensions = ['.jpg', '.jpeg', '.png', '.tiff', '.tif', '.webp']
    can_edit_files = False  # Not directly editable yet

    def can_edit(self, file_path: Path) -> bool:
        """Check if file is an image"""
        return file_path.suffix.lower() in self.supported_extensions

    def load_content(self, file_path: Path) -> Dict[str, Any]:
        """
        Load image metadata.

        Args:
            file_path: Path to image file

        Returns:
            Dictionary with image metadata
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        metadata = self.get_metadata(file_path)

        # Try to get image dimensions if PIL is available
        try:
            from PIL import Image
            with Image.open(file_path) as img:
                metadata['width'] = img.width
                metadata['height'] = img.height
                metadata['format'] = img.format
                metadata['mode'] = img.mode

                # Try to get EXIF data
                if hasattr(img, '_getexif') and img._getexif():
                    metadata['exif'] = img._getexif()

        except ImportError:
            self.logger.debug("PIL not available, skipping image dimensions")
        except Exception as e:
            self.logger.debug(f"Could not read image data: {e}")

        return metadata

    def save_content(self, file_path: Path, content: Any) -> bool:
        """
        Save image content.

        Currently not implemented - images are not directly editable.
        Future: Could save adjusted EXIF, rotation, crop parameters.

        Args:
            file_path: Path to image file
            content: Content to save

        Returns:
            False (not implemented)
        """
        self.logger.warning("Direct image editing not yet implemented")
        return False

    def get_dimensions(self, file_path: Path) -> tuple[int, int]:
        """
        Get image dimensions.

        Args:
            file_path: Path to image

        Returns:
            Tuple of (width, height) or (0, 0) if cannot determine
        """
        try:
            from PIL import Image
            with Image.open(file_path) as img:
                return img.width, img.height
        except:
            return 0, 0

    def get_format_info(self, file_path: Path) -> str:
        """
        Get image format information.

        Args:
            file_path: Path to image

        Returns:
            Format string (e.g., "JPEG", "PNG")
        """
        try:
            from PIL import Image
            with Image.open(file_path) as img:
                return img.format
        except:
            return file_path.suffix.upper().lstrip('.')
