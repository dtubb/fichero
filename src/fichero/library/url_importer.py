"""
Shared URL Import Logic

Used by both CLI and GUI to import content from URLs using the plugin system.
"""

import logging
from typing import Optional, Callable
from datetime import datetime

logger = logging.getLogger(__name__)


class URLImporter:
    """Handles URL imports using the plugin system - shared between CLI and GUI"""

    def __init__(self, library_manager):
        """
        Initialize URL importer

        Args:
            library_manager: LibraryManager instance
        """
        self.library_manager = library_manager
        self._progress_callback: Optional[Callable] = None

    def set_progress_callback(self, callback: Callable[[int, int, str], None]):
        """
        Set progress callback for tracking import progress

        Args:
            callback: Function(current, total, message) called during import
        """
        self._progress_callback = callback

    async def import_from_url(
        self,
        url: str,
        collection_id: Optional[str] = None,
        collection_name: Optional[str] = None,
        description: Optional[str] = None,
        timeout: int = 600,
        max_items: int = 1000,
        download_mode: Optional[str] = None,
        collection_type: str = "local",
        source_path: Optional[str] = None,
        use_tiled_download: bool = False
    ) -> dict:
        """
        Import content from URL using plugin system

        Args:
            url: URL to import from
            collection_id: Optional ID of existing collection to add items to (not yet implemented - will create new collection)
            collection_name: Optional collection name (auto-generated if None)
            description: Optional collection description
            timeout: Download timeout in seconds
            max_items: Maximum items to import
            download_mode: Download mode for EAP plugin ('link' or 'download')
            collection_type: Collection type ('local' or 'external')
            source_path: Source path for external collections
            use_tiled_download: Enable IIIF tiled download for full-resolution images (EAP plugin only)

        Returns:
            dict with keys:
                - success: bool
                - collection_id: str or None
                - collection_name: str
                - files_imported: int
                - files_skipped: int
                - errors: int
                - error_message: str or None
                - metadata: dict
        """
        # TODO: Implement collection_id support to add items to existing collection
        # For now, we always create a new collection regardless of collection_id
        if collection_id:
            logger.warning(f"collection_id parameter not yet supported - will create new collection instead")
        try:
            # Import plugin system
            from fichero.library.import_plugins import PluginRegistry
            from fichero.library.import_plugins.zip_plugin import ZipImportPlugin
            from fichero.library.import_plugins.box_plugin import BoxImportPlugin
            from fichero.library.import_plugins.eap_plugin import EAPImportPlugin

            # Create registry and register all plugins
            registry = PluginRegistry()
            registry.register(ZipImportPlugin(self.library_manager))
            registry.register(BoxImportPlugin(self.library_manager))
            registry.register(EAPImportPlugin(self.library_manager))

            # Find appropriate plugin for URL
            plugin = registry.find_plugin_for_url(url)

            if not plugin:
                logger.error(f"No plugin found to handle URL: {url}")
                return {
                    'success': False,
                    'collection_id': None,
                    'collection_name': '',
                    'files_imported': 0,
                    'files_skipped': 0,
                    'errors': 1,
                    'error_message': f"No plugin found to handle URL: {url}",
                    'metadata': {}
                }

            # Generate collection name if not provided
            if not collection_name:
                url_parts = url.split('/')
                url_identifier = url_parts[-1] or url_parts[-2] if len(url_parts) > 1 else "Import"
                collection_name = f"{url_identifier} {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            # Set progress callback if available
            if self._progress_callback:
                plugin.set_progress_callback(self._progress_callback)

            plugin_info = plugin.get_plugin_info()
            logger.info(f"Using plugin {plugin_info['name']} v{plugin_info['version']} for URL: {url}")

            # Build kwargs based on plugin
            kwargs = {
                'timeout': timeout,
                'max_items': max_items,
                'collection_type': collection_type,
                'source_path': source_path
            }

            # Add EAP-specific options
            if "EAP" in plugin_info['name']:
                if download_mode:
                    kwargs['download_mode'] = download_mode
                if use_tiled_download:
                    kwargs['use_tiled_download'] = use_tiled_download

            # Perform import
            result = await plugin.download_and_import(
                url=url,
                collection_name=collection_name,
                collection_description=description or f"Imported from {url}",
                **kwargs
            )

            # Convert result to dict format
            return {
                'success': result.success,
                'collection_id': result.collection_id,
                'collection_name': result.collection_name,
                'files_imported': result.files_imported,
                'files_skipped': result.files_skipped,
                'errors': result.errors,
                'error_message': result.error_message,
                'metadata': result.metadata or {}
            }

        except Exception as e:
            logger.error(f"Failed to import from URL {url}: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'collection_id': None,
                'collection_name': '',
                'files_imported': 0,
                'files_skipped': 0,
                'errors': 1,
                'error_message': str(e),
                'metadata': {}
            }

    def list_supported_plugins(self) -> list:
        """
        Get list of all available import plugins

        Returns:
            List of dicts with plugin info (name, version, description, domains)
        """
        try:
            from fichero.library.import_plugins import PluginRegistry
            from fichero.library.import_plugins.zip_plugin import ZipImportPlugin
            from fichero.library.import_plugins.box_plugin import BoxImportPlugin
            from fichero.library.import_plugins.eap_plugin import EAPImportPlugin

            # Create registry and register all plugins
            registry = PluginRegistry()
            registry.register(ZipImportPlugin(self.library_manager))
            registry.register(BoxImportPlugin(self.library_manager))
            registry.register(EAPImportPlugin(self.library_manager))

            return registry.list_plugins()

        except Exception as e:
            logger.error(f"Failed to list plugins: {e}")
            return []
