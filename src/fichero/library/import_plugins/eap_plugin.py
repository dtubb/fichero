"""
British Library EAP (Endangered Archives Programme) Import Plugin

Downloads or links to files from British Library EAP project pages.
Supports both downloading files and creating direct links to resources.
"""

import logging
import re
import tempfile
import shutil
import io
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
        collection_type: str = "local",  # "local" or "external"
        source_path: Optional[str] = None,  # Required for external collections
        use_tiled_download: bool = False,  # Enable IIIF tiled download for full resolution
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
            collection_type: "local" or "external" collection type
            source_path: Required for external collections
            use_tiled_download: Enable IIIF tiled download for true full-resolution images (slower, but highest quality)
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
                # Append /search to both collection and project URLs
                if not url.endswith('/search'):
                    url = url.rstrip('/') + '/search'
                    logger.info(f"Normalized URL to: {url}")

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

            # Separate folders and files before applying limit
            # Folders are metadata-only and shouldn't count against max_items
            folders = [item for item in items if item.get('type') == 'folder']
            files = [item for item in items if item.get('type') != 'folder']

            # Limit ONLY files to max_items (folders are needed for hierarchy)
            if len(files) > max_items:
                logger.info(f"Found {len(files)} files and {len(folders)} folders in EAP project, limiting files to {max_items}")
                files = files[:max_items]
            else:
                logger.info(f"Found {len(files)} files and {len(folders)} folders in EAP project")

            # Recombine folders + limited files
            items = folders + files

            self._report_progress(30, 100, f"Found {len(items)} items with {len(folders)} folder")

            # Process items based on mode
            if download_mode == "download":
                files_processed, folder_metadata_map, file_metadata_map = await self._download_eap_files(
                    items,
                    temp_download_dir,
                    timeout,
                    use_tiled_download
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

                # Import downloaded files with metadata maps
                result = await self._import_downloaded_files(
                    temp_download_dir,
                    collection_name,
                    collection_description,
                    collection_type,
                    source_path,
                    folder_metadata_map,
                    file_metadata_map
                )
            else:
                # Link mode: create metadata files with URLs
                self._report_progress(50, 100, "Creating link metadata")
                result = await self._import_linked_items(
                    items,
                    collection_name,
                    collection_description,
                    collection_type,
                    source_path
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

    async def _extract_collection_metadata(
        self,
        url: str,
        timeout: int
    ) -> Dict[str, Any]:
        """
        Extract metadata from EAP collection/project page

        Extracts title, description, and other metadata from the collection page
        to provide better naming and context for imported items.

        Args:
            url: Collection or project URL
            timeout: Timeout in seconds

        Returns:
            Dictionary with collection metadata
        """
        metadata = {
            'collection_title': None,
            'collection_description': None,
            'project_id': None,
            'reference': None,
            'date_range': None,
            'extent': None,
            'language': None,
            'subject': None,
            'eap_url': url
        }

        try:
            timeout_obj = aiohttp.ClientTimeout(total=timeout)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }

            async with aiohttp.ClientSession(headers=headers, timeout=timeout_obj) as session:
                async with session.get(url) as response:
                    response.raise_for_status()
                    html = await response.text()

                soup = BeautifulSoup(html, 'html.parser')

                # Extract title (usually in h1 or title tag)
                title_elem = soup.find('h1')
                if title_elem:
                    metadata['collection_title'] = title_elem.get_text(strip=True)

                # Try meta description
                meta_desc = soup.find('meta', attrs={'name': 'description'})
                if meta_desc:
                    metadata['collection_description'] = meta_desc.get('content', '').strip()

                # Look for metadata table/dl elements (common in EAP pages)
                # EAP often uses <dl> or table elements for metadata
                dt_elements = soup.find_all('dt')
                for dt in dt_elements:
                    label = dt.get_text(strip=True).lower()
                    dd = dt.find_next_sibling('dd')
                    if dd:
                        value = dd.get_text(strip=True)

                        if 'reference' in label or 'identifier' in label:
                            metadata['reference'] = value
                        elif 'date' in label:
                            metadata['date_range'] = value
                        elif 'extent' in label or 'size' in label:
                            metadata['extent'] = value
                        elif 'language' in label:
                            metadata['language'] = value
                        elif 'subject' in label:
                            metadata['subject'] = value
                        elif 'description' in label and not metadata['collection_description']:
                            metadata['collection_description'] = value
                        elif 'project' in label:
                            metadata['project_id'] = value

                # Extract project/collection ID from URL as fallback
                if not metadata['reference']:
                    if '/collection/' in url:
                        match = re.search(r'/collection/(EAP[^/\?]+)', url)
                        if match:
                            metadata['reference'] = match.group(1)
                    elif '/project/' in url:
                        match = re.search(r'/project/(EAP[^/\?]+)', url)
                        if match:
                            metadata['reference'] = match.group(1)
                            metadata['project_id'] = match.group(1)

                logger.info(f"Extracted collection metadata: {metadata.get('collection_title', 'Unknown')}")

        except Exception as e:
            logger.warning(f"Failed to extract collection metadata: {e}")

        return metadata

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

            # Step 0: Extract collection metadata from the page
            collection_metadata = await self._extract_collection_metadata(url, timeout)

            # Log suggested collection name based on metadata
            if collection_metadata.get('collection_title'):
                logger.info(f"📋 EAP Collection: {collection_metadata['collection_title']}")
                if collection_metadata.get('reference'):
                    logger.info(f"📋 Reference: {collection_metadata['reference']}")
                if collection_metadata.get('collection_description'):
                    logger.info(f"📋 Description: {collection_metadata['collection_description'][:100]}...")

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

                    # Use manifest label as folder name if available and better than link text
                    folder_title = archive_name
                    if images and len(images) > 0:
                        # Look for folder items or use collection_label from first image
                        first_item = images[0]
                        if first_item.get('collection_label') and first_item['collection_label'] != archive_id:
                            folder_title = first_item['collection_label']
                            logger.debug(f"Using manifest label for folder: {folder_title}")

                    # Create folder item for this archive with EAP collection metadata
                    # Also include manifest-level IIIF metadata from the first image
                    folder_metadata = {
                        'eap_collection_title': collection_metadata.get('collection_title'),
                        'eap_collection_description': collection_metadata.get('collection_description'),
                        'eap_project_id': collection_metadata.get('project_id'),
                        'eap_reference': collection_metadata.get('reference'),
                        'eap_date_range': collection_metadata.get('date_range'),
                        'eap_language': collection_metadata.get('language'),
                        'eap_subject': collection_metadata.get('subject'),
                        'eap_url': collection_metadata.get('eap_url'),
                    }

                    # Add manifest-level metadata from first image if available
                    if images and len(images) > 0:
                        first_image_meta = images[0].get('metadata', {})
                        if first_image_meta:
                            # Include manifest-level fields (not canvas-specific)
                            folder_metadata.update({
                                'manifest_url': first_image_meta.get('manifest_url'),
                                'iiif_metadata': first_image_meta.get('iiif_metadata'),
                                'manifest_metadata': first_image_meta.get('manifest_metadata'),
                                'collection_label': first_image_meta.get('collection_label'),
                                'attribution': first_image_meta.get('attribution'),
                                'license': first_image_meta.get('license'),
                                'description': first_image_meta.get('description'),
                            })

                    folder_item = {
                        'title': folder_title,
                        'type': 'folder',
                        'archive_id': archive_id,
                        'manifest_url': manifest_url,
                        'relative_path': folder_title,  # For hierarchy
                        'is_folder': True,
                        'metadata': folder_metadata
                    }
                    all_items.append(folder_item)

                    # Add all images from this archive with parent reference and EAP metadata
                    for image in images:
                        image['parent_folder'] = folder_title  # Mark parent for hierarchy
                        image['archive_id'] = archive_id

                        # Add EAP collection metadata to each image
                        if 'metadata' not in image:
                            image['metadata'] = {}
                        image['metadata'].update({
                            'eap_collection_title': collection_metadata.get('collection_title'),
                            'eap_collection_description': collection_metadata.get('collection_description'),
                            'eap_project_id': collection_metadata.get('project_id'),
                            'eap_reference': collection_metadata.get('reference'),
                            'eap_date_range': collection_metadata.get('date_range'),
                            'eap_language': collection_metadata.get('language'),
                            'eap_subject': collection_metadata.get('subject'),
                            'eap_url': collection_metadata.get('eap_url'),
                        })

                        all_items.append(image)

                    logger.info(f"Added {len(images)} images from {folder_title}")

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

        For project pages, this will first find collection links, then drill down
        to find archive files within each collection.

        Args:
            url: Collection or project URL
            max_items: Maximum archive files to find
            timeout: Timeout in seconds

        Returns:
            List of dictionaries with archive info (id, name, manifest_url)
        """
        archive_files = []

        try:
            # Extract collection/project ID from URL for filtering
            # Examples:
            # /collection/EAP1477-1-2 -> EAP1477-1-2
            # /project/EAP1477 -> EAP1477
            collection_id = None
            is_project_page = False

            if '/collection/' in url:
                match = re.search(r'/collection/(EAP[^/\?]+)', url)
                if match:
                    collection_id = match.group(1)
                    logger.info(f"Filtering archive files for collection: {collection_id}")
            elif '/project/' in url:
                match = re.search(r'/project/(EAP[^/\?]+)', url)
                if match:
                    collection_id = match.group(1)
                    is_project_page = True
                    logger.info(f"Filtering archive files for project: {collection_id}")

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

                            # Filter by collection/project ID if specified
                            # Archive IDs follow patterns like:
                            # - EAP1477-1-1-1, EAP1477-1-1-2 for collection EAP1477-1-1
                            # - EAP1477-1-2-1, EAP1477-1-2-2 for collection EAP1477-1-2
                            # - EAP1477-1-1, EAP1477-1-2 for project EAP1477
                            if collection_id:
                                # Check if archive ID starts with collection ID
                                if not archive_id.startswith(collection_id):
                                    logger.debug(f"Skipping archive {archive_id} (doesn't match {collection_id})")
                                    continue

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

                # Log if no archive files found (shouldn't happen on search pages)
                if not archive_files:
                    logger.warning(f"No archive files found on page: {url}")
                    # Log page structure for debugging
                    all_links = soup.find_all('a', href=True)
                    logger.info(f"Total links on page: {len(all_links)}")
                    # Sample first 10 archive-related links
                    archive_related = [l for l in all_links if 'archive' in l.get('href', '').lower()][:10]
                    if archive_related:
                        logger.info(f"Found {len(archive_related)} archive-related links (sample):")
                        for i, link in enumerate(archive_related):
                            href = link.get('href', '')
                            text = link.get_text(strip=True)[:50]
                            logger.debug(f"  {i+1}. {href} | Text: {text}")

                # Remove duplicates (same archive ID)
                seen_ids = set()
                unique_archives = []
                for archive in archive_files:
                    if archive['id'] not in seen_ids:
                        seen_ids.add(archive['id'])
                        unique_archives.append(archive)

                logger.info(f"Total archive files found: {len(unique_archives)}")
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

                # Extract extended IIIF fields
                viewing_hint = manifest.get('viewingHint', '')
                viewing_direction = manifest.get('viewingDirection', '')
                nav_date = manifest.get('navDate', '')
                related = manifest.get('related', '')
                rendering = manifest.get('rendering', [])
                see_also = manifest.get('seeAlso', [])
                within = manifest.get('within', '')
                service = manifest.get('service', '')

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
                    'viewing_hint': viewing_hint,
                    'viewing_direction': viewing_direction,
                    'nav_date': nav_date,
                    'related': related,
                    'rendering': rendering,
                    'see_also': see_also,
                    'within': within,
                    'service': service,
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
                    logger.info(f"Found {len(structures)} structures and {len(ranges)} ranges - parsing hierarchy")
                    # Parse IIIF structures/ranges to extract folder hierarchy
                    folder_structure, canvas_to_folder = self._parse_iiif_ranges(
                        structures or ranges,
                        collection_label
                    )
                    logger.info(f"Parsed {len(folder_structure)} folders from manifest structure")

                # Create folders if we have a folder structure from the manifest
                if folder_structure:
                    logger.info(f"Creating {len(folder_structure)} folders from manifest structure")
                    for folder_path, folder_info in folder_structure.items():
                        # Extract just the folder label (last part of path) for the title
                        folder_label = folder_info.get('label', folder_path.split('/')[-1])

                        # Build folder metadata dict with ALL manifest and IIIF fields
                        sub_folder_metadata = {
                            # Range-specific metadata
                            'range_id': folder_info.get('range_id', ''),
                            'range_description': folder_info.get('description', ''),
                            'canvas_count': folder_info.get('canvas_count', 0),
                            'page_range': folder_info.get('page_range', ''),
                            # Manifest-level metadata (same as items get)
                            'manifest_label': collection_label,
                            'manifest_id': collection_id,
                            'manifest_url': manifest_url,
                            'manifest_metadata': manifest_metadata,  # Original IIIF metadata array
                            'description': description,
                            'attribution': attribution,
                            'license': license_url,
                            'logo': logo,
                            'thumbnail': thumbnail,
                            'viewing_hint': viewing_hint,
                            'viewing_direction': viewing_direction,
                            'nav_date': nav_date,
                            'related': related,
                            'rendering': rendering,
                            'see_also': see_also,
                            'within': within,
                            'service': service,
                            'iiif_metadata': manifest_metadata,  # Alias for compatibility
                            'collection_label': collection_label,  # For consistency with items
                        }

                        sub_folder = {
                            'title': folder_label,
                            'type': 'folder',
                            'is_folder': True,
                            'parent_folder': folder_info.get('parent_path'),  # Nested hierarchy support
                            'relative_path': folder_path,  # Full path for reference
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
                        # Get canvas dimensions for full-resolution download
                        canvas_width = canvas.get('width')
                        canvas_height = canvas.get('height')

                        for img_idx, image_obj in enumerate(canvas_images):
                            resource = image_obj.get('resource', {})
                            # Get full-resolution IIIF URL using canvas dimensions
                            image_url = self._get_full_resolution_iiif_url(resource, canvas_width, canvas_height)

                            if image_url:
                                canvas_metadata = canvas.get('metadata', [])
                                canvas_thumbnail = canvas.get('thumbnail', '')
                                canvas_viewing_hint = canvas.get('viewingHint', '')
                                canvas_related = canvas.get('related', '')
                                canvas_rendering = canvas.get('rendering', [])
                                canvas_see_also = canvas.get('seeAlso', [])
                                canvas_service = canvas.get('service', '')
                                canvas_other_content = canvas.get('otherContent', [])

                                # Extract resource-level metadata
                                resource_format = resource.get('format', '')
                                resource_width = resource.get('width')
                                resource_height = resource.get('height')
                                resource_service = resource.get('service', '')

                                # Determine parent folder from manifest structure (ranges/structures)
                                canvas_id = canvas.get('@id')
                                parent_folder = canvas_to_folder.get(canvas_id)  # None if no structure in manifest

                                # Package all IIIF metadata into metadata dict
                                item_metadata = {
                                    # Canvas metadata
                                    'canvas_id': canvas_id,
                                    'canvas_label': canvas_label,
                                    'canvas_width': canvas_width,
                                    'canvas_height': canvas_height,
                                    'canvas_metadata': canvas_metadata,  # This has the ref field!
                                    'canvas_thumbnail': canvas_thumbnail,
                                    'canvas_viewing_hint': canvas_viewing_hint,
                                    'canvas_related': canvas_related,
                                    'canvas_rendering': canvas_rendering,
                                    'canvas_see_also': canvas_see_also,
                                    'canvas_service': canvas_service,
                                    'canvas_other_content': canvas_other_content,
                                    # Resource metadata
                                    'resource_format': resource_format,
                                    'resource_width': resource_width,
                                    'resource_height': resource_height,
                                    'resource_service': resource_service,
                                    # Manifest metadata
                                    'collection_label': collection_label,
                                    'manifest_url': manifest_url,
                                    'manifest_metadata': manifest_metadata,
                                    'iiif_metadata': manifest_metadata,  # Alias for compatibility
                                    'attribution': attribution,
                                    'license': license_url,
                                    'description': description,
                                    'logo': logo,
                                    'thumbnail': thumbnail,
                                    'viewing_hint': viewing_hint,
                                    'viewing_direction': viewing_direction,
                                    'nav_date': nav_date,
                                    'related': related,
                                    'rendering': rendering,
                                    'see_also': see_also,
                                    'within': within,
                                    'service': service,
                                }

                                items.append({
                                    'title': f"{canvas_label}_{img_idx+1}" if img_idx > 0 else canvas_label,
                                    'url': image_url,
                                    'image_url': image_url,
                                    'type': 'iiif_image',
                                    'parent_folder': parent_folder,  # Link to parent folder (possibly sub-folder)
                                    'manifest_position': manifest_position,  # Original order in manifest
                                    'metadata': item_metadata,  # All IIIF metadata packaged together
                                    # Also keep at top level for backward compatibility
                                    'canvas_metadata': canvas_metadata,
                                    'collection_label': collection_label,
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

    def _parse_iiif_ranges(
        self,
        ranges: list,
        collection_label: str,
        parent_path: str = None
    ) -> Tuple[dict, dict]:
        """
        Parse IIIF ranges/structures to extract folder hierarchy

        IIIF manifests can define hierarchical organization through ranges/structures.
        Each range represents a folder/section and can contain:
        - canvases (the actual images)
        - child ranges (sub-folders)

        Args:
            ranges: List of IIIF range objects from manifest
            collection_label: Base label for the collection
            parent_path: Parent folder path for nested ranges

        Returns:
            Tuple of (folder_structure dict, canvas_to_folder dict)
            - folder_structure: {folder_name: {metadata}}
            - canvas_to_folder: {canvas_id: folder_name}
        """
        folder_structure = {}
        canvas_to_folder = {}

        for range_obj in ranges:
            if not isinstance(range_obj, dict):
                continue

            try:
                # Extract range label (folder name)
                raw_label = range_obj.get('label', 'Untitled Section')

                # Handle label - could be string or object (IIIF v2 vs v3)
                if isinstance(raw_label, dict):
                    # IIIF v3 style: {"en": ["Label"]} or {"@value": "Label"}
                    if 'en' in raw_label:
                        folder_label = raw_label['en'][0] if isinstance(raw_label['en'], list) else raw_label['en']
                    elif '@value' in raw_label:
                        folder_label = raw_label['@value']
                    else:
                        folder_label = str(raw_label)
                else:
                    folder_label = str(raw_label) if raw_label else 'Untitled Section'

                # Build full folder path (parent/child)
                if parent_path:
                    folder_name = f"{parent_path}/{folder_label}"
                else:
                    folder_name = folder_label

                # Extract canvases that belong to this range
                range_canvases = range_obj.get('canvases', [])

                # Also check 'members' field (IIIF v3)
                members = range_obj.get('members', [])
                for member in members:
                    if isinstance(member, dict):
                        member_type = member.get('type', '').lower()
                        if member_type == 'canvas' or 'canvas' in member.get('@type', '').lower():
                            canvas_id = member.get('id') or member.get('@id')
                            if canvas_id:
                                range_canvases.append(canvas_id)

                # Map canvases to this folder
                for canvas_ref in range_canvases:
                    # Handle both string IDs and object references
                    canvas_id = canvas_ref if isinstance(canvas_ref, str) else canvas_ref.get('@id') or canvas_ref.get('id')
                    if canvas_id:
                        canvas_to_folder[canvas_id] = folder_name

                # Store folder metadata
                folder_structure[folder_name] = {
                    'label': folder_label,
                    'parent_path': parent_path,
                    'range_id': range_obj.get('@id') or range_obj.get('id'),
                    'canvas_count': len(range_canvases),
                    'description': range_obj.get('description', ''),
                }

                logger.debug(f"Parsed range: {folder_name} ({len(range_canvases)} canvases)")

                # Recursively parse child ranges (sub-folders)
                child_ranges = range_obj.get('ranges', [])
                if child_ranges:
                    # Child ranges might be references (strings) or embedded objects
                    # For now, we'll handle embedded objects
                    # TODO: Handle range references by looking them up in manifest
                    embedded_children = [r for r in child_ranges if isinstance(r, dict)]
                    if embedded_children:
                        child_folders, child_canvas_map = self._parse_iiif_ranges(
                            embedded_children,
                            collection_label,
                            parent_path=folder_name
                        )
                        folder_structure.update(child_folders)
                        canvas_to_folder.update(child_canvas_map)

            except Exception as e:
                logger.warning(f"Failed to parse range: {e}")
                continue

        return folder_structure, canvas_to_folder

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

    def _get_full_resolution_iiif_url(self, resource: dict, canvas_width: Optional[int] = None, canvas_height: Optional[int] = None, use_tiles: bool = False) -> Optional[str]:
        """
        Construct full-resolution IIIF Image API URL from resource data

        Args:
            resource: IIIF resource dict with @id and optional service
            canvas_width: Canvas width for full resolution (preferred)
            canvas_height: Canvas height for full resolution (preferred)
            use_tiles: If True, return tile info dict instead of single URL

        Returns:
            Full-resolution image URL, or tile info dict if use_tiles=True, or original @id if no IIIF service available
        """
        # Try to use IIIF Image API service for full resolution
        service = resource.get('service')
        if service and isinstance(service, dict):
            service_id = service.get('@id', '')

            if service_id:
                # Check for tile support
                tiles_config = service.get('tiles', [])
                if use_tiles and tiles_config and canvas_width and canvas_height:
                    # Return tile configuration for tiled download
                    tile_info = tiles_config[0] if tiles_config else {}
                    return {
                        'mode': 'tiles',
                        'service_id': service_id,
                        'canvas_width': canvas_width,
                        'canvas_height': canvas_height,
                        'tile_width': tile_info.get('width', 256),
                        'scale_factors': tile_info.get('scaleFactors', [1])
                    }

                # IIIF Image API URL pattern: {base}/{region}/{size}/{rotation}/{quality}.{format}
                # Use canvas dimensions if available (best resolution for British Library)
                # Note: British Library's IIIF server appears to have resolution limits and doesn't
                # provide the full canvas resolution (e.g., 2667x4000), but canvas dimensions give
                # better results than service dimensions or 'full' parameter
                if canvas_width and canvas_height:
                    full_res_url = f"{service_id}/full/{canvas_width},{canvas_height}/0/default.jpg"
                    logger.debug(f"Constructed IIIF URL with canvas dimensions {canvas_width}x{canvas_height}")
                else:
                    # Fall back to service dimensions
                    width = service.get('width')
                    height = service.get('height')
                    if width and height:
                        full_res_url = f"{service_id}/full/{width},{height}/0/default.jpg"
                        logger.debug(f"Constructed IIIF URL with service dimensions {width}x{height}")
                    else:
                        # Last resort: use 'full' parameter
                        full_res_url = f"{service_id}/full/full/0/default.jpg"
                        logger.debug(f"Constructed IIIF URL with 'full' parameter")
                return full_res_url

        # Fall back to original resource @id if no IIIF service available
        original_url = resource.get('@id')
        if original_url:
            logger.debug(f"No IIIF service found, using original URL: {original_url}")
        return original_url

    async def _download_and_stitch_tiles(self, tile_info: dict, session: aiohttp.ClientSession, output_path: Path) -> bool:
        """
        Download IIIF tiles and stitch them together into a full resolution image

        Args:
            tile_info: Dictionary with tile configuration
            session: aiohttp session for downloads
            output_path: Where to save the stitched image

        Returns:
            True if successful, False otherwise
        """
        try:
            from PIL import Image
            import math

            service_id = tile_info['service_id']
            canvas_width = tile_info['canvas_width']
            canvas_height = tile_info['canvas_height']
            tile_width = tile_info['tile_width']
            scale_factors = tile_info['scale_factors']

            # Use the highest scale factor (1 = full resolution, higher numbers = lower resolution)
            # For full resolution tiles, we want scale_factor = 1
            scale_factor = 1

            # Calculate number of tiles needed
            tiles_x = math.ceil(canvas_width / tile_width)
            tiles_y = math.ceil(canvas_height / tile_width)  # Tiles are square

            logger.info(f"Downloading {tiles_x}x{tiles_y} = {tiles_x * tiles_y} tiles at full resolution for {output_path.name}")

            # Create output image
            output_image = Image.new('RGB', (canvas_width, canvas_height))

            # Download and place each tile
            tiles_downloaded = 0
            for y in range(tiles_y):
                for x in range(tiles_x):
                    # Calculate tile region
                    tile_x = x * tile_width
                    tile_y = y * tile_width
                    tile_w = min(tile_width, canvas_width - tile_x)
                    tile_h = min(tile_width, canvas_height - tile_y)

                    # IIIF Image API: {server}/{region}/{size}/{rotation}/{quality}.{format}
                    # Region format: x,y,w,h
                    tile_url = f"{service_id}/{tile_x},{tile_y},{tile_w},{tile_h}/full/0/default.jpg"

                    # Download tile
                    try:
                        async with session.get(tile_url) as response:
                            if response.status == 200:
                                tile_data = await response.read()
                                tile_image = Image.open(io.BytesIO(tile_data))

                                # Paste tile into output image
                                output_image.paste(tile_image, (tile_x, tile_y))
                                tiles_downloaded += 1

                                if tiles_downloaded % 10 == 0:
                                    logger.debug(f"Downloaded {tiles_downloaded}/{tiles_x * tiles_y} tiles")
                            else:
                                logger.warning(f"Failed to download tile at {tile_x},{tile_y}: HTTP {response.status}")
                                return False
                    except Exception as e:
                        logger.error(f"Error downloading tile at {tile_x},{tile_y}: {e}")
                        return False

            # Save stitched image
            output_image.save(output_path, 'JPEG', quality=95)
            logger.info(f"Successfully stitched {tiles_downloaded} tiles into {output_path.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to download and stitch tiles: {e}")
            return False

    def _extract_ref_from_metadata(self, iiif_metadata: list) -> Optional[str]:
        """
        Extract reference field from IIIF manifest metadata array

        Args:
            iiif_metadata: IIIF metadata array (list of dicts with 'label' and 'value')

        Returns:
            Reference string if found, None otherwise
        """
        if not iiif_metadata or not isinstance(iiif_metadata, list):
            return None

        for meta in iiif_metadata:
            if not isinstance(meta, dict):
                continue

            # Get label - could be string or dict (IIIF v3)
            label = meta.get('label', '')
            if isinstance(label, dict):
                # IIIF v3 style: {"en": ["Ref"]} or {"@value": "Ref"}
                label = label.get('en', [label.get('@value', '')])[0] if isinstance(label.get('en'), list) else label.get('en', label.get('@value', ''))
            label = str(label).lower().strip()

            # Look for ref, reference, or identifier fields
            if any(keyword in label for keyword in ['ref', 'reference', 'identifier']):
                # Get value - could also be string or dict
                value = meta.get('value', '')
                if isinstance(value, dict):
                    value = value.get('en', [value.get('@value', '')])[0] if isinstance(value.get('en'), list) else value.get('en', value.get('@value', ''))
                value = str(value).strip()

                if value:
                    return value

        return None

    def _sanitize_ref_for_filename(self, ref: str) -> str:
        """
        Convert IIIF reference to safe filename/folder name

        Args:
            ref: Reference string (e.g., "EAP640/1/1")

        Returns:
            Safe filename (e.g., "EAP640-1-1")
        """
        # Replace forward slashes with hyphens
        safe_ref = ref.replace('/', '-')
        # Remove any other unsafe characters
        safe_ref = re.sub(r'[^\w\s-]', '', safe_ref)
        # Replace whitespace with underscores
        safe_ref = re.sub(r'\s+', '_', safe_ref)
        return safe_ref

    async def _download_eap_files(
        self,
        items: List[Dict[str, Any]],
        download_dir: Path,
        timeout: int,
        use_tiled_download: bool = False
    ) -> int:
        """
        Download files from EAP items preserving folder hierarchy

        Args:
            items: List of item dictionaries (includes folders and files)
            download_dir: Directory to download to
            timeout: Timeout in seconds
            use_tiled_download: If True, download IIIF tiles and stitch them for full resolution

        Returns:
            Tuple of (files_downloaded, folder_metadata_map, file_metadata_map)
        """
        files_downloaded = 0

        try:
            # Separate folders and files
            folders = [item for item in items if item.get('type') == 'folder']
            files = [item for item in items if item.get('type') != 'folder']

            # Create folder structure first and store metadata
            import json
            folder_paths = {}  # folder_name -> Path mapping
            folder_metadata_map = {}  # folder_name -> metadata mapping
            file_metadata_map = {}  # relative_path -> metadata mapping
            for folder in folders:
                folder_name = folder['title']
                folder_metadata = folder.get('metadata', {})

                # Try to extract ref from IIIF metadata for folder naming
                # The ref might be in iiif_metadata or manifest_metadata
                ref = None
                iiif_metadata = folder_metadata.get('iiif_metadata', [])
                if iiif_metadata:
                    ref = self._extract_ref_from_metadata(iiif_metadata)

                # Also try manifest_metadata if not found
                if not ref:
                    manifest_metadata = folder_metadata.get('manifest_metadata', [])
                    if manifest_metadata:
                        ref = self._extract_ref_from_metadata(manifest_metadata)

                # Use ref for folder name if available, otherwise use original name
                if ref:
                    folder_display_name = self._sanitize_ref_for_filename(ref)
                    logger.info(f"Using ref '{ref}' for folder name: {folder_display_name}")
                else:
                    folder_display_name = folder_name

                # Get relative path, replacing folder name with ref-based name if available
                relative_path = folder.get('relative_path', folder_display_name)
                if ref:
                    # Replace the last component of the path with the ref-based name
                    path_parts = relative_path.split('/')
                    path_parts[-1] = folder_display_name
                    relative_path = '/'.join(path_parts)

                # Create folder path (handle nested paths)
                folder_path = download_dir / relative_path
                folder_path.mkdir(parents=True, exist_ok=True)
                folder_paths[folder_name] = folder_path

                # Store folder metadata in map using the display name (ref-based or last part of path)
                # This matches what the import function will use to look it up
                folder_key = folder_path.name  # Use the actual folder name on disk
                folder_metadata_map[folder_key] = folder_metadata
                logger.info(f"Created folder: {relative_path}")

            timeout_obj = aiohttp.ClientTimeout(total=timeout)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }

            async with aiohttp.ClientSession(headers=headers, timeout=timeout_obj) as session:
                for idx, item in enumerate(files):
                    if self.is_cancelled:
                        logger.info("Download cancelled by user")
                        break

                    try:
                        # Report progress
                        progress = 30 + int((idx / len(files)) * 50)
                        self._report_progress(progress, 100, f"Downloading {item['title']}")

                        # Download image if available
                        download_url = item.get('image_url') or item.get('url')
                        if not download_url:
                            continue

                        # Determine download directory based on parent folder
                        parent_folder = item.get('parent_folder')
                        if parent_folder and parent_folder in folder_paths:
                            target_dir = folder_paths[parent_folder]
                        else:
                            target_dir = download_dir  # Root level if no parent

                        # Try to extract ref from metadata for filename
                        # Check both canvas_metadata and manifest iiif_metadata
                        ref = None

                        # First try canvas metadata
                        canvas_metadata = item.get('canvas_metadata', [])
                        if canvas_metadata:
                            ref = self._extract_ref_from_metadata(canvas_metadata)

                        # If not found, try manifest-level iiif_metadata from item's metadata dict
                        if not ref:
                            item_metadata = item.get('metadata', {})
                            iiif_metadata = item_metadata.get('iiif_metadata', [])
                            if iiif_metadata:
                                ref = self._extract_ref_from_metadata(iiif_metadata)

                        # Generate filename - use ref + position for uniqueness
                        manifest_pos = item.get('manifest_position', idx + 1)  # 1-indexed for filenames

                        if ref:
                            # Use ref-based filename + position for uniqueness
                            ref_base = self._sanitize_ref_for_filename(ref)
                            base_name = f"{ref_base}_{manifest_pos:04d}"
                            logger.debug(f"Using ref '{ref}' + position for filename: {base_name}")
                        else:
                            # Fall back to title + manifest position
                            title_safe = re.sub(r'[^\w\s-]', '', item['title'])[:100]
                            base_name = f"{title_safe}_{manifest_pos:04d}"

                        file_ext = self._guess_extension(download_url, item.get('type', 'unknown'))
                        filename = f"{base_name}{file_ext}"
                        file_path = target_dir / filename

                        logger.info(f"Downloading {idx+1}/{len(files)}: {item['title']} -> {file_path.relative_to(download_dir)}")

                        # Check if this is a IIIF image and we should use tiled download
                        download_success = False
                        if use_tiled_download and item.get('type') == 'iiif_image':
                            # Try to get canvas dimensions and resource info for tiled download
                            item_metadata = item.get('metadata', {})
                            canvas_width = item_metadata.get('canvas_width')
                            canvas_height = item_metadata.get('canvas_height')

                            # We need to reconstruct the resource object from metadata
                            # The service info should be in resource_service
                            resource_service = item_metadata.get('resource_service')

                            if canvas_width and canvas_height and resource_service:
                                # Reconstruct resource dict for tile URL generation
                                resource = {
                                    '@id': download_url,
                                    'service': resource_service
                                }

                                # Get tile info
                                tile_or_url = self._get_full_resolution_iiif_url(
                                    resource,
                                    canvas_width,
                                    canvas_height,
                                    use_tiles=True
                                )

                                # Check if we got tile info (dict) or URL (string)
                                if isinstance(tile_or_url, dict) and tile_or_url.get('mode') == 'tiles':
                                    logger.info(f"Using tiled download for {item['title']} at {canvas_width}x{canvas_height}")
                                    download_success = await self._download_and_stitch_tiles(
                                        tile_or_url,
                                        session,
                                        file_path
                                    )

                                    if not download_success:
                                        logger.warning(f"Tiled download failed, falling back to standard download")

                        # Standard download (either not IIIF, tiled disabled, or tiled failed)
                        if not download_success:
                            async with session.get(download_url) as response:
                                response.raise_for_status()

                                async with aiofiles.open(file_path, 'wb') as f:
                                    async for chunk in response.content.iter_chunked(8192):
                                        await f.write(chunk)

                        # Store file metadata with merged parent folder metadata
                        file_metadata = item.get('metadata', {}).copy()
                        parent_folder = item.get('parent_folder')
                        if parent_folder and parent_folder in folder_metadata_map:
                            parent_meta = folder_metadata_map[parent_folder]
                            file_metadata = {**parent_meta, **file_metadata}  # File-specific overrides parent

                        relative_file_path = file_path.relative_to(download_dir)
                        file_metadata_map[str(relative_file_path)] = file_metadata

                        files_downloaded += 1
                        logger.info(f"Downloaded: {relative_file_path}")

                    except Exception as e:
                        logger.error(f"Failed to download {item.get('title', 'unknown')}: {e}")
                        continue

        except Exception as e:
            logger.error(f"Download session failed: {e}")
            raise

        return files_downloaded, folder_metadata_map, file_metadata_map

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
        collection_description: str,
        collection_type: str = "local",
        source_path: Optional[str] = None,
        folder_metadata_map: Optional[dict] = None,
        file_metadata_map: Optional[dict] = None
    ) -> ImportResult:
        """
        Import downloaded files directly to collection's items folder

        Args:
            download_dir: Directory containing downloaded files (temp dir with hierarchy)
            collection_name: Collection name
            collection_description: Collection description
            collection_type: Collection type ("local" or "external")
            source_path: Source path for external collections

        Returns:
            ImportResult with statistics
        """
        try:
            import shutil

            # Determine collection source based on type
            if collection_type == "external":
                # For external collections, use the specified source path
                if not source_path:
                    raise Exception("source_path is required for external collections")
                collection_source = source_path
            else:
                # For local/internal collections, no source path
                collection_source = None

            # Create collection
            collection_id = await self.library_manager.add_collection(
                name=collection_name,
                collection_type=collection_type,
                source_path=collection_source,
                description=collection_description or "Imported from British Library EAP"
            )

            if not collection_id:
                raise Exception("Failed to create collection")

            # Get/create collection folder path
            collection = await self.library_manager.get_collection(collection_id)

            if collection_type == "external":
                # For external collections, use the source_path
                if not collection.source_path:
                    raise Exception("External collection missing source_path")
                collection_path = Path(collection.source_path)
            else:
                # For local/internal collections, use local_path
                if collection.local_path:
                    collection_path = Path(collection.local_path)
                else:
                    # Create the folder ourselves if not set
                    collection_path = self.library_manager.library_path / "collections" / str(collection_id)
                    collection_path.mkdir(parents=True, exist_ok=True)

                    # Update collection with local_path
                    collection.local_path = str(collection_path)
                    self.library_manager.storage.update_collection(collection)

            # Create items directory
            items_dir = collection_path / "items"
            items_dir.mkdir(parents=True, exist_ok=True)

            # First, discover all unique folder paths and create folder items
            folder_paths = set()
            for item_path in download_dir.rglob("*"):
                if item_path.is_file():
                    relative_path = item_path.relative_to(download_dir)
                    # Get all parent folders for this file
                    for parent in relative_path.parents:
                        if parent != Path('.'):
                            folder_paths.add(parent)

            # Sort folders by depth (shallowest first) to create parent folders before children
            sorted_folders = sorted(folder_paths, key=lambda p: len(p.parts))

            # Initialize metadata maps
            if folder_metadata_map is None:
                folder_metadata_map = {}
            if file_metadata_map is None:
                file_metadata_map = {}

            # Create folder items and track their IDs
            folder_id_map = {}  # Maps folder path to folder item ID
            for folder_path in sorted_folders:
                # Determine parent folder ID
                parent_id = None
                if folder_path.parent != Path('.'):
                    parent_id = folder_id_map.get(folder_path.parent)

                # Create physical folder
                physical_folder = items_dir / folder_path
                physical_folder.mkdir(parents=True, exist_ok=True)

                # Get folder metadata from map (passed from download function)
                folder_name = folder_path.name
                folder_metadata = folder_metadata_map.get(folder_name)
                if folder_metadata:
                    logger.debug(f"Using metadata from map for folder '{folder_name}': {len(folder_metadata)} keys")
                else:
                    logger.debug(f"No metadata in map for folder '{folder_name}'")

                # Create folder item in database with metadata
                # Use empty source for folders - they're container items, not filesystem references
                # The folder structure is maintained through parent_id relationships
                folder_item_id = await self.library_manager.add_item_to_collection(
                    collection_id=collection_id,
                    item_type='folder',
                    source="",  # Empty source = metadata-only folder (not recursive import)
                    name=folder_name,
                    operation='link',
                    parent_id=parent_id,
                    metadata=folder_metadata
                )
                folder_id_map[folder_path] = folder_item_id
                logger.info(f"Created folder item: {folder_path}")

            # Now copy files and add them to the database with proper parent_id
            files_imported = 0
            for item_path in download_dir.rglob("*"):
                if item_path.is_file():
                    # Calculate relative path from download_dir
                    relative_path = item_path.relative_to(download_dir)

                    # Destination path in items folder
                    dest_path = items_dir / relative_path

                    # Create parent directories if needed (should already exist from folder creation)
                    dest_path.parent.mkdir(parents=True, exist_ok=True)

                    # Copy file
                    shutil.copy2(item_path, dest_path)

                    # Get file metadata from map (passed from download function)
                    file_metadata = file_metadata_map.get(str(relative_path))
                    if file_metadata:
                        logger.debug(f"Using metadata from map for file '{relative_path}': {len(file_metadata)} keys")
                    else:
                        logger.debug(f"No metadata in map for file '{relative_path}'")

                    # Determine parent folder ID
                    parent_id = None
                    if relative_path.parent != Path('.'):
                        parent_id = folder_id_map.get(relative_path.parent)

                    # Add file item to database with parent_id and metadata
                    item_name = relative_path.name
                    await self.library_manager.add_item_to_collection(
                        collection_id=collection_id,
                        item_type='file',
                        source=str(dest_path),
                        name=item_name,
                        operation='link',  # File is already copied, just register it
                        parent_id=parent_id,
                        metadata=file_metadata
                    )

                    files_imported += 1
                    if files_imported % 10 == 0:
                        logger.info(f"Copied and registered {files_imported} files...")

            return ImportResult(
                success=True,
                collection_id=collection_id,
                collection_name=collection_name,
                files_imported=files_imported,
                files_skipped=0,
                errors=0
            )

        except Exception as e:
            logger.error(f"Failed to import downloaded files: {e}")
            raise

    async def _import_linked_items(
        self,
        items: List[Dict[str, Any]],
        collection_name: str,
        collection_description: str,
        collection_type: str = "local",
        source_path: Optional[str] = None
    ) -> ImportResult:
        """
        Import items as URL links (without downloading)

        Handles both flat and hierarchical structures.
        For hierarchical imports, creates folders and links files with parent_id relationships.

        Args:
            items: List of item dictionaries (may include folders)
            collection_name: Collection name
            collection_description: Collection description
            collection_type: Collection type ("local" or "external")
            source_path: Source path for external collections

        Returns:
            ImportResult with import statistics
        """
        try:
            # Determine collection source based on type
            if collection_type == "external":
                # For external collections, use the specified source path
                if not source_path:
                    raise Exception("source_path is required for external collections")
                collection_source = source_path
            else:
                # For local/internal collections, no source path
                collection_source = ""

            # Create collection (type determines where metadata is stored)
            collection_id = await self.library_manager.add_collection(
                name=collection_name,
                collection_type=collection_type,
                source_path=collection_source,
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

                    # Merge in all metadata from the item (including EAP collection metadata)
                    if 'metadata' in item and isinstance(item['metadata'], dict):
                        for key, value in item['metadata'].items():
                            if key not in metadata:  # Don't override existing fields
                                metadata[key] = value

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
                },
                {
                    "name": "use_tiled_download",
                    "type": "bool",
                    "default": False,
                    "description": "Enable IIIF tiled download for full-resolution images (slower, higher quality)"
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
