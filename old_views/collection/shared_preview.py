"""
Shared Image Preview Utilities

Common image preview functionality shared between mobile and desktop components.
"""

import toga
from toga.style import Pack
import logging
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


class ImagePreviewHelper:
    """Shared utilities for image preview functionality"""
    
    @staticmethod
    def is_image_file(file_path: Path) -> bool:
        """Check if a file is a supported image type"""
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.webp'}
        return file_path.suffix.lower() in image_extensions
    
    @staticmethod
    def get_file_info(file_path: Path) -> Tuple[str, float]:
        """Get file information (name and size in MB)"""
        try:
            file_size = file_path.stat().st_size
            size_mb = file_size / (1024 * 1024)
            return file_path.name, size_mb
        except Exception as e:
            logger.error(f"Failed to get file info for {file_path}: {e}")
            return file_path.name, 0.0
    
    @staticmethod
    def create_image_view(image_path: Path, height=200) -> Optional[toga.ImageView]:
        """Create a toga ImageView from an image file"""
        try:
            if image_path.exists():
                image = toga.Image(image_path)
                style = Pack(height=height, margin=5)
                return toga.ImageView(image=image, style=style)
            else:
                logger.warning(f"Image file not found: {image_path}")
                return None
        except Exception as e:
            logger.error(f"Failed to create image view for {image_path}: {e}")
            return None
    
    @staticmethod
    def create_error_label(message: str, style: Optional[Pack] = None) -> toga.Label:
        """Create an error label with consistent styling"""
        if style is None:
            style = Pack(font_size=10, margin=5)
        return toga.Label(message, style=style)
    
    @staticmethod
    def create_info_label(filename: str, size_mb: float, style: Optional[Pack] = None) -> toga.Label:
        """Create an info label with file details"""
        if style is None:
            style = Pack(font_size=10, margin=5)
        return toga.Label(f"{filename} • {size_mb:.1f} MB", style=style) 