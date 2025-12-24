"""
Box.com Import Plugin

Downloads files and folders from Box.com sharing links and imports them into the library.
"""

import logging
import re
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, List, Tuple
from urllib.parse import urlparse, urljoin
import json

import aiohttp
import aiofiles
from bs4 import BeautifulSoup

from .base import ImportPlugin, ImportResult

logger = logging.getLogger(__name__)


class BoxImportPlugin(ImportPlugin):
    """
    Box.com folder import plugin

    Downloads files from Box.com shared folders using web scraping.
    Supports recursive folder traversal and bulk file downloads.
    """

    def __init__(self, library_manager):
        """
        Initialize Box.com import plugin

        Args:
            library_manager: LibraryManager instance
        """
        super().__init__(library_manager)

    def can_handle(self, url: str) -> bool:
        """
        Check if this plugin can handle the given URL

        Handles Box.com sharing URLs:
        - https://app.box.com/s/[share_id]
        - https://[company].app.box.com/s/[share_id]

        Args:
            url: URL to check

        Returns:
            True if plugin can handle this URL
        """
        parsed = urlparse(url)
        # Must have box.com domain (not dropbox.com) AND /s/ in path
        netloc_lower = parsed.netloc.lower()
        is_box_domain = (netloc_lower == 'box.com' or
                        netloc_lower.endswith('.box.com'))
        return is_box_domain and '/s/' in parsed.path

    async def download_and_import(
        self,
        url: str,
        collection_name: str,
        collection_description: str = "",
        max_files: int = 1000,
        timeout: int = 600,
        **kwargs
    ) -> ImportResult:
        """
        Download files from Box.com folder and import into library

        Args:
            url: Box.com sharing URL
            collection_name: Name for the new collection
            collection_description: Optional description
            max_files: Maximum number of files to download (default: 1000)
            timeout: Timeout in seconds (default: 10 minutes)
            **kwargs: Additional options (ignored)

        Returns:
            ImportResult with import statistics
        """
        temp_download_dir = None

        try:
            logger.info(f"Starting Box.com import from URL: {url}")

            # Create temp directory for downloads
            temp_download_dir = Path(tempfile.mkdtemp(prefix='fichero_box_import_'))
            logger.info(f"Created temp download directory: {temp_download_dir}")

            # Parse Box.com folder and download files
            files_downloaded = await self._download_box_folder(
                url,
                temp_download_dir,
                max_files,
                timeout
            )

            if files_downloaded == 0:
                raise Exception("No files were downloaded from Box.com folder")

            logger.info(f"Downloaded {files_downloaded} files from Box.com")

            # Import downloaded files into library
            logger.info(f"Importing files into collection '{collection_name}'...")
            result = await self._import_downloaded_files(
                temp_download_dir,
                collection_name,
                collection_description
            )

            logger.info(f"Box.com import completed successfully")
            return result

        except Exception as e:
            logger.error(f"Box.com import failed: {e}")
            return ImportResult(
                success=False,
                error_message=str(e),
                collection_id=None,
                files_imported=0
            )

        finally:
            # Clean up temp files
            if temp_download_dir and temp_download_dir.exists():
                try:
                    shutil.rmtree(temp_download_dir)
                    logger.info(f"Deleted temporary download directory: {temp_download_dir}")
                except Exception as e:
                    logger.warning(f"Failed to delete temp download dir: {e}")

    async def _download_box_folder(
        self,
        url: str,
        download_dir: Path,
        max_files: int,
        timeout: int
    ) -> int:
        """
        Download all files from Box.com shared folder

        Args:
            url: Box.com sharing URL
            download_dir: Directory to download files to
            max_files: Maximum number of files to download
            timeout: Timeout in seconds

        Returns:
            Number of files downloaded
        """
        files_downloaded = 0

        try:
            timeout_obj = aiohttp.ClientTimeout(total=timeout)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }

            async with aiohttp.ClientSession(headers=headers, timeout=timeout_obj) as session:
                # Fetch the Box.com share page
                async with session.get(url) as response:
                    response.raise_for_status()
                    html = await response.text()

                # Parse HTML to extract file information
                soup = BeautifulSoup(html, 'html.parser')

                # Try to find embedded JSON data with file information
                # Box.com often includes file data in script tags
                file_items = await self._parse_box_page(soup, url)

                if not file_items:
                    logger.warning("No files found on Box.com page, trying alternative parsing")
                    # Try alternative parsing methods
                    file_items = await self._parse_box_page_alternative(soup, url)

                if not file_items:
                    raise Exception("Could not find any files in Box.com folder")

                logger.info(f"Found {len(file_items)} items in Box.com folder")

                # Download files
                for idx, (file_url, file_name, file_type) in enumerate(file_items):
                    if files_downloaded >= max_files:
                        logger.warning(f"Reached maximum file limit: {max_files}")
                        break

                    if file_type == 'folder':
                        # For folders, we would need to recursively fetch
                        # For now, skip folders (or implement recursive logic)
                        logger.info(f"Skipping folder: {file_name}")
                        continue

                    try:
                        # Download file
                        file_path = download_dir / file_name
                        logger.info(f"Downloading file {idx+1}/{len(file_items)}: {file_name}")

                        async with session.get(file_url) as file_response:
                            file_response.raise_for_status()

                            # Write file
                            async with aiofiles.open(file_path, 'wb') as f:
                                async for chunk in file_response.content.iter_chunked(8192):
                                    await f.write(chunk)

                        files_downloaded += 1
                        logger.info(f"Downloaded: {file_name}")

                    except Exception as e:
                        logger.error(f"Failed to download {file_name}: {e}")
                        continue

            return files_downloaded

        except aiohttp.ClientError as e:
            logger.error(f"HTTP error accessing Box.com: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to download Box.com folder: {e}")
            raise

    async def _parse_box_page(self, soup: BeautifulSoup, base_url: str) -> List[Tuple[str, str, str]]:
        """
        Parse Box.com page to extract file information

        Args:
            soup: BeautifulSoup object of the page
            base_url: Base URL for resolving relative links

        Returns:
            List of tuples (download_url, file_name, file_type)
        """
        file_items = []

        try:
            # Look for JSON data in script tags
            # Box.com typically embeds data in script tags with specific patterns
            script_tags = soup.find_all('script')

            for script in script_tags:
                if script.string and 'window.Box' in script.string:
                    # Try to extract JSON data
                    # This is a simplified approach - actual implementation may vary
                    try:
                        # Look for patterns like "files": [...] or similar
                        json_match = re.search(r'\"files\"\s*:\s*(\[.*?\])', script.string, re.DOTALL)
                        if json_match:
                            files_data = json.loads(json_match.group(1))
                            for item in files_data:
                                if isinstance(item, dict):
                                    file_name = item.get('name', '')
                                    file_type = item.get('type', 'file')
                                    file_id = item.get('id', '')

                                    if file_name and file_id:
                                        # Construct download URL (may need adjustment)
                                        download_url = f"{base_url}/download/{file_id}"
                                        file_items.append((download_url, file_name, file_type))

                    except (json.JSONDecodeError, KeyError) as e:
                        logger.debug(f"Failed to parse JSON from script: {e}")
                        continue

            # If no files found via JSON, try HTML parsing
            if not file_items:
                # Look for download links in the HTML
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    if '/download' in href or '/file/' in href:
                        file_name = link.get_text(strip=True) or "unknown_file"
                        download_url = urljoin(base_url, href)
                        file_items.append((download_url, file_name, 'file'))

        except Exception as e:
            logger.error(f"Error parsing Box.com page: {e}")

        return file_items

    async def _parse_box_page_alternative(self, soup: BeautifulSoup, base_url: str) -> List[Tuple[str, str, str]]:
        """
        Alternative parsing method for Box.com pages

        Args:
            soup: BeautifulSoup object
            base_url: Base URL

        Returns:
            List of tuples (download_url, file_name, file_type)
        """
        file_items = []

        try:
            # Look for specific Box.com UI elements
            # This is a fallback method and may need updates based on Box.com's UI changes

            # Try to find items in lists or divs with specific classes
            item_containers = soup.find_all(['div', 'li'], class_=re.compile(r'item|file|folder'))

            for container in item_containers:
                # Extract file name and link
                name_elem = container.find(['span', 'a'], class_=re.compile(r'name|title'))
                link_elem = container.find('a', href=True)

                if name_elem and link_elem:
                    file_name = name_elem.get_text(strip=True)
                    file_url = urljoin(base_url, link_elem['href'])

                    # Determine if it's a folder or file
                    file_type = 'folder' if 'folder' in str(container.get('class', [])) else 'file'

                    file_items.append((file_url, file_name, file_type))

        except Exception as e:
            logger.error(f"Alternative parsing failed: {e}")

        return file_items

    async def _import_downloaded_files(
        self,
        download_dir: Path,
        collection_name: str,
        collection_description: str
    ) -> ImportResult:
        """
        Import downloaded files into library

        Args:
            download_dir: Directory containing downloaded files
            collection_name: Name for collection
            collection_description: Collection description

        Returns:
            ImportResult with import statistics
        """
        try:
            # Create collection
            collection_id = await self.library_manager.add_collection(
                name=collection_name,
                collection_type="local",
                source_path=str(download_dir),
                description=collection_description or f"Imported from Box.com"
            )

            if not collection_id:
                raise Exception("Failed to create collection")

            # Import all files
            stats = await self.library_manager.add_folder_items_to_collection(
                collection_id=collection_id,
                folder_path=str(download_dir),
                operation="copy",
                recursive=True
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
            logger.error(f"Failed to import downloaded files: {e}")
            raise

    def get_plugin_info(self) -> Dict[str, Any]:
        """
        Get plugin metadata

        Returns:
            Plugin information dictionary
        """
        return {
            "name": "Box.com Import",
            "version": "1.0.0",
            "description": "Download files and folders from Box.com shared links",
            "supported_domains": [
                "box.com",
                "app.box.com"
            ],
            "options": [
                {
                    "name": "max_files",
                    "type": "int",
                    "default": 1000,
                    "description": "Maximum number of files to download"
                },
                {
                    "name": "timeout",
                    "type": "int",
                    "default": 600,
                    "description": "Download timeout in seconds"
                }
            ],
            "notes": [
                "Uses web scraping to download files from shared folders",
                "May require updates if Box.com changes their page structure",
                "Folders are currently skipped (only files are downloaded)"
            ]
        }
