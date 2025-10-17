"""
ZIP File Import Plugin

Downloads ZIP files from URLs (including OneDrive/SharePoint), extracts them,
and imports content into the library.
"""

import logging
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, Any
from urllib.parse import urlparse, parse_qs, unquote, quote

import aiohttp
import aiofiles

from .base import ImportPlugin, ImportResult

logger = logging.getLogger(__name__)


class OneDriveLinkConverter:
    """Convert OneDrive/SharePoint sharing links to direct download URLs"""

    @staticmethod
    def is_onedrive_link(url: str) -> bool:
        """Check if URL is a OneDrive/SharePoint sharing link"""
        parsed = urlparse(url)
        return (
            'sharepoint.com' in parsed.netloc.lower() or
            'onedrive.live.com' in parsed.netloc.lower() or
            '1drv.ms' in parsed.netloc.lower()
        )

    @staticmethod
    def convert_to_direct_download(url: str) -> str:
        """
        Convert OneDrive/SharePoint sharing link to direct download URL

        Supports formats:
        - https://[tenant]-my.sharepoint.com/:u:/g/personal/[user]/[id]?e=[token]
        - https://[tenant].sharepoint.com/my?id=[path]  (view URL)
        - https://onedrive.live.com/download?[params]
        - https://1drv.ms/[short_code]

        Args:
            url: OneDrive/SharePoint sharing URL

        Returns:
            Direct download URL
        """
        try:
            parsed = urlparse(url)

            # SharePoint format
            if 'sharepoint.com' in parsed.netloc.lower():
                # Check for /my?id= format (view URL)
                if '/my' in parsed.path and 'id=' in parsed.query:
                    # Extract the file path from id parameter
                    query_params = parse_qs(parsed.query)
                    file_path = query_params.get('id', [''])[0]

                    if file_path:
                        # Decode URL encoding
                        file_path = unquote(file_path)
                        # Build direct download URL
                        base_url = f"{parsed.scheme}://{parsed.netloc}"
                        # Re-encode for SourceUrl parameter
                        encoded_path = quote(file_path, safe='')
                        direct_url = f"{base_url}/_layouts/15/download.aspx?SourceUrl={encoded_path}"
                        logger.info(f"Converted SharePoint view URL to download URL")
                        return direct_url

                # Check for /_layouts/15/download.aspx format (already direct download)
                elif '/_layouts/15/download.aspx' in parsed.path:
                    logger.info(f"URL is already a direct download link")
                    return url

                # Replace :u: (preview) with :d: (download)
                direct_url = url.replace('/:u:/', '/:d:/')

                # If still has :u:, try alternative format
                if '/:u:/' in direct_url:
                    # Parse components
                    parts = parsed.path.split('/')
                    if len(parts) >= 4:
                        # Build download URL
                        base_url = f"{parsed.scheme}://{parsed.netloc}"
                        share_param = parse_qs(parsed.query).get('share', [''])[0]
                        if share_param:
                            direct_url = f"{base_url}/_layouts/15/download.aspx?share={share_param}"

                logger.info(f"Converted SharePoint URL: {url} -> {direct_url}")
                return direct_url

            # OneDrive format
            elif 'onedrive.live.com' in parsed.netloc.lower():
                # Already in download format or needs conversion
                if '/download' in parsed.path:
                    return url
                else:
                    # Convert view link to download link
                    return url.replace('/view.aspx', '/download.aspx')

            # 1drv.ms short links (need to follow redirect)
            elif '1drv.ms' in parsed.netloc.lower():
                logger.info(f"Short link detected: {url} (will follow redirects)")
                return url  # Will be handled by aiohttp follow_redirects

            # Unknown format, return as-is
            logger.warning(f"Unknown OneDrive URL format: {url}")
            return url

        except Exception as e:
            logger.error(f"Failed to convert OneDrive URL: {e}")
            return url


