"""
Main Library Manager for Fichero

Orchestrates collection management, item operations, and processing integration.
"""

import logging
import shutil
import asyncio
from pathlib import Path
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime

try:
    from fichero.library.models import Collection, CollectionItem, ProcessingResult, ExternalPath
    from fichero.library.storage import LibraryStorage
    from fichero.library.import_export import CollectionExporter, CollectionImporter
    from fichero.library.url_downloader import URLDownloader
except ImportError:
    try:
        from .models import Collection, CollectionItem, ProcessingResult, ExternalPath
        from .storage import LibraryStorage
        from .import_export import CollectionExporter, CollectionImporter
        from .url_downloader import URLDownloader
    except ImportError:
        # Direct import for testing
        import models
        import storage
        import import_export
        import url_downloader
        Collection = models.Collection
        CollectionItem = models.CollectionItem
        ProcessingResult = models.ProcessingResult
        ExternalPath = models.ExternalPath
        LibraryStorage = storage.LibraryStorage
        CollectionExporter = import_export.CollectionExporter
        CollectionImporter = import_export.CollectionImporter
        URLDownloader = url_downloader.URLDownloader

logger = logging.getLogger(__name__)


class LibraryManager:
    """Main library management system for Fichero"""
    
    def __init__(self, app):
        """Initialize library manager with Toga app reference"""
        self.app = app
        
        # Get library path using centralized resolver (same logic for CLI, GUI, tests)
        from fichero.library.path_resolver import get_library_database_path
        db_path = get_library_database_path(app)
        
        # Ensure directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.storage = LibraryStorage(db_path)

        # Initialize import/export
        self.exporter = CollectionExporter(self.storage)
        self.importer = CollectionImporter(self.storage)

        # Initialize URL downloader with cache directory
        cache_root = db_path.parent / "cache"
        self.downloader = URLDownloader(cache_root)

        # Collection cache
        self._collections_cache: Optional[List[Collection]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._demo_setup_pending: bool = False

        logger.info(f"Library manager initialized successfully with database: {db_path}")
        
        # Auto-populate demo collections on first run
        self._demo_setup_pending = True  # Will be handled in get_all_collections
    
    # ===== COLLECTION MANAGEMENT =====
    
    async def add_collection(self, 
                           name: str,
                           collection_type: Literal["local", "external", "url", "hybrid"],
                           source_path: Optional[str] = None,
                           description: str = "",
                           metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Add a new collection to the library"""
        try:
            # Validate inputs
            if not name.strip():
                logger.error("Collection name cannot be empty")
                return None
            
            # Check for duplicate names
            existing = await self.get_collection_by_name(name)
            if existing:
                logger.error(f"Collection with name '{name}' already exists")
                return None
            
            # Create collection
            # Store description in metadata since Collection model doesn't have description field
            if metadata is None:
                metadata = {}
            if description:
                metadata['description'] = description
                
            collection = Collection(
                name=name.strip(),
                type=collection_type,
                source_path=source_path,
                metadata=metadata
            )
            
            # Handle different collection types
            if collection_type == "local" and source_path:
                # Copy to library directory
                local_path = await self._copy_to_library(collection, source_path)
                collection.local_path = str(local_path)
            elif collection_type == "external" and source_path:
                # Link to external location
                collection.source_path = source_path
            elif collection_type == "url" and source_path:
                # Store URL reference
                collection.source_path = source_path
                collection.metadata["url"] = source_path
            
            # Save to storage
            if self.storage.add_collection(collection):
                # Clear cache
                self._clear_cache()
                logger.info(f"Collection added: {name} ({collection_type})")
                return collection.id
            else:
                logger.error("Failed to save collection to storage")
                return None
                
        except Exception as e:
            logger.error(f"Failed to add collection: {e}")
            return None
    
    async def _copy_to_library(self, collection: Collection, source_path: str) -> Path:
        """Copy collection files to library directory"""
        try:
            source = Path(source_path)
            if not source.exists():
                raise FileNotFoundError(f"Source path does not exist: {source_path}")
            
            # Create library collection directory
            library_collection_path = self.app.paths.data / "library" / "collections" / collection.name
            library_collection_path.mkdir(parents=True, exist_ok=True)
            
            if source.is_file():
                # Copy single file
                shutil.copy2(source, library_collection_path / source.name)
            elif source.is_dir():
                # Copy directory contents
                shutil.copytree(source, library_collection_path, dirs_exist_ok=True)
            
            logger.debug(f"Collection copied to library: {library_collection_path}")
            return library_collection_path
            
        except Exception as e:
            logger.error(f"Failed to copy collection to library: {e}")
            raise
    
    async def get_collection(self, collection_id: str) -> Optional[Collection]:
        """Get a collection by ID"""
        return self.storage.get_collection(collection_id)
    
    async def get_collection_by_name(self, name: str) -> Optional[Collection]:
        """Get a collection by name"""
        collections = await self.get_all_collections()
        return next((c for c in collections if c.name == name), None)
    
    async def get_all_collections(self, force_refresh: bool = False, sort_by: str = "manual") -> List[Collection]:
        """Get all collections with caching and sorting

        Args:
            force_refresh: Force refresh from database
            sort_by: Sort mode - "manual", "name", "date_created", "date_updated", "type"
        """
        try:
            # Check for pending demo setup
            if self._demo_setup_pending:
                await self._ensure_demo_collections()
                self._demo_setup_pending = False
                force_refresh = True  # Force refresh after demo setup

            # Check cache (cache key includes sort mode)
            cache_key = f"{sort_by}"
            if (not force_refresh and
                self._collections_cache is not None and
                self._cache_timestamp and
                (datetime.now() - self._cache_timestamp).seconds < 30 and
                getattr(self, '_last_sort_mode', None) == sort_by):
                return self._collections_cache.copy()

            # Check for pending demo setup
            if self._demo_setup_pending:
                await self._ensure_demo_collections()
                self._demo_setup_pending = False
                # Force cache refresh after demo setup
                self._clear_cache()

            # Load from storage with sort mode
            collections = self.storage.get_all_collections(sort_by=sort_by)

            # Update cache
            self._collections_cache = collections
            self._cache_timestamp = datetime.now()
            self._last_sort_mode = sort_by

            return collections

        except Exception as e:
            logger.error(f"Failed to get all collections: {e}")
            return []
    
    async def update_collection(self, collection_id: str, **updates) -> bool:
        """Update collection properties"""
        try:
            collection = await self.get_collection(collection_id)
            if not collection:
                logger.error(f"Collection not found: {collection_id}")
                return False
            
            # Apply updates
            for key, value in updates.items():
                if hasattr(collection, key):
                    setattr(collection, key, value)
            
            collection.updated_at = datetime.now()
            
            # Save to storage
            if self.storage.update_collection(collection):
                self._clear_cache()
                logger.info(f"Collection updated: {collection.name}")
                return True
            else:
                logger.error("Failed to save collection updates")
                return False
                
        except Exception as e:
            logger.error(f"Failed to update collection: {e}")
            return False

    async def reorder_collection(self, collection_id: str, new_position: int) -> bool:
        """Move a collection to a new position in manual sort order

        Args:
            collection_id: ID of collection to move
            new_position: New position (1-based index)
        """
        try:
            # Get all collections in manual sort order
            collections = await self.get_all_collections(sort_by="manual")

            if new_position < 1 or new_position > len(collections):
                logger.error(f"Invalid position {new_position}, must be between 1 and {len(collections)}")
                return False

            # Find the collection to move
            collection_to_move = None
            current_index = None
            for i, col in enumerate(collections):
                if col.id == collection_id:
                    collection_to_move = col
                    current_index = i
                    break

            if not collection_to_move:
                logger.error(f"Collection {collection_id} not found")
                return False

            # Remove from current position
            collections.pop(current_index)

            # Insert at new position (convert from 1-based to 0-based)
            collections.insert(new_position - 1, collection_to_move)

            # Update sort_order for all collections
            for i, col in enumerate(collections):
                col.sort_order = i + 1  # 1-based sort order
                if not self.storage.update_collection(col):
                    logger.error(f"Failed to update sort order for {col.name}")
                    return False

            self._clear_cache()
            logger.info(f"Collection {collection_to_move.name} moved to position {new_position}")
            return True

        except Exception as e:
            logger.error(f"Failed to reorder collection: {e}")
            return False

    async def delete_collection(self, collection_id: str) -> bool:
        """Delete a collection and all its data"""
        try:
            collection = await self.get_collection(collection_id)
            if not collection:
                logger.error(f"Collection not found: {collection_id}")
                return False
            
            # Remove local files if it's a local collection
            if collection.type == "local" and collection.local_path:
                local_path = Path(collection.local_path)
                if local_path.exists():
                    try:
                        shutil.rmtree(local_path)
                        logger.debug(f"Removed local collection files: {local_path}")
                    except Exception as file_error:
                        logger.warning(f"Could not remove local files for collection {collection.name}: {file_error}")
                        # Continue with database deletion even if file removal fails

            # Remove from storage
            logger.debug(f"Attempting to delete collection {collection_id} from storage")
            if self.storage.delete_collection(collection_id):
                self._clear_cache()
                logger.info(f"Collection deleted: {collection.name}")
                return True
            else:
                logger.error(f"Failed to delete collection {collection_id} from storage - check storage.delete_collection method")
                return False
                
        except Exception as e:
            logger.error(f"Failed to delete collection: {e}")
            return False
    
    # ===== ITEM MANAGEMENT =====
    
    async def add_item_to_collection(self, 
                                   collection_id: str,
                                   item_type: Literal["file", "folder", "url", "camera", "audio"],
                                   source: str,
                                   name: str,
                                   operation: Literal["link", "copy", "move"] = "link",
                                   metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Add an item to a collection"""
        try:
            # Validate collection exists
            collection = await self.get_collection(collection_id)
            if not collection:
                logger.error(f"Collection not found: {collection_id}")
                return None
            
            # Create item
            item = CollectionItem(
                collection_id=collection_id,
                type=item_type,
                name=name,
                metadata=metadata or {}
            )
            
            # Handle different operations
            if operation == "link":
                # Just reference the source
                item.source_path = source
                item.storage_type = "external"
            elif operation in ["copy", "move"]:
                # Copy or move to library
                local_path = await self._add_item_to_library(collection, source, name, operation)
                item.local_path = str(local_path)
                item.storage_type = "local"
            elif operation == "capture":
                # Save captured content directly to library
                local_path = await self._save_captured_content(collection, name, item_type)
                item.local_path = str(local_path)
                item.storage_type = "local"
            
            # Save to storage
            if self.storage.add_collection_item(item):
                logger.info(f"Item added to collection: {name}")
                return item.id
            else:
                logger.error("Failed to save item to storage")
                return None
                
        except Exception as e:
            logger.error(f"Failed to add item to collection: {e}")
            return None
    
    async def _add_item_to_library(self, collection: Collection, source: str, name: str, operation: str) -> Path:
        """Add item to library directory"""
        try:
            source_path = Path(source)
            if not source_path.exists():
                raise FileNotFoundError(f"Source does not exist: {source}")
            
            # Create library item directory
            library_item_path = self.app.paths.data / "library" / "collections" / collection.name / "items"
            library_item_path.mkdir(parents=True, exist_ok=True)
            
            # Generate unique filename
            target_path = library_item_path / name
            
            if operation == "copy":
                if source_path.is_file():
                    shutil.copy2(source_path, target_path)
                else:
                    shutil.copytree(source_path, target_path, dirs_exist_ok=True)
            elif operation == "move":
                if source_path.is_file():
                    shutil.move(source_path, target_path)
                else:
                    shutil.move(source_path, target_path)
            
            logger.debug(f"Item added to library: {target_path}")
            return target_path
            
        except Exception as e:
            logger.error(f"Failed to add item to library: {e}")
            raise
    
    async def _save_captured_content(self, collection: Collection, name: str, item_type: str) -> Path:
        """Save captured content (camera/audio) to library"""
        try:
            # Create captured content directory
            captured_path = self.app.paths.data / "library" / "collections" / collection.name / "captured"
            captured_path.mkdir(parents=True, exist_ok=True)
            
            # Generate filename for captured content
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if item_type == "camera":
                filename = f"photo_{timestamp}.jpg"
            elif item_type == "audio":
                filename = f"recording_{timestamp}.m4a"
            else:
                filename = f"capture_{timestamp}.dat"
            
            target_path = captured_path / filename
            
            # For now, create a placeholder file
            # In a real implementation, this would save actual captured content
            target_path.touch()
            
            logger.debug(f"Captured content saved: {target_path}")
            return target_path
            
        except Exception as e:
            logger.error(f"Failed to save captured content: {e}")
            raise
    
    async def get_collection_items(self, collection_id: str) -> List[CollectionItem]:
        """Get all items in a collection"""
        return self.storage.get_collection_items(collection_id)

    async def get_item(self, item_id: str) -> Optional[CollectionItem]:
        """Get a single item by ID"""
        return self.storage.get_item(item_id)

    async def update_item_status(self, item_id: str, status: str) -> bool:
        """Update item processing status"""
        try:
            # This would update the item status in storage
            # For now, just log the update
            logger.debug(f"Item status updated: {item_id} -> {status}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update item status: {e}")
            return False
    
    # ===== PROCESSING INTEGRATION =====
    
    async def add_processing_result(self, 
                                  item_id: str,
                                  workflow: str,
                                  status: Literal["success", "failed", "partial"],
                                  output_paths: Optional[List[str]] = None,
                                  logs_path: Optional[str] = None,
                                  metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Add a processing result for an item"""
        try:
            result = ProcessingResult(
                item_id=item_id,
                workflow=workflow,
                status=status,
                output_paths=output_paths or [],
                logs_path=logs_path,
                metadata=metadata or {},
                started_at=datetime.now(),
                completed_at=datetime.now()
            )
            
            if self.storage.add_processing_result(result):
                logger.info(f"Processing result added: {workflow} -> {status}")
                return result.id
            else:
                logger.error("Failed to save processing result")
                return None
                
        except Exception as e:
            logger.error(f"Failed to add processing result: {e}")
            return None
    
    async def get_processing_history(self, item_id: str) -> List[ProcessingResult]:
        """Get processing history for an item"""
        return self.storage.get_processing_history(item_id)
    
    # ===== IMPORT/EXPORT =====
    
    async def export_collection(self, collection_id: str, output_path: Path, include_files: bool = False) -> bool:
        """Export a collection to ZIP + JSONL format"""
        return self.exporter.export_collection(collection_id, output_path, include_files)
    
    async def import_collection(self, import_path: Path, target_name: Optional[str] = None) -> Optional[str]:
        """Import a collection from ZIP + JSONL format"""
        return await self.importer.import_collection(import_path, target_name)
    
    # ===== DEMO SETUP =====
    
    async def _ensure_demo_collections(self):
        """Auto-populate demo collections if library is empty"""
        try:
            # Check if library already has collections (directly from storage)
            existing_collections = self.storage.get_all_collections()
            if existing_collections:
                logger.debug("Library already has collections, skipping demo setup")
                return
            
            logger.info("Empty library detected, setting up demo collections...")
            
            # Get demo collection paths
            demo_resources_path = Path(self.app.paths.app) / "resources" / "demo_collection"
            
            if not demo_resources_path.exists():
                logger.warning(f"Demo collection resources not found at: {demo_resources_path}")
                return
            
            # Add Test Document Collection (comprehensive test data)
            test_path = demo_resources_path / "test"
            if test_path.exists():
                await self.add_collection(
                    name="Test Document Collection",
                    collection_type="local",
                    source_path=str(test_path),
                    description="Comprehensive test collection with documents, images, and various file types for testing purposes"
                )
                logger.info("✅ Added Test Document Collection")
            
            # Add individual demo collections
            demo_path = demo_resources_path / "demo"
            if demo_path.exists():
                for demo_dir in demo_path.iterdir():
                    if demo_dir.is_dir() and not demo_dir.name.startswith('.'):
                        await self.add_collection(
                            name=demo_dir.name,
                            collection_type="local", 
                            source_path=str(demo_dir),
                            description=f"Demo collection: {demo_dir.name}"
                        )
                        logger.info(f"✅ Added demo collection: {demo_dir.name}")
            
            logger.info("🎉 Demo collections setup completed successfully!")
            
        except Exception as e:
            logger.error(f"Failed to setup demo collections: {e}")
    
    # ===== UTILITY METHODS =====
    
    def _clear_cache(self):
        """Clear the collections cache"""
        self._collections_cache = None
        self._cache_timestamp = None
    
    async def get_library_stats(self) -> Dict[str, Any]:
        """Get library statistics"""
        try:
            collections = await self.get_all_collections()
            
            total_items = 0
            total_processing_results = 0
            
            for collection in collections:
                items = await self.get_collection_items(collection.id)
                total_items += len(items)
                
                for item in items:
                    history = await self.get_processing_history(item.id)
                    total_processing_results += len(history)
            
            return {
                "total_collections": len(collections),
                "total_items": total_items,
                "total_processing_results": total_processing_results,
                "library_path": str(self.app.paths.data / "library"),
                "last_updated": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get library stats: {e}")
            return {}
    
    async def scan_external_collections(self) -> Dict[str, str]:
        """Scan external collections for availability"""
        try:
            collections = await self.get_all_collections()
            external_status = {}
            
            for collection in collections:
                if collection.type == "external" and collection.source_path:
                    path = Path(collection.source_path)
                    if path.exists():
                        external_status[collection.id] = "available"
                    else:
                        external_status[collection.id] = "unmounted"
                        logger.warning(f"External collection unmounted: {collection.name}")
            
            return external_status

        except Exception as e:
            logger.error(f"Failed to scan external collections: {e}")
            return {}

    # ===== URL DOWNLOAD/CACHE MANAGEMENT =====

    async def download_url_item(self, item_id: str, timeout: int = 30) -> bool:
        """
        Download and cache a URL item

        Args:
            item_id: ID of the URL item to download
            timeout: Download timeout in seconds

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get item
            item = await self.get_item(item_id)
            if not item:
                logger.error(f"Item not found: {item_id}")
                return False

            # Verify it's a URL item
            if item.type != "url" or not item.source_path:
                logger.error(f"Item {item_id} is not a URL item")
                return False

            # Check if already cached
            if item.local_path and Path(item.local_path).exists():
                logger.info(f"Item {item_id} already cached at {item.local_path}")
                return True

            # Download
            logger.info(f"Downloading URL item {item_id}: {item.source_path}")
            cache_metadata = await self.downloader.download_url(
                url=item.source_path,
                collection_id=item.collection_id,
                item_id=item_id,
                timeout=timeout
            )

            # Update item with cache info
            item.local_path = cache_metadata["cached_path"]
            item.metadata.update(cache_metadata)
            item.updated_at = datetime.now()

            # Save to database
            self.storage.update_item(item)

            logger.info(f"Successfully downloaded and cached item {item_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to download URL item {item_id}: {e}")
            return False

    async def download_collection_urls(
        self,
        collection_id: str,
        max_concurrent: int = 5,
        skip_cached: bool = True
    ) -> Dict[str, Any]:
        """
        Download all URL items in a collection

        Args:
            collection_id: ID of the collection
            max_concurrent: Maximum concurrent downloads
            skip_cached: Skip already cached items

        Returns:
            Dict with download statistics
        """
        try:
            # Get all items in collection
            items = await self.get_collection_items(collection_id)
            url_items = [item for item in items if item.type == "url"]

            if not url_items:
                logger.warning(f"No URL items found in collection {collection_id}")
                return {
                    "total": 0,
                    "downloaded": 0,
                    "skipped": 0,
                    "failed": 0
                }

            # Filter out already cached if requested
            if skip_cached:
                url_items = [
                    item for item in url_items
                    if not item.local_path or not Path(item.local_path).exists()
                ]

            logger.info(f"Downloading {len(url_items)} URL items from collection {collection_id}")

            # Download with concurrency limit
            semaphore = asyncio.Semaphore(max_concurrent)
            results = {
                "total": len(url_items),
                "downloaded": 0,
                "skipped": 0,
                "failed": 0
            }

            async def download_with_semaphore(item):
                async with semaphore:
                    try:
                        success = await self.download_url_item(item.id)
                        if success:
                            results["downloaded"] += 1
                        else:
                            results["failed"] += 1
                    except Exception as e:
                        logger.error(f"Failed to download item {item.id}: {e}")
                        results["failed"] += 1

            # Download all items
            await asyncio.gather(*[download_with_semaphore(item) for item in url_items])

            logger.info(f"Bulk download complete: {results}")
            return results

        except Exception as e:
            logger.error(f"Failed to download collection URLs: {e}")
            return {
                "total": 0,
                "downloaded": 0,
                "skipped": 0,
                "failed": 0,
                "error": str(e)
            }

    async def get_cache_info(self, collection_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get cache information

        Args:
            collection_id: Optional collection ID to filter by

        Returns:
            Dict with cache statistics
        """
        try:
            total_size = self.downloader.get_cache_size(collection_id)

            # Count cached items
            if collection_id:
                items = await self.get_collection_items(collection_id)
                cached_items = len([
                    item for item in items
                    if item.local_path and Path(item.local_path).exists()
                ])
                total_items = len([item for item in items if item.type == "url"])
            else:
                # Count all cached items across all collections
                collections = await self.get_all_collections()
                cached_items = 0
                total_items = 0
                for collection in collections:
                    items = await self.get_collection_items(collection.id)
                    cached_items += len([
                        item for item in items
                        if item.local_path and Path(item.local_path).exists()
                    ])
                    total_items += len([item for item in items if item.type == "url"])

            return {
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "cached_items": cached_items,
                "total_url_items": total_items,
                "cache_percentage": round((cached_items / total_items * 100) if total_items > 0 else 0, 1)
            }

        except Exception as e:
            logger.error(f"Failed to get cache info: {e}")
            return {
                "total_size_bytes": 0,
                "total_size_mb": 0.0,
                "cached_items": 0,
                "total_url_items": 0,
                "cache_percentage": 0.0,
                "error": str(e)
            }

    async def clear_cache(self, collection_id: Optional[str] = None) -> int:
        """
        Clear cached files

        Args:
            collection_id: Optional collection ID to clear (clears all if None)

        Returns:
            Number of files deleted
        """
        try:
            # Clear files from cache directory
            deleted_count = self.downloader.clear_cache(collection_id)

            # Update items in database to remove local_path
            if collection_id:
                items = await self.get_collection_items(collection_id)
            else:
                collections = await self.get_all_collections()
                items = []
                for collection in collections:
                    items.extend(await self.get_collection_items(collection.id))

            for item in items:
                if item.type == "url" and item.local_path:
                    item.local_path = None
                    item.metadata = {k: v for k, v in item.metadata.items()
                                   if k not in ["cached_path", "cached_at", "file_size", "content_type", "checksum"]}
                    item.updated_at = datetime.now()
                    self.storage.update_item(item)

            logger.info(f"Cleared {deleted_count} cached files")
            return deleted_count

        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return 0 