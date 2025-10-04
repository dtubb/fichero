"""
URL Downloader for Library System

Downloads and caches URLs for local access.
"""

import asyncio
import aiohttp
import aiofiles
import hashlib
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class URLDownloader:
    """Downloads and caches URLs for library items"""

    def __init__(self, cache_root: Path):
        """
        Initialize URL downloader

        Args:
            cache_root: Root directory for cached files
        """
        self.cache_root = Path(cache_root)
        self.cache_root.mkdir(parents=True, exist_ok=True)

    async def download_url(
        self,
        url: str,
        collection_id: str,
        item_id: str,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """
        Download a URL and cache it locally

        Args:
            url: URL to download
            collection_id: ID of the collection
            item_id: ID of the item
            timeout: Download timeout in seconds

        Returns:
            Dict with cache metadata
        """
        try:
            # Create collection cache directory
            collection_cache = self.cache_root / collection_id
            collection_cache.mkdir(parents=True, exist_ok=True)

            # Extract filename from URL
            filename = self._extract_filename(url)
            cache_filename = f"{item_id}_{filename}"
            cache_path = collection_cache / cache_filename

            # Check if already cached
            if cache_path.exists():
                logger.info(f"File already cached: {cache_path}")
                return await self._get_cache_metadata(cache_path, url)

            # Download file
            logger.info(f"Downloading {url} to {cache_path}")

            # Set User-Agent header to avoid 403 errors from some servers
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }

            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, timeout=timeout) as response:
                    response.raise_for_status()

                    # Get content type
                    content_type = response.headers.get('Content-Type', 'application/octet-stream')

                    # Download to temp file first
                    temp_path = cache_path.with_suffix('.tmp')

                    # Calculate hash while downloading
                    hasher = hashlib.sha256()
                    file_size = 0

                    async with aiofiles.open(temp_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)
                            hasher.update(chunk)
                            file_size += len(chunk)

                    # Rename temp to final
                    temp_path.rename(cache_path)

                    # Create metadata
                    metadata = {
                        "cached_path": str(cache_path),
                        "cached_at": datetime.now().isoformat(),
                        "file_size": file_size,
                        "content_type": content_type,
                        "checksum": hasher.hexdigest(),
                        "original_url": url
                    }

                    logger.info(f"Downloaded {file_size} bytes to {cache_path}")
                    return metadata

        except asyncio.TimeoutError:
            logger.error(f"Timeout downloading {url}")
            raise Exception(f"Download timeout for {url}")
        except aiohttp.ClientError as e:
            logger.error(f"HTTP error downloading {url}: {e}")
            raise Exception(f"HTTP error: {e}")
        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            raise

    async def _get_cache_metadata(self, cache_path: Path, url: str) -> Dict[str, Any]:
        """Get metadata for already cached file"""
        try:
            stat = cache_path.stat()

            # Calculate checksum
            hasher = hashlib.sha256()
            async with aiofiles.open(cache_path, 'rb') as f:
                while chunk := await f.read(8192):
                    hasher.update(chunk)

            return {
                "cached_path": str(cache_path),
                "cached_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "file_size": stat.st_size,
                "content_type": self._guess_content_type(cache_path),
                "checksum": hasher.hexdigest(),
                "original_url": url
            }
        except Exception as e:
            logger.error(f"Failed to get cache metadata: {e}")
            raise

    def _extract_filename(self, url: str) -> str:
        """Extract filename from URL"""
        from urllib.parse import urlparse, unquote

        path = urlparse(url).path
        filename = unquote(path.split('/')[-1])

        # If no filename, use hash of URL
        if not filename or '.' not in filename:
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            filename = f"download_{url_hash}"

        return filename

    def _guess_content_type(self, path: Path) -> str:
        """Guess content type from file extension"""
        import mimetypes
        content_type, _ = mimetypes.guess_type(str(path))
        return content_type or 'application/octet-stream'

    def get_cache_size(self, collection_id: Optional[str] = None) -> int:
        """
        Get total size of cached files

        Args:
            collection_id: Optional collection ID to filter by

        Returns:
            Total size in bytes
        """
        try:
            if collection_id:
                cache_dir = self.cache_root / collection_id
                if not cache_dir.exists():
                    return 0
                dirs = [cache_dir]
            else:
                dirs = [self.cache_root]

            total_size = 0
            for cache_dir in dirs:
                for file_path in cache_dir.rglob('*'):
                    if file_path.is_file() and not file_path.suffix == '.tmp':
                        total_size += file_path.stat().st_size

            return total_size

        except Exception as e:
            logger.error(f"Failed to get cache size: {e}")
            return 0

    def clear_cache(self, collection_id: Optional[str] = None) -> int:
        """
        Clear cached files

        Args:
            collection_id: Optional collection ID to clear (clears all if None)

        Returns:
            Number of files deleted
        """
        try:
            if collection_id:
                cache_dir = self.cache_root / collection_id
                if not cache_dir.exists():
                    return 0
                dirs = [cache_dir]
            else:
                dirs = list(self.cache_root.iterdir())

            deleted_count = 0
            for cache_dir in dirs:
                if cache_dir.is_dir():
                    for file_path in cache_dir.iterdir():
                        if file_path.is_file():
                            file_path.unlink()
                            deleted_count += 1
                    # Remove empty directory
                    if not list(cache_dir.iterdir()):
                        cache_dir.rmdir()

            logger.info(f"Cleared {deleted_count} cached files")
            return deleted_count

        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return 0
