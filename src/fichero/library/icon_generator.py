"""
Icon and Thumbnail Generator for Library Items

Generates Toga-compatible icons and thumbnails for library items including
images, documents, URLs, and other file types.
"""

import logging
from pathlib import Path
from typing import Optional, Tuple
import io

logger = logging.getLogger(__name__)


class IconGenerator:
    """Generates icons and thumbnails for library items"""

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize icon generator

        Args:
            cache_dir: Directory to cache generated thumbnails (optional)
        """
        self.cache_dir = cache_dir
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Standard thumbnail sizes
        self.thumbnail_size = (128, 128)  # For list views
        self.preview_size = (512, 512)    # For preview pane

        # Supported image formats
        self.image_formats = {
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif',
            '.webp', '.ico', '.svg'
        }

        logger.info(f"IconGenerator initialized with cache: {cache_dir}")

    def get_item_icon(self, item_path: Optional[str], item_type: str,
                      size: Tuple[int, int] = None) -> Optional['toga.Image']:
        """
        Get icon/thumbnail for a library item

        Args:
            item_path: Path to the item file (local_path or source_path)
            item_type: Type of item (file, folder, url, etc.)
            size: Desired icon size (default: thumbnail_size)

        Returns:
            toga.Image or None if icon cannot be generated
        """
        try:
            if not item_path:
                return self._get_default_icon(item_type)

            path = Path(item_path)
            size = size or self.thumbnail_size

            # Check cache first
            if self.cache_dir:
                cache_key = f"{path.stem}_{size[0]}x{size[1]}.png"
                cache_path = self.cache_dir / cache_key
                if cache_path.exists():
                    return self._load_toga_image(cache_path)

            # Generate thumbnail based on file type
            if path.suffix.lower() in self.image_formats:
                thumbnail = self._generate_image_thumbnail(path, size)
                if thumbnail and self.cache_dir:
                    cache_path = self.cache_dir / cache_key
                    self._save_thumbnail(thumbnail, cache_path)
                return thumbnail

            # For non-images, return type-based icon
            return self._get_default_icon(item_type, path.suffix)

        except Exception as e:
            logger.error(f"Failed to generate icon for {item_path}: {e}")
            return self._get_default_icon(item_type)

    def _generate_image_thumbnail(self, image_path: Path, size: Tuple[int, int]) -> Optional['toga.Image']:
        """
        Generate thumbnail from image file

        Args:
            image_path: Path to image file
            size: Desired thumbnail size

        Returns:
            toga.Image or None
        """
        try:
            from PIL import Image

            if not image_path.exists():
                logger.warning(f"Image file not found: {image_path}")
                return None

            # Open and resize image
            with Image.open(image_path) as img:
                # Convert to RGB if necessary (for transparency handling)
                if img.mode in ('RGBA', 'LA', 'P'):
                    # Create white background
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')

                # Calculate aspect-preserving size
                img.thumbnail(size, Image.Resampling.LANCZOS)

                # Save to bytes for Toga
                img_bytes = io.BytesIO()
                img.save(img_bytes, format='PNG')
                img_bytes.seek(0)

                # Create Toga image
                return self._create_toga_image_from_bytes(img_bytes.getvalue())

        except Exception as e:
            logger.error(f"Failed to generate thumbnail for {image_path}: {e}")
            return None

    def _create_toga_image_from_bytes(self, image_bytes: bytes) -> Optional['toga.Image']:
        """
        Create Toga Image from bytes

        Args:
            image_bytes: PNG image data as bytes

        Returns:
            toga.Image or None
        """
        try:
            import toga

            # Save to temp file (Toga requires file path)
            if self.cache_dir:
                temp_path = self.cache_dir / f"temp_{id(image_bytes)}.png"
                temp_path.write_bytes(image_bytes)
                image = toga.Image(temp_path)
                temp_path.unlink()  # Clean up temp file
                return image
            else:
                # Without cache dir, save to system temp
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
                    f.write(image_bytes)
                    temp_path = Path(f.name)

                image = toga.Image(temp_path)
                temp_path.unlink()  # Clean up
                return image

        except Exception as e:
            logger.error(f"Failed to create Toga image: {e}")
            return None

    def _load_toga_image(self, path: Path) -> Optional['toga.Image']:
        """Load Toga image from file"""
        try:
            import toga
            return toga.Image(path)
        except Exception as e:
            logger.error(f"Failed to load Toga image from {path}: {e}")
            return None

    def _save_thumbnail(self, toga_image: 'toga.Image', cache_path: Path):
        """Save Toga image to cache (placeholder - Toga doesn't expose raw data)"""
        # Note: This is a limitation - we'd need to save the PIL image before conversion
        # For now, we regenerate thumbnails when needed
        pass

    def _get_default_icon(self, item_type: str, file_ext: str = "") -> Optional['toga.Image']:
        """
        Get default icon based on item type

        Args:
            item_type: Type of item (file, folder, url)
            file_ext: File extension for specific file type icons

        Returns:
            toga.Image or None
        """
        try:
            import toga

            # Map types to icon files
            icon_map = {
                'folder': 'resources/icons/toolbar/folder@10x.png',
                'url': 'resources/icons/toolbar/link.png',
                'file': 'resources/icons/toolbar/document.png',
                'camera': 'resources/icons/toolbar/camera.png',
                'audio': 'resources/icons/toolbar/audio.png',
            }

            # Extension-specific icons
            ext_icon_map = {
                '.pdf': 'resources/icons/toolbar/document.png',
                '.doc': 'resources/icons/toolbar/document.png',
                '.docx': 'resources/icons/toolbar/document.png',
                '.txt': 'resources/icons/toolbar/document.png',
            }

            # Try extension-specific first
            if file_ext and file_ext.lower() in ext_icon_map:
                icon_path = Path(ext_icon_map[file_ext.lower()])
                if icon_path.exists():
                    return toga.Image(icon_path)

            # Fall back to type-based icon
            if item_type in icon_map:
                icon_path = Path(icon_map[item_type])
                if icon_path.exists():
                    return toga.Image(icon_path)

            return None

        except Exception as e:
            logger.error(f"Failed to get default icon: {e}")
            return None

    def generate_preview(self, item_path: str) -> Optional['toga.Image']:
        """
        Generate larger preview image for item

        Args:
            item_path: Path to item file

        Returns:
            toga.Image at preview size or None
        """
        return self.get_item_icon(item_path, 'file', self.preview_size)

    def clear_cache(self):
        """Clear thumbnail cache"""
        try:
            if self.cache_dir and self.cache_dir.exists():
                for cache_file in self.cache_dir.glob('*.png'):
                    cache_file.unlink()
                logger.info("Thumbnail cache cleared")
        except Exception as e:
            logger.error(f"Failed to clear thumbnail cache: {e}")
