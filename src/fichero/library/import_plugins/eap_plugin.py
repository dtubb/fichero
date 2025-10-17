"""
British Library EAP (Endangered Archives Programme) Import Plugin

Downloads or links to files from British Library EAP project pages.
Supports both downloading files and creating direct links to resources.
"""

import logging
import re
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from urllib.parse import urlparse, urljoin, quote

import aiohttp
import aiofiles
from bs4 import BeautifulSoup

from .base import ImportPlugin, ImportResult

logger = logging.getLogger(__name__)


class EAPImportPlugin(ImportPlugin):
    """
    British Library EAP project import plugin

    Downloads or links to files from Endangered Archives Programme projects.
    Supports search results pages and individual item pages.
    """

    def __init__(self, library_manager):
        """
        Initialize EAP import plugin

        Args:
            library_manager: LibraryManager instance
        """
        super().__init__(library_manager)

    def can_handle(self, url: str) -> bool:
        """
        Check if this plugin can handle the given URL

        Handles British Library EAP URLs:
        - https://eap.bl.uk/project/[PROJECT_ID]/search
        - https://eap.bl.uk/archive/[ARCHIVE_ID]
        - https://eap.bl.uk/collection/[COLLECTION_ID]
        - https://eap.bl.uk/archive-file/[FILE_ID]/manifest (IIIF manifest)

        Args:
            url: URL to check

        Returns:
            True if plugin can handle this URL
        """
        parsed = urlparse(url)
        return (parsed.netloc.lower() == 'eap.bl.uk' and
                ('/project/' in parsed.path or
                 '/archive/' in parsed.path or
                 '/archive-file/' in parsed.path or
                 '/manifest' in parsed.path or
                 '/collection/' in parsed.path))

    async def download_and_import(
        self,
        url: str,
        collection_name: str,
        collection_description: str = "",
        max_items: int = 1000,
        download_mode: str = "link",  # "link" or "download"
        timeout: int = 600,
        **kwargs
    ) -> ImportResult:
        """
        Process EAP content and import into library

        Args:
            url: EAP project/archive/collection URL
            collection_name: Name for the new collection
            collection_description: Optional description
            max_items: Maximum number of items to process (default: 1000)
            download_mode: "link" to store URLs only, "download" to download files (default: "link")
            timeout: Timeout in seconds (default: 10 minutes)
            **kwargs: Additional options (ignored)

        Returns:
            ImportResult with import statistics
        """
        temp_download_dir = None

        try:
            logger.info(f"Starting EAP import from URL: {url} (mode: {download_mode})")
            self._report_progress(0, 100, f"Starting EAP import from {url}")

            # Create temp directory if downloading
            if download_mode == "download":
                temp_download_dir = Path(tempfile.mkdtemp(prefix='fichero_eap_import_'))
                logger.info(f"Created temp download directory: {temp_download_dir}")

            # Check if this is a IIIF manifest URL
            if 'manifest' in url or '/archive-file/' in url:
                self._report_progress(10, 100, "Fetching IIIF manifest")
                items = await self._fetch_iiif_manifest(url, timeout)
            else:
                # Parse EAP page and extract items
                self._report_progress(10, 100, "Fetching EAP project page")
                items = await self._fetch_eap_items(url, max_items, timeout)

            if self.is_cancelled:
                return ImportResult(
                    success=False,
                    error_message="Import cancelled by user",
                    collection_id=None,
                    files_imported=0
                )

            if not items:
                raise Exception("No items found in EAP project")

            logger.info(f"Found {len(items)} items in EAP project")
            self._report_progress(30, 100, f"Found {len(items)} items")

            # Process items based on mode
            if download_mode == "download":
                files_processed = await self._download_eap_files(
                    items,
                    temp_download_dir,
                    timeout
                )

                if self.is_cancelled:
                    return ImportResult(
                        success=False,
                        error_message="Import cancelled by user",
                        collection_id=None,
                        files_imported=0
                    )

                logger.info(f"Downloaded {files_processed} files from EAP")
                self._report_progress(80, 100, f"Downloaded {files_processed} files")

                # Import downloaded files
                result = await self._import_downloaded_files(
                    temp_download_dir,
                    collection_name,
                    collection_description
                )
            else:
                # Link mode: create metadata files with URLs
                self._report_progress(50, 100, "Creating link metadata")
                result = await self._import_linked_items(
                    items,
                    collection_name,
                    collection_description
                )

            self._report_progress(100, 100, "EAP import completed")
            logger.info(f"EAP import completed successfully")
            return result

        except Exception as e:
            logger.error(f"EAP import failed: {e}")
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

    async def _fetch_eap_items(
        self,
        url: str,
        max_items: int,
        timeout: int
    ) -> List[Dict[str, Any]]:
        """
        Fetch items from EAP project page

        Args:
            url: EAP project URL
            max_items: Maximum number of items to fetch
            timeout: Timeout in seconds

        Returns:
            List of item dictionaries with metadata
        """
        items = []

        try:
            timeout_obj = aiohttp.ClientTimeout(total=timeout)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }

            async with aiohttp.ClientSession(headers=headers, timeout=timeout_obj) as session:
                # Fetch the main page
                async with session.get(url) as response:
                    response.raise_for_status()
                    html = await response.text()

                if self.is_cancelled:
                    return items

                # Parse HTML
                soup = BeautifulSoup(html, 'html.parser')

                # Extract items based on page type
                if '/project/' in url and '/search' in url:
                    items = await self._parse_search_results(soup, url, max_items)
                elif '/archive/' in url:
                    items = await self._parse_archive_page(soup, url, max_items)
                elif '/collection/' in url:
                    items = await self._parse_collection_page(soup, url, max_items)

                logger.info(f"Extracted {len(items)} items from EAP page")

            return items

        except aiohttp.ClientError as e:
            logger.error(f"HTTP error accessing EAP: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to fetch EAP items: {e}")
            raise

    async def _fetch_iiif_manifest(
        self,
        manifest_url: str,
        timeout: int
    ) -> List[Dict[str, Any]]:
        """
        Fetch and parse IIIF manifest from EAP

        Args:
            manifest_url: IIIF manifest URL
            timeout: Timeout in seconds

        Returns:
            List of item dictionaries with image URLs
        """
        items = []

        try:
            timeout_obj = aiohttp.ClientTimeout(total=timeout)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }

            async with aiohttp.ClientSession(headers=headers, timeout=timeout_obj) as session:
                # Fetch the manifest JSON
                async with session.get(manifest_url) as response:
                    response.raise_for_status()
                    manifest = await response.json()

                if self.is_cancelled:
                    return items

                # Extract collection metadata
                collection_label = manifest.get('label', 'EAP Collection')
                collection_id = manifest.get('@id', manifest_url)
                metadata = manifest.get('metadata', [])

                logger.info(f"Processing IIIF manifest: {collection_label}")

                # Extract images from canvases
                sequences = manifest.get('sequences', [])
                if not sequences:
                    raise Exception("No sequences found in IIIF manifest")

                canvases = sequences[0].get('canvases', [])
                logger.info(f"Found {len(canvases)} canvases in manifest")

                for idx, canvas in enumerate(canvases):
                    if self.is_cancelled:
                        break

                    try:
                        # Extract canvas label/title
                        canvas_label = canvas.get('label', f'Image_{idx+1}')

                        # Extract images from canvas
                        canvas_images = canvas.get('images', [])
                        for img_idx, image_obj in enumerate(canvas_images):
                            resource = image_obj.get('resource', {})
                            image_url = resource.get('@id')

                            if image_url:
                                items.append({
                                    'title': f"{canvas_label}_{img_idx+1}" if img_idx > 0 else canvas_label,
                                    'url': image_url,
                                    'image_url': image_url,
                                    'type': 'iiif_image',
                                    'canvas_id': canvas.get('@id'),
                                    'collection_label': collection_label,
                                    'metadata': metadata
                                })

                                logger.debug(f"Found IIIF image: {canvas_label} -> {image_url}")

                    except Exception as e:
                        logger.warning(f"Failed to parse canvas {idx}: {e}")
                        continue

                logger.info(f"Extracted {len(items)} images from IIIF manifest")

            return items

        except aiohttp.ClientError as e:
            logger.error(f"HTTP error fetching IIIF manifest: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to fetch IIIF manifest: {e}")
            raise

    async def _parse_search_results(
        self,
        soup: BeautifulSoup,
        base_url: str,
        max_items: int
    ) -> List[Dict[str, Any]]:
        """
        Parse EAP search results page

        Args:
            soup: BeautifulSoup object
            base_url: Base URL for resolving relative links
            max_items: Maximum items to extract

        Returns:
            List of item dictionaries
        """
        items = []

        try:
            # Look for search result items
            # EAP typically uses div or article elements with specific classes
            result_items = soup.find_all(['div', 'article', 'li'],
                                        class_=re.compile(r'result|item|document|record'))

            for idx, item in enumerate(result_items[:max_items]):
                if self.is_cancelled:
                    break

                try:
                    # Extract title
                    title_elem = item.find(['h2', 'h3', 'h4', 'a'],
                                          class_=re.compile(r'title|heading'))
                    title = title_elem.get_text(strip=True) if title_elem else f"Item_{idx+1}"

                    # Extract link to detail page
                    link_elem = item.find('a', href=True)
                    if link_elem:
                        item_url = urljoin(base_url, link_elem['href'])

                        # Extract thumbnail or image URL if available
                        img_elem = item.find('img', src=True)
                        image_url = urljoin(base_url, img_elem['src']) if img_elem else None

                        items.append({
                            'title': title,
                            'url': item_url,
                            'image_url': image_url,
                            'type': 'archive_item'
                        })

                        logger.debug(f"Found item: {title} -> {item_url}")

                except Exception as e:
                    logger.warning(f"Failed to parse result item {idx}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to parse search results: {e}")

        return items

    async def _parse_archive_page(
        self,
        soup: BeautifulSoup,
        base_url: str,
        max_items: int
    ) -> List[Dict[str, Any]]:
        """
        Parse EAP archive detail page

        Args:
            soup: BeautifulSoup object
            base_url: Base URL
            max_items: Maximum items to extract

        Returns:
            List of item dictionaries
        """
        items = []

        try:
            # Look for download links and viewer links
            download_links = soup.find_all('a', href=re.compile(r'download|manifest|iiif|image'))

            for idx, link in enumerate(download_links[:max_items]):
                if self.is_cancelled:
                    break

                try:
                    href = link['href']
                    full_url = urljoin(base_url, href)

                    # Extract link text or nearby label
                    label = link.get_text(strip=True) or link.get('title', f"File_{idx+1}")

                    # Determine file type from URL
                    file_type = self._guess_file_type(full_url)

                    items.append({
                        'title': label,
                        'url': full_url,
                        'image_url': full_url if file_type in ['jpg', 'png', 'tif'] else None,
                        'type': file_type
                    })

                except Exception as e:
                    logger.warning(f"Failed to parse download link {idx}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to parse archive page: {e}")

        return items

    async def _parse_collection_page(
        self,
        soup: BeautifulSoup,
        base_url: str,
        max_items: int
    ) -> List[Dict[str, Any]]:
        """
        Parse EAP collection page

        Args:
            soup: BeautifulSoup object
            base_url: Base URL
            max_items: Maximum items to extract

        Returns:
            List of item dictionaries
        """
        # Collections often have similar structure to search results
        return await self._parse_search_results(soup, base_url, max_items)

    def _guess_file_type(self, url: str) -> str:
        """Guess file type from URL"""
        url_lower = url.lower()
        if any(ext in url_lower for ext in ['.jpg', '.jpeg']):
            return 'jpg'
        elif '.png' in url_lower:
            return 'png'
        elif any(ext in url_lower for ext in ['.tif', '.tiff']):
            return 'tif'
        elif '.pdf' in url_lower:
            return 'pdf'
        elif 'iiif' in url_lower or 'manifest' in url_lower:
            return 'iiif'
        else:
            return 'unknown'

    async def _download_eap_files(
        self,
        items: List[Dict[str, Any]],
        download_dir: Path,
        timeout: int
    ) -> int:
        """
        Download files from EAP items

        Args:
            items: List of item dictionaries
            download_dir: Directory to download to
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
                for idx, item in enumerate(items):
                    if self.is_cancelled:
                        logger.info("Download cancelled by user")
                        break

                    try:
                        # Report progress
                        progress = 30 + int((idx / len(items)) * 50)
                        self._report_progress(progress, 100, f"Downloading {item['title']}")

                        # Download image if available
                        download_url = item.get('image_url') or item.get('url')
                        if not download_url:
                            continue

                        # Generate safe filename
                        title_safe = re.sub(r'[^\w\s-]', '', item['title'])[:100]
                        file_ext = self._guess_extension(download_url, item['type'])
                        filename = f"{title_safe}_{idx}{file_ext}"
                        file_path = download_dir / filename

                        logger.info(f"Downloading {idx+1}/{len(items)}: {item['title']}")

                        # Download file
                        async with session.get(download_url) as response:
                            response.raise_for_status()

                            async with aiofiles.open(file_path, 'wb') as f:
                                async for chunk in response.content.iter_chunked(8192):
                                    await f.write(chunk)

                        files_downloaded += 1
                        logger.info(f"Downloaded: {filename}")

                    except Exception as e:
                        logger.error(f"Failed to download {item.get('title', 'unknown')}: {e}")
                        continue

        except Exception as e:
            logger.error(f"Download session failed: {e}")
            raise

        return files_downloaded

    def _guess_extension(self, url: str, file_type: str) -> str:
        """Guess file extension from URL and type"""
        if file_type == 'jpg':
            return '.jpg'
        elif file_type == 'png':
            return '.png'
        elif file_type == 'tif':
            return '.tif'
        elif file_type == 'pdf':
            return '.pdf'
        else:
            # Try to extract from URL
            parsed = urlparse(url)
            path = Path(parsed.path)
            if path.suffix:
                return path.suffix
            return '.jpg'  # Default to jpg

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
            collection_name: Collection name
            collection_description: Collection description

        Returns:
            ImportResult with statistics
        """
        try:
            # Create collection
            collection_id = await self.library_manager.add_collection(
                name=collection_name,
                collection_type="local",
                source_path=str(download_dir),
                description=collection_description or "Imported from British Library EAP"
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

    async def _import_linked_items(
        self,
        items: List[Dict[str, Any]],
        collection_name: str,
        collection_description: str
    ) -> ImportResult:
        """
        Import items as URL links (without downloading)

        Args:
            items: List of item dictionaries
            collection_name: Collection name
            collection_description: Collection description

        Returns:
            ImportResult with statistics
        """
        try:
            # Create collection with url type (for web-based resources)
            collection_id = await self.library_manager.add_collection(
                name=collection_name,
                collection_type="url",
                source_path="",
                description=collection_description or "Linked from British Library EAP"
            )

            if not collection_id:
                raise Exception("Failed to create collection")

            # Add items as URL items with metadata
            added_count = 0
            skipped_count = 0
            error_count = 0

            for idx, item in enumerate(items):
                if self.is_cancelled:
                    break

                try:
                    progress = 50 + int((idx / len(items)) * 50)
                    self._report_progress(progress, 100, f"Linking {item['title']}")

                    # Prefer image_url (direct image) over url (page URL)
                    item_url = item.get('image_url') or item.get('url')
                    if not item_url:
                        logger.warning(f"No URL found for item: {item.get('title')}")
                        skipped_count += 1
                        continue

                    # Create metadata for URL item
                    metadata = {
                        'title': item['title'],
                        'image_url': item.get('image_url'),
                        'page_url': item.get('url'),
                        'type': item.get('type', 'unknown'),
                        'source': 'British Library EAP',
                        'canvas_id': item.get('canvas_id'),
                        'collection_label': item.get('collection_label')
                    }

                    # Add URL item to collection
                    item_id = await self.library_manager.add_item_to_collection(
                        collection_id=collection_id,
                        item_type="url",
                        source=item_url,
                        name=item['title'],
                        operation="link",
                        metadata=metadata
                    )

                    if item_id:
                        added_count += 1
                        logger.info(f"Linked: {item['title']} -> {item_url}")
                    else:
                        error_count += 1
                        logger.error(f"Failed to add item: {item['title']}")

                except Exception as e:
                    logger.error(f"Failed to link item {item.get('title')}: {e}")
                    error_count += 1
                    continue

            return ImportResult(
                success=True,
                collection_id=collection_id,
                collection_name=collection_name,
                files_imported=added_count,
                files_skipped=skipped_count,
                errors=error_count,
                metadata={'mode': 'link', 'note': f'Items stored as URL links (no download)'}
            )

        except Exception as e:
            logger.error(f"Failed to import linked items: {e}")
            raise

    def get_plugin_info(self) -> Dict[str, Any]:
        """
        Get plugin metadata

        Returns:
            Plugin information dictionary
        """
        return {
            "name": "British Library EAP Import",
            "version": "1.0.0",
            "description": "Download or link to files from British Library Endangered Archives Programme projects",
            "supported_domains": [
                "eap.bl.uk"
            ],
            "options": [
                {
                    "name": "max_items",
                    "type": "int",
                    "default": 1000,
                    "description": "Maximum number of items to process"
                },
                {
                    "name": "download_mode",
                    "type": "str",
                    "default": "link",
                    "description": "Processing mode: 'link' (store URLs only) or 'download' (download files)"
                },
                {
                    "name": "timeout",
                    "type": "int",
                    "default": 600,
                    "description": "Timeout in seconds"
                }
            ],
            "notes": [
                "Supports EAP project search pages, archive pages, and collection pages",
                "Link mode stores URLs without downloading (faster, less storage)",
                "Download mode downloads actual files (slower, requires storage)",
                "Supports progress tracking and cancellation",
                "Uses web scraping - may need updates if EAP changes structure"
            ]
        }