class ZipImportPlugin(ImportPlugin):
    """
    ZIP file download and import plugin

    Downloads ZIP files from direct URLs or cloud storage links (OneDrive/SharePoint),
    extracts contents, and imports into library collections.
    """

    def __init__(self, library_manager):
        """
        Initialize ZIP import plugin

        Args:
            library_manager: LibraryManager instance
        """
        super().__init__(library_manager)
        self.link_converter = OneDriveLinkConverter()

    def can_handle(self, url: str) -> bool:
        """
        Check if this plugin can handle the given URL

        Handles:
        - Direct .zip URLs
        - OneDrive/SharePoint sharing links
        - Any URL if it's explicitly a ZIP file

        Args:
            url: URL to check

        Returns:
            True if plugin can handle this URL
        """
        # Check if it's a OneDrive/SharePoint link
        if self.link_converter.is_onedrive_link(url):
            return True

        # Check if URL ends with .zip
        parsed = urlparse(url)
        if parsed.path.lower().endswith('.zip'):
            return True

        return False

    async def download_and_import(
        self,
        url: str,
        collection_name: str,
        collection_description: str = "",
        timeout: int = 300,
        max_zip_size_mb: int = 500,
        **kwargs
    ) -> ImportResult:
        """
        Download ZIP from URL, extract, and import into library

        Args:
            url: URL to ZIP file (supports OneDrive/SharePoint links) or local file path
            collection_name: Name for the new collection
            collection_description: Optional description
            timeout: Download timeout in seconds (default: 5 minutes)
            max_zip_size_mb: Maximum allowed ZIP size in MB (default: 500MB)
            **kwargs: Additional options (ignored)

        Returns:
            ImportResult with import statistics
        """
        temp_zip_path = None
        temp_extract_dir = None
        is_local_file = False

        try:
            logger.info(f"Starting ZIP import from: {url}")

            # Check if it's a local file path
            if url.startswith('file://'):
                # Convert file:// URL to local path
                from urllib.parse import unquote
                local_path = Path(unquote(url[7:]))  # Remove 'file://' prefix
                if local_path.exists() and local_path.is_file():
                    temp_zip_path = local_path
                    is_local_file = True
                    logger.info(f"Using local file: {temp_zip_path}")
                else:
                    raise ValueError(f"Local file not found: {local_path}")
            elif not url.startswith(('http://', 'https://')):
                # Assume it's a local file path
                local_path = Path(url)
                if local_path.exists() and local_path.is_file():
                    temp_zip_path = local_path
                    is_local_file = True
                    logger.info(f"Using local file: {temp_zip_path}")
                else:
                    raise ValueError(f"Local file not found: {local_path}")
            else:
                # It's a URL - download it
                # Convert OneDrive links if needed
                download_url = url
                if self.link_converter.is_onedrive_link(url):
                    logger.info("OneDrive/SharePoint link detected, converting to direct download URL")
                    download_url = self.link_converter.convert_to_direct_download(url)

                # Download ZIP to temp file
                logger.info("Downloading ZIP file...")
                temp_zip_path = await self._download_zip(download_url, timeout, max_zip_size_mb)

            # Validate ZIP file
            logger.info("Validating ZIP file...")
            if not await self._validate_zip(temp_zip_path):
                raise ValueError("Invalid or corrupted ZIP file")

            # Extract to temp directory
            logger.info("Extracting ZIP file...")
            temp_extract_dir = await self._extract_zip(temp_zip_path)

            # Import extracted contents into library
            logger.info(f"Importing contents into collection '{collection_name}'...")
            result = await self._import_extracted_files(
                temp_extract_dir,
                collection_name,
                collection_description
            )

            # Clean up ZIP file (only if it was downloaded, not a local file)
            if not is_local_file and temp_zip_path and temp_zip_path.exists():
                temp_zip_path.unlink()
                logger.info(f"Deleted temporary ZIP file: {temp_zip_path}")

            logger.info(f"ZIP import completed successfully")
            return result

        except Exception as e:
            logger.error(f"ZIP import failed: {e}")
            return ImportResult(
                success=False,
                error_message=str(e),
                collection_id=None,
                files_imported=0
            )

        finally:
            # Clean up temp files (only if it was downloaded, not a local file)
            if not is_local_file and temp_zip_path and temp_zip_path.exists():
                try:
                    temp_zip_path.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete temp ZIP: {e}")

            if temp_extract_dir and temp_extract_dir.exists():
                try:
                    shutil.rmtree(temp_extract_dir)
                    logger.info(f"Deleted temporary extraction directory: {temp_extract_dir}")
                except Exception as e:
                    logger.warning(f"Failed to delete temp extraction dir: {e}")

    async def _download_zip(
        self,
        url: str,
        timeout: int,
        max_size_mb: int
    ) -> Path:
        """
        Download ZIP file from URL to temporary location

        Args:
            url: URL to download
            timeout: Timeout in seconds
            max_size_mb: Maximum file size in MB

        Returns:
            Path to downloaded ZIP file
        """
        try:
            # Create temp file for ZIP
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
            temp_path = Path(temp_file.name)
            temp_file.close()

            # Download with aiohttp
            timeout_obj = aiohttp.ClientTimeout(total=timeout)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }

            async with aiohttp.ClientSession(headers=headers, timeout=timeout_obj) as session:
                async with session.get(url, allow_redirects=True) as response:
                    response.raise_for_status()

                    # Check content length
                    content_length = response.headers.get('Content-Length')
                    if content_length:
                        size_mb = int(content_length) / (1024 * 1024)
                        if size_mb > max_size_mb:
                            raise ValueError(f"ZIP file too large: {size_mb:.1f}MB (max: {max_size_mb}MB)")
                        logger.info(f"Downloading ZIP file ({size_mb:.1f}MB)...")

                    # Download in chunks
                    downloaded = 0
                    async with aiofiles.open(temp_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)
                            downloaded += len(chunk)

                            # Check size during download
                            if downloaded > max_size_mb * 1024 * 1024:
                                raise ValueError(f"Download exceeded maximum size: {max_size_mb}MB")

            file_size_mb = temp_path.stat().st_size / (1024 * 1024)
            logger.info(f"ZIP file downloaded successfully: {file_size_mb:.1f}MB")
            return temp_path

        except aiohttp.ClientError as e:
            logger.error(f"HTTP error downloading ZIP: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to download ZIP: {e}")
            if 'temp_path' in locals() and temp_path.exists():
                temp_path.unlink()
            raise

    async def _validate_zip(self, zip_path: Path) -> bool:
        """
        Validate ZIP file integrity and security

        Args:
            zip_path: Path to ZIP file

        Returns:
            True if valid, False otherwise
        """
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                # Test ZIP integrity
                bad_file = zf.testzip()
                if bad_file:
                    logger.error(f"Corrupted file in ZIP: {bad_file}")
                    return False

                # Check for dangerous paths (path traversal attack)
                for name in zf.namelist():
                    if name.startswith('/') or '..' in name:
                        logger.error(f"Suspicious path in ZIP: {name}")
                        return False

                logger.info(f"ZIP file validated successfully ({len(zf.namelist())} files)")
                return True

        except zipfile.BadZipFile:
            logger.error("Invalid ZIP file format")
            return False
        except Exception as e:
            logger.error(f"ZIP validation failed: {e}")
            return False

    async def _extract_zip(self, zip_path: Path) -> Path:
        """
        Extract ZIP file to temporary directory

        Args:
            zip_path: Path to ZIP file

        Returns:
            Path to extraction directory
        """
        try:
            # Create temp extraction directory
            temp_dir = Path(tempfile.mkdtemp(prefix='fichero_zip_import_'))

            # Extract ZIP
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(temp_dir)

            logger.info(f"ZIP extracted to: {temp_dir}")
            return temp_dir

        except Exception as e:
            logger.error(f"ZIP extraction failed: {e}")
            raise

    async def _import_extracted_files(
        self,
        extract_dir: Path,
        collection_name: str,
        collection_description: str
    ) -> ImportResult:
        """
        Import extracted files into library based on folder structure

        Args:
            extract_dir: Path to extracted files
            collection_name: Name for collection
            collection_description: Collection description

        Returns:
            ImportResult with import statistics
        """
        try:
            # Find root folder (skip __MACOSX and hidden folders)
            root_folders = [
                d for d in extract_dir.iterdir()
                if d.is_dir() and not d.name.startswith('.') and d.name != '__MACOSX'
            ]

            # If single root folder, use its contents
            if len(root_folders) == 1:
                import_path = root_folders[0]
                logger.info(f"Using single root folder: {import_path.name}")
            else:
                import_path = extract_dir
                logger.info(f"Using extraction root (multiple folders)")

            # Create collection
            collection_id = await self.library_manager.add_collection(
                name=collection_name,
                collection_type="local",
                source_path=str(import_path),
                description=collection_description or f"Imported from ZIP file"
            )

            if not collection_id:
                raise Exception("Failed to create collection")

            # Import all files based on folder structure
            stats = await self.library_manager.add_folder_items_to_collection(
                collection_id=collection_id,
                folder_path=str(import_path),
                operation="copy",  # Copy files to library
                recursive=True  # Preserve folder structure
            )

            return ImportResult(
                success=True,
                collection_id=collection_id,
                collection_name=collection_name,
                files_imported=stats.get("added", 0),
                files_skipped=stats.get("skipped", 0),
                errors=stats.get("errors", 0)
            )

        except Exception as e:
            logger.error(f"Failed to import extracted files: {e}")
            raise

    def get_plugin_info(self) -> Dict[str, Any]:
        """
        Get plugin metadata

        Returns:
            Plugin information dictionary
        """
        return {
            "name": "ZIP Import",
            "version": "1.0.0",
            "description": "Download and import ZIP files from direct URLs and cloud storage (OneDrive/SharePoint)",
            "supported_domains": [
                "sharepoint.com",
                "onedrive.live.com",
                "1drv.ms",
                "*.zip"
            ],
            "options": [
                {
                    "name": "timeout",
                    "type": "int",
                    "default": 300,
                    "description": "Download timeout in seconds"
                },
                {
                    "name": "max_zip_size_mb",
                    "type": "int",
                    "default": 500,
                    "description": "Maximum ZIP file size in MB"
                }
            ]
        }
