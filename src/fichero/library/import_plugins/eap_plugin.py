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
        - https://dx.doi.org/10.15130/EAP[PROJECT_ID] (DOI redirects)

        Args:
            url: URL to check

        Returns:
            True if plugin can handle this URL
        """
        parsed = urlparse(url)

        # Handle direct eap.bl.uk URLs
        if parsed.netloc.lower() == 'eap.bl.uk':
            return ('/project/' in parsed.path or
                    '/archive/' in parsed.path or
                    '/archive-file/' in parsed.path or
                    '/manifest' in parsed.path or
                    '/collection/' in parsed.path)

        # Handle DOI URLs that redirect to EAP (dx.doi.org/10.15130/EAP*)
        if parsed.netloc.lower() == 'dx.doi.org':
            # Check if this is an EAP DOI (format: 10.15130/EAP*)
            return '/10.15130/EAP' in parsed.path.upper()

        return False

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

            # If this is a DOI URL, resolve the redirect first
            if 'dx.doi.org' in url:
                logger.info("Resolving DOI redirect to EAP URL")
                url = await self._resolve_doi_redirect(url, timeout)
                logger.info(f"Resolved DOI to: {url}")

            # Create temp directory if downloading
            if download_mode == "download":
                temp_download_dir = Path(tempfile.mkdtemp(prefix='fichero_eap_import_'))
                logger.info(f"Created temp download directory: {temp_download_dir}")

            # Check if this is a IIIF manifest URL or archive-file page
            if 'manifest' in url:
                # Direct manifest URL
                self._report_progress(10, 100, "Fetching IIIF manifest")
                items = await self._fetch_iiif_manifest(url, timeout)
            elif '/archive-file/' in url:
                # Archive-file page URL - need to extract manifest URL
                self._report_progress(10, 100, "Extracting manifest URL from page")
                manifest_url = await self._extract_manifest_url_from_page(url, timeout)
                if manifest_url:
                    logger.info(f"Found manifest URL: {manifest_url}")
                    self._report_progress(20, 100, "Fetching IIIF manifest")
                    items = await self._fetch_iiif_manifest(manifest_url, timeout)
                else:
                    raise Exception(f"Could not find IIIF manifest URL on page: {url}")
            # Check if this is a collection or project page (hierarchical import)
            elif '/collection/' in url or '/project/' in url:
                # Ensure collection URLs have /search at the end for proper parsing
                if '/collection/' in url and not url.endswith('/search'):
                    url = url.rstrip('/') + '/search'
                    logger.info(f"Normalized collection URL to: {url}")

                self._report_progress(10, 100, "Discovering collection hierarchy")
                items = await self._fetch_hierarchical_collection(url, max_items, timeout)
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

    async def _resolve_doi_redirect(
        self,
        doi_url: str,
        timeout: int
    ) -> str:
        """
        Resolve DOI URL to actual EAP URL

        Args:
            doi_url: DOI URL (e.g., https://dx.doi.org/10.15130/EAP1550)
            timeout: Timeout in seconds

        Returns:
            Resolved EAP URL
        """
        try:
            timeout_obj = aiohttp.ClientTimeout(total=timeout)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }

            async with aiohttp.ClientSession(headers=headers, timeout=timeout_obj) as session:
                # Follow redirects and get final URL
                async with session.get(doi_url, allow_redirects=True) as response:
                    response.raise_for_status()
                    final_url = str(response.url)
                    logger.info(f"DOI resolved: {doi_url} -> {final_url}")
                    return final_url

        except Exception as e:
            logger.error(f"Failed to resolve DOI redirect: {e}")
            raise Exception(f"Could not resolve DOI URL: {e}")

    async def _extract_manifest_url_from_page(
        self,
        page_url: str,
        timeout: int
    ) -> Optional[str]:
        """
        Extract IIIF manifest URL from an archive-file page

        Looks for the IIIF logo link that points to the manifest.

        Args:
            page_url: Archive-file page URL (e.g., https://eap.bl.uk/archive-file/EAP640-1-1-1)
            timeout: Timeout in seconds

        Returns:
            Manifest URL if found, None otherwise
        """
        try:
            timeout_obj = aiohttp.ClientTimeout(total=timeout)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }

            async with aiohttp.ClientSession(headers=headers, timeout=timeout_obj) as session:
                # Fetch the page
                async with session.get(page_url) as response:
                    response.raise_for_status()
                    html = await response.text()

                # Parse HTML
                soup = BeautifulSoup(html, 'html.parser')

                # Look for IIIF manifest link
                # The IIIF logo is inside an <a> tag with href pointing to the manifest
                # Pattern: <a href="https://eap.bl.uk/archive-file/EAP640-1-1-1/manifest?manifest=..." class="draggable-manifest-link__content">
                manifest_link = soup.find('a', class_=re.compile(r'draggable-manifest-link|iiif-manifest'))

                if manifest_link and manifest_link.get('href'):
                    manifest_url = manifest_link['href']

                    # Make URL absolute if it's relative
                    if not manifest_url.startswith('http'):
                        manifest_url = urljoin(page_url, manifest_url)

                    logger.info(f"Found manifest URL: {manifest_url}")
                    return manifest_url

                # Fallback: Look for any link containing "/manifest"
                manifest_links = soup.find_all('a', href=re.compile(r'/manifest'))
                if manifest_links:
                    manifest_url = manifest_links[0]['href']

                    # Make URL absolute
                    if not manifest_url.startswith('http'):
                        manifest_url = urljoin(page_url, manifest_url)

                    logger.info(f"Found manifest URL (fallback): {manifest_url}")
                    return manifest_url

                # Last resort: Construct manifest URL from page URL
                # If page is https://eap.bl.uk/archive-file/EAP640-1-1-1
                # Then manifest is https://eap.bl.uk/archive-file/EAP640-1-1-1/manifest
                if '/archive-file/' in page_url:
                    base_url = page_url.rstrip('/')
                    manifest_url = f"{base_url}/manifest"
                    logger.info(f"Constructed manifest URL from page URL: {manifest_url}")
                    return manifest_url

                logger.warning(f"No manifest URL found on page: {page_url}")
                return None

        except Exception as e:
            logger.error(f"Failed to extract manifest URL from page: {e}")
            return None

    async def _fetch_hierarchical_collection(
        self,
        url: str,
        max_items: int,
        timeout: int
    ) -> List[Dict[str, Any]]:
        """
        Fetch hierarchical collection with all manifests

        This method discovers the full hierarchy:
        Collection/Project → Archive Files → Images (from manifests)

        Args:
            url: Collection or project URL
            max_items: Maximum archive files to process
            timeout: Timeout in seconds

        Returns:
            List of items with hierarchy (folders + images)
        """
        all_items = []

        try:
            logger.info(f"Fetching hierarchical collection from: {url}")

            # Step 1: Find all archive-file links in the collection/project
            archive_file_urls = await self._find_archive_files(url, max_items, timeout)

            if not archive_file_urls:
                logger.warning("No archive files found in collection")
                return all_items

            logger.info(f"Found {len(archive_file_urls)} archive files to process")
            self._report_progress(20, 100, f"Found {len(archive_file_urls)} archives")

            # Step 2: For each archive file, fetch its manifest and extract images
            for idx, archive_info in enumerate(archive_file_urls):
                if self.is_cancelled:
                    break

                archive_id = archive_info['id']
                archive_name = archive_info['name']
                manifest_url = archive_info['manifest_url']

                progress = 20 + int((idx / len(archive_file_urls)) * 70)
                self._report_progress(progress, 100, f"Processing {archive_name}")

                try:
                    # Fetch manifest for this archive
                    logger.info(f"Fetching manifest {idx+1}/{len(archive_file_urls)}: {archive_name}")
                    images = await self._fetch_iiif_manifest(manifest_url, timeout)

                    # Create folder item for this archive
                    folder_item = {
                        'title': archive_name,
                        'type': 'folder',
                        'archive_id': archive_id,
                        'manifest_url': manifest_url,
                        'relative_path': archive_name,  # For hierarchy
                        'is_folder': True
                    }
                    all_items.append(folder_item)

                    # Add all images from this archive with parent reference
                    for image in images:
                        image['parent_folder'] = archive_name  # Mark parent for hierarchy
                        image['archive_id'] = archive_id
                        all_items.append(image)

                    logger.info(f"Added {len(images)} images from {archive_name}")

                except Exception as e:
                    logger.error(f"Failed to fetch manifest for {archive_name}: {e}")
                    continue

            logger.info(f"Hierarchical fetch complete: {len(all_items)} total items")
            return all_items

        except Exception as e:
            logger.error(f"Failed to fetch hierarchical collection: {e}")
            raise

    async def _find_archive_files(
        self,
        url: str,
        max_items: int,
        timeout: int
    ) -> List[Dict[str, Any]]:
        """
        Find all archive-file links in a collection/project page

        Args:
            url: Collection or project URL
            max_items: Maximum archive files to find
            timeout: Timeout in seconds

        Returns:
            List of dictionaries with archive info (id, name, manifest_url)
        """
        archive_files = []

        try:
            timeout_obj = aiohttp.ClientTimeout(total=timeout)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }

            async with aiohttp.ClientSession(headers=headers, timeout=timeout_obj) as session:
                # Fetch the collection page
                async with session.get(url) as response:
                    response.raise_for_status()
                    html = await response.text()

                # Parse HTML
                soup = BeautifulSoup(html, 'html.parser')

                # Find all links to archive-file pages
                archive_links = soup.find_all('a', href=re.compile(r'/archive-file/'))

                for link in archive_links[:max_items]:
                    if self.is_cancelled:
                        break

                    try:
                        href = link.get('href')
                        if not href:
                            continue

                        # Extract archive ID from URL (e.g., /archive-file/EAP1049-1-2-1)
                        match = re.search(r'/archive-file/(EAP[^/\?]+)', href)
                        if match:
                            archive_id = match.group(1)

                            # Get archive name from link text or use ID
                            archive_name = link.get_text(strip=True) or archive_id

                            # Construct manifest URL
                            manifest_url = f"https://eap.bl.uk/archive-file/{archive_id}/manifest"

                            archive_files.append({
                                'id': archive_id,
                                'name': archive_name,
                                'manifest_url': manifest_url
                            })

                            logger.debug(f"Found archive: {archive_id} - {archive_name}")

                    except Exception as e:
                        logger.warning(f"Failed to parse archive link: {e}")
                        continue

                # Remove duplicates (same archive ID)
                seen_ids = set()
                unique_archives = []
                for archive in archive_files:
                    if archive['id'] not in seen_ids:
                        seen_ids.add(archive['id'])
                        unique_archives.append(archive)

                return unique_archives

        except Exception as e:
            logger.error(f"Failed to find archive files: {e}")
            raise

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

                # Extract collection metadata from manifest
                raw_label = manifest.get('label', 'EAP Collection')

                # Handle label - could be string or object
                if isinstance(raw_label, dict):
                    # IIIF v3 style: {"en": ["Label"]} or {"@value": "Label"}
                    collection_label = raw_label.get('en', [raw_label.get('@value', 'EAP Collection')])[0] if isinstance(raw_label.get('en'), list) else raw_label.get('en', raw_label.get('@value', 'EAP Collection'))
                else:
                    collection_label = str(raw_label) if raw_label else 'EAP Collection'

                # If label is just a number or very short, try to get a better name from metadata
                if collection_label.isdigit() or len(collection_label) < 3:
                    # Look for title or description in metadata
                    for meta in manifest.get('metadata', []):
                        if isinstance(meta, dict):
                            label_key = meta.get('label', '').lower()
                            if 'title' in label_key or 'reference' in label_key:
                                value = meta.get('value', '')
                                if value and len(str(value)) > 3:
                                    collection_label = str(value)
                                    break

                collection_id = manifest.get('@id', manifest_url)
                manifest_metadata = manifest.get('metadata', [])

                # Extract additional manifest-level metadata
                description = manifest.get('description', '')
                attribution = manifest.get('attribution', '')
                license_url = manifest.get('license', '')
                logo = manifest.get('logo', '')
                thumbnail = manifest.get('thumbnail', '')

                # Build comprehensive metadata dictionary
                folder_metadata = {
                    'manifest_label': collection_label,
                    'manifest_id': collection_id,
                    'manifest_url': manifest_url,
                    'description': description,
                    'attribution': attribution,
                    'license': license_url,
                    'logo': logo,
                    'thumbnail': thumbnail,
                    'iiif_metadata': manifest_metadata,  # Original IIIF metadata array
                }

                logger.info(f"Processing IIIF manifest: {collection_label}")

                # Extract images from canvases
                sequences = manifest.get('sequences', [])
                if not sequences:
                    raise Exception("No sequences found in IIIF manifest")

                canvases = sequences[0].get('canvases', [])
                logger.info(f"Found {len(canvases)} canvases in manifest")

                # Check for structures/ranges for hierarchical organization
                structures = manifest.get('structures', [])
                ranges = manifest.get('ranges', [])

                # Build folder structure from ranges if available
                folder_structure = {}
                canvas_to_folder = {}  # Map canvas ID to folder path

                if structures or ranges:
                    logger.info(f"Found {len(structures)} structures and {len(ranges)} ranges - building hierarchy")
                    # TODO: Parse structures/ranges to build folder hierarchy
                    # For now, just note that structure exists
                else:
                    # No structure - check if we should auto-group by page numbers
                    # Group canvases into folders of ~100 items each for large collections
                    if len(canvases) > 100:
                        logger.info(f"Large collection ({len(canvases)} canvases) - will auto-group into folders")
                        folder_structure = self._auto_group_canvases(canvases, collection_label)
                        for idx, canvas in enumerate(canvases):
                            folder_num = (idx // 100) + 1
                            folder_name = f"{collection_label} - Part {folder_num}"
                            canvas_to_folder[canvas.get('@id')] = folder_name

                # Only create sub-folders if we have a large collection (>100 items)
                # Don't create a redundant root folder - the collection itself serves that purpose
                if folder_structure:
                    logger.info(f"Creating {len(folder_structure)} sub-folders for large collection")
                    for folder_name, folder_info in folder_structure.items():
                        # Build folder metadata dict with ALL manifest fields at top level (like items)
                        sub_folder_metadata = {
                            'manifest_url': manifest_url,
                            'page_range': folder_info.get('page_range', ''),
                        }
                        # Merge ALL manifest-level metadata fields directly into folder metadata
                        for key, value in folder_metadata.items():
                            if key not in sub_folder_metadata:
                                sub_folder_metadata[key] = value

                        sub_folder = {
                            'title': folder_name,
                            'type': 'folder',
                            'is_folder': True,
                            'parent_folder': None,  # At collection root level
                            'relative_path': folder_name,
                            'metadata': sub_folder_metadata  # Flat metadata structure like items
                        }
                        items.append(sub_folder)

                for idx, canvas in enumerate(canvases):
                    if self.is_cancelled:
                        break

                    try:
                        # Track manifest position for proper ordering (idx is 0-based)
                        manifest_position = idx

                        # Extract canvas label/title
                        raw_canvas_label = canvas.get('label', f'Image_{idx+1}')

                        # Handle label - could be string, number, or object
                        if isinstance(raw_canvas_label, dict):
                            # IIIF v3 style
                            canvas_label = raw_canvas_label.get('en', [raw_canvas_label.get('@value', f'Image_{idx+1}')])[0] if isinstance(raw_canvas_label.get('en'), list) else raw_canvas_label.get('en', raw_canvas_label.get('@value', f'Image_{idx+1}'))
                        else:
                            canvas_label = str(raw_canvas_label) if raw_canvas_label else f'Image_{idx+1}'

                        # If label is empty, just a number, or very short, try to build a better name
                        if not canvas_label or canvas_label.isdigit() or len(canvas_label) < 2:
                            # Try to find a meaningful name from canvas metadata
                            canvas_meta = canvas.get('metadata', [])
                            for meta in canvas_meta:
                                if isinstance(meta, dict):
                                    meta_label = meta.get('label', '').lower()
                                    if 'folio' in meta_label or 'page' in meta_label or 'reference' in meta_label:
                                        value = meta.get('value', '')
                                        if value:
                                            canvas_label = f"{collection_label}_{value}"
                                            break

                            # Still no good name? Use collection + index
                            if not canvas_label or canvas_label.isdigit() or len(canvas_label) < 2:
                                canvas_label = f"{collection_label}_p{idx+1:04d}"

                        # Extract images from canvas
                        canvas_images = canvas.get('images', [])
                        for img_idx, image_obj in enumerate(canvas_images):
                            resource = image_obj.get('resource', {})
                            image_url = resource.get('@id')

                            if image_url:
                                # Extract canvas-level metadata
                                canvas_width = canvas.get('width')
                                canvas_height = canvas.get('height')
                                canvas_metadata = canvas.get('metadata', [])

                                # Determine parent folder - use sub-folder name if we're grouping, otherwise None (at collection root)
                                canvas_id = canvas.get('@id')
                                parent_folder = canvas_to_folder.get(canvas_id)  # None if not grouped

                                items.append({
                                    'title': f"{canvas_label}_{img_idx+1}" if img_idx > 0 else canvas_label,
                                    'url': image_url,
                                    'image_url': image_url,
                                    'type': 'iiif_image',
                                    'parent_folder': parent_folder,  # Link to parent folder (possibly sub-folder)
                                    'manifest_position': manifest_position,  # Original order in manifest
                                    'canvas_id': canvas_id,
                                    'canvas_label': canvas_label,
                                    'canvas_width': canvas_width,
                                    'canvas_height': canvas_height,
                                    'canvas_metadata': canvas_metadata,
                                    'collection_label': collection_label,
                                    'manifest_url': manifest_url,
                                    'manifest_metadata': manifest_metadata,
                                    'attribution': attribution,
                                    'license': license_url
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

    def _auto_group_canvases(self, canvases: list, collection_label: str, items_per_folder: int = 100) -> dict:
        """Auto-group canvases into folders for large collections

        Args:
            canvases: List of canvas objects from manifest
            collection_label: Base label for the collection
            items_per_folder: Number of items to put in each folder

        Returns:
            Dictionary of folder_name -> {page_range, start_idx, end_idx}
        """
        total = len(canvases)
        folder_structure = {}

        for i in range(0, total, items_per_folder):
            folder_num = (i // items_per_folder) + 1
            start_page = i + 1
            end_page = min(i + items_per_folder, total)

            folder_name = f"{collection_label} - Part {folder_num}"
            folder_structure[folder_name] = {
                'page_range': f"Pages {start_page}-{end_page}",
                'start_idx': i,
                'end_idx': end_page
            }

        logger.info(f"Created {len(folder_structure)} auto-grouped folders for {total} canvases")
        return folder_structure

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

        Handles both flat and hierarchical structures.
        For hierarchical imports, creates folders and links files with parent_id relationships.

        Args:
            items: List of item dictionaries (may include folders)
            collection_name: Collection name
            collection_description: Collection description

        Returns:
            ImportResult with import statistics
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

            # Separate folders and files
            folders = [item for item in items if item.get('type') == 'folder']
            files = [item for item in items if item.get('type') != 'folder']

            # Track folder_name → item_id mapping for parent relationships
            folder_id_map = {}

            added_count = 0
            skipped_count = 0
            error_count = 0

            # First pass: Create all folder items
            for folder in folders:
                if self.is_cancelled:
                    break

                try:
                    folder_name = folder['title']
                    relative_path = folder.get('relative_path', folder_name)

                    # Create folder item in collection with ALL metadata (flat structure like items)
                    folder_metadata = {
                        'relative_path': relative_path,
                        'type': 'folder'
                    }

                    # Add ALL metadata from the folder's metadata field (now flat, like items)
                    if 'metadata' in folder and isinstance(folder['metadata'], dict):
                        # Merge all metadata fields directly (no nesting)
                        for key, value in folder['metadata'].items():
                            if key not in folder_metadata:
                                folder_metadata[key] = value

                    folder_id = await self.library_manager.add_item_to_collection(
                        collection_id=collection_id,
                        item_type="folder",
                        source="",  # Folders don't have a source path
                        name=folder_name,
                        operation="link",
                        metadata=folder_metadata,
                        parent_id=None  # Folders are at root level
                    )

                    if folder_id:
                        folder_id_map[folder_name] = folder_id
                        added_count += 1
                        logger.info(f"Created folder: {folder_name} (ID: {folder_id})")
                    else:
                        error_count += 1
                        logger.error(f"Failed to create folder: {folder_name}")

                except Exception as e:
                    logger.error(f"Failed to create folder {folder.get('title')}: {e}")
                    error_count += 1
                    continue

            # Second pass: Add files with parent_id references
            for idx, item in enumerate(files):
                if self.is_cancelled:
                    break

                try:
                    progress = 50 + int((idx / len(files)) * 50)
                    self._report_progress(progress, 100, f"Linking {item['title']}")

                    # Prefer image_url (direct image) over url (page URL)
                    item_url = item.get('image_url') or item.get('url')
                    if not item_url:
                        logger.warning(f"No URL found for item: {item.get('title')}")
                        skipped_count += 1
                        continue

                    # Determine parent_id if this file belongs to a folder
                    parent_id = None
                    if 'parent_folder' in item:
                        parent_folder_name = item['parent_folder']
                        parent_id = folder_id_map.get(parent_folder_name)
                        if not parent_id:
                            logger.warning(f"Parent folder '{parent_folder_name}' not found for {item['title']}")

                    # Create metadata for URL item
                    metadata = {
                        'title': item['title'],
                        'image_url': item.get('image_url'),
                        'page_url': item.get('url'),
                        'type': item.get('type', 'unknown'),
                        'source': 'British Library EAP',
                        'canvas_id': item.get('canvas_id'),
                        'collection_label': item.get('collection_label'),
                        'archive_id': item.get('archive_id'),
                        'manifest_position': item.get('manifest_position')  # Preserve manifest order
                    }

                    # Add URL item to collection with parent_id
                    item_id = await self.library_manager.add_item_to_collection(
                        collection_id=collection_id,
                        item_type="url",
                        source=item_url,
                        name=item['title'],
                        operation="link",
                        metadata=metadata,
                        parent_id=parent_id  # Link to parent folder if exists
                    )

                    if item_id:
                        added_count += 1
                        parent_info = f" (parent: {item.get('parent_folder')})" if parent_id else ""
                        logger.info(f"Linked: {item['title']}{parent_info} -> {item_url}")
                    else:
                        error_count += 1
                        logger.error(f"Failed to add item: {item['title']}")

                except Exception as e:
                    logger.error(f"Failed to link item {item.get('title')}: {e}")
                    error_count += 1
                    continue

            hierarchy_note = f" ({len(folders)} folders, {len(files)} files)" if folders else ""
            return ImportResult(
                success=True,
                collection_id=collection_id,
                collection_name=collection_name,
                files_imported=added_count,
                files_skipped=skipped_count,
                errors=error_count,
                metadata={'mode': 'link', 'note': f'Items stored as URL links{hierarchy_note} (no download)'}
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
                "eap.bl.uk",
                "dx.doi.org (EAP DOIs: 10.15130/EAP*)"
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
