"""
Icon and Thumbnail Generator for Library Items

Generates Toga-compatible icons and thumbnails for library items including
images, documents, URLs, and other file types.
"""

import logging
from pathlib import Path
from typing import Optional, Tuple
import io
import hashlib

logger = logging.getLogger(__name__)


class IconGenerator:
    """Generates icons and thumbnails for library items"""

    def __init__(self, cache_dir: Optional[Path] = None, storage: Optional['LibraryStorage'] = None):
        """
        Initialize icon generator

        Args:
            cache_dir: Directory to cache generated thumbnails (optional)
            storage: LibraryStorage instance for thumbnail tracking (optional)
        """
        self.cache_dir = cache_dir
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.storage = storage

        # Standard thumbnail sizes
        self.thumbnail_size = (128, 128)  # For list views
        self.preview_size = (512, 512)    # For preview pane

        # Supported image formats
        self.image_formats = {
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif',
            '.webp', '.ico', '.svg'
        }

        logger.info(f"IconGenerator initialized with cache: {cache_dir}, storage: {storage is not None}")

    @staticmethod
    def calculate_file_hash(file_path: Path) -> str:
        """
        Calculate SHA256 hash of a file's content

        Args:
            file_path: Path to the file

        Returns:
            Hex string of SHA256 hash
        """
        try:
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                # Read in chunks to handle large files
                for byte_block in iter(lambda: f.read(65536), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            logger.error(f"Failed to calculate file hash for {file_path}: {e}")
            # Fallback to path-based hash if file can't be read
            return hashlib.sha256(str(file_path).encode()).hexdigest()

    @staticmethod
    def calculate_image_hash(image_bytes: bytes) -> str:
        """
        Calculate SHA256 hash of image bytes

        Args:
            image_bytes: Image data as bytes

        Returns:
            Hex string of SHA256 hash
        """
        return hashlib.sha256(image_bytes).hexdigest()

    def get_organized_thumbnail_path(self, file_hash: str, size: Tuple[int, int]) -> Path:
        """
        Get organized path for thumbnail using hash-based subdirectories

        Args:
            file_hash: SHA256 hash of source file
            size: Thumbnail size tuple (width, height)

        Returns:
            Path relative to cache_dir: aa/bb/aabbcc..._{width}x{height}.png
        """
        if not self.cache_dir:
            raise ValueError("Cache directory not configured")

        # Use first 2 chars for first level, next 2 for second level
        # This creates 256 * 256 = 65,536 possible subdirectories
        level1 = file_hash[:2]
        level2 = file_hash[2:4]

        # Filename: full_hash_widthxheight.png
        filename = f"{file_hash}_{size[0]}x{size[1]}.png"

        # Full path with subdirectories
        organized_path = self.cache_dir / level1 / level2 / filename

        return organized_path

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
                # _generate_image_thumbnail now handles caching internally
                return self._generate_image_thumbnail(path, size)

            # For non-images, return type-based icon
            return self._get_default_icon(item_type, path.suffix)

        except Exception as e:
            logger.error(f"Failed to generate icon for {item_path}: {e}")
            return self._get_default_icon(item_type)

    def _generate_image_thumbnail(self, image_path: Path, size: Tuple[int, int]) -> Optional['toga.Image']:
        """
        Generate thumbnail from image file with database-tracked deduplication

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

            # Calculate file hash for deduplication
            file_hash = self.calculate_file_hash(image_path)
            size_str = f"{size[0]}x{size[1]}"

            # Check database for existing thumbnail (if storage available)
            if self.storage:
                existing_thumbnail = self.storage.get_thumbnail(file_hash, size_str)
                if existing_thumbnail:
                    # Check if thumbnail file still exists
                    thumbnail_path = self.cache_dir / existing_thumbnail.thumbnail_path
                    if thumbnail_path.exists():
                        logger.debug(f"♻️ Reusing existing thumbnail: {existing_thumbnail.thumbnail_path}")
                        # Update last accessed timestamp
                        self.storage.update_thumbnail_access(existing_thumbnail.id)
                        return self._load_toga_image(thumbnail_path)
                    else:
                        # Thumbnail record exists but file is missing - delete record
                        logger.warning(f"Thumbnail file missing, removing record: {existing_thumbnail.thumbnail_path}")
                        self.storage.delete_thumbnail(existing_thumbnail.id)

            # Generate new thumbnail
            # Determine cache path
            if self.cache_dir and self.storage:
                # Use organized path for database-tracked thumbnails
                cache_path = self.get_organized_thumbnail_path(file_hash, size)
                # Store relative path for database
                relative_path = cache_path.relative_to(self.cache_dir)
            elif self.cache_dir:
                # Fallback to old naming scheme if no storage
                cache_key = f"{image_path.stem}_{size[0]}x{size[1]}.png"
                cache_path = self.cache_dir / cache_key
                relative_path = cache_key
            else:
                cache_path = None
                relative_path = None

            # Open and resize image
            with Image.open(image_path) as img:
                # Convert to RGBA to support transparency
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')

                # Calculate aspect-preserving thumbnail size
                img.thumbnail(size, Image.Resampling.LANCZOS)

                # Create square canvas with transparent background
                square_size = max(size)  # Use the larger dimension
                square_canvas = Image.new('RGBA', (square_size, square_size), (0, 0, 0, 0))

                # Center the thumbnail on the square canvas
                offset_x = (square_size - img.width) // 2
                offset_y = (square_size - img.height) // 2
                square_canvas.paste(img, (offset_x, offset_y), img)

                # Use the square canvas instead of the original thumbnail
                img = square_canvas

                # Save thumbnail and track in database
                if cache_path:
                    # Create subdirectories if needed
                    cache_path.parent.mkdir(parents=True, exist_ok=True)

                    # Save image
                    img.save(cache_path, format='PNG')
                    logger.debug(f"✅ Saved new thumbnail: {relative_path}")

                    # Track in database if storage available
                    if self.storage:
                        # Calculate thumbnail hash for verification
                        thumbnail_bytes = cache_path.read_bytes()
                        thumbnail_hash = self.calculate_image_hash(thumbnail_bytes)

                        # Import ThumbnailRecord here to avoid circular import
                        try:
                            from fichero.library.models import ThumbnailRecord
                        except ImportError:
                            from .models import ThumbnailRecord

                        # Create thumbnail record
                        thumbnail_record = ThumbnailRecord(
                            source_file_hash=file_hash,
                            thumbnail_hash=thumbnail_hash,
                            thumbnail_path=str(relative_path),
                            size=size_str
                        )

                        # Save to database
                        self.storage.add_thumbnail(thumbnail_record)
                        logger.debug(f"📝 Tracked thumbnail in database: {file_hash[:8]}... -> {relative_path}")

                    # Load from cache to create Toga image
                    return self._load_toga_image(cache_path)
                else:
                    # No caching - create Toga image from bytes
                    img_bytes = io.BytesIO()
                    img.save(img_bytes, format='PNG')
                    img_bytes.seek(0)
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
