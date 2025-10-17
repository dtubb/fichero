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
    from fichero.shared.navigation.navigation_event_bus import emit_navigation_event
except ImportError:
    # Fallback for when navigation events aren't available (e.g., in CLI mode)
    def emit_navigation_event(event_type: str, data: Dict[str, Any] = None):
        """No-op fallback for emit_navigation_event"""
        pass

try:
    from fichero.library.models import Collection, CollectionItem, ProcessingResult, ExternalPath
    from fichero.library.storage import LibraryStorage
    from fichero.library.import_export import CollectionExporter, CollectionImporter
    from fichero.library.url_downloader import URLDownloader
    from fichero.library.icon_generator import IconGenerator
    from fichero.library.director_output_parser import DirectorOutputParser, ProcessingStep
except ImportError:
    try:
        from .models import Collection, CollectionItem, ProcessingResult, ExternalPath
        from .storage import LibraryStorage
        from .import_export import CollectionExporter, CollectionImporter
        from .url_downloader import URLDownloader
        from .icon_generator import IconGenerator
        from .director_output_parser import DirectorOutputParser, ProcessingStep
    except ImportError:
        # Direct import for testing
        import models
        import storage
        import import_export
        import url_downloader
        import icon_generator
        Collection = models.Collection
        CollectionItem = models.CollectionItem
        ProcessingResult = models.ProcessingResult
        ExternalPath = models.ExternalPath
        LibraryStorage = storage.LibraryStorage
        CollectionExporter = import_export.CollectionExporter
        CollectionImporter = import_export.CollectionImporter
        URLDownloader = url_downloader.URLDownloader
        IconGenerator = icon_generator.IconGenerator

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

        # Initialize icon generator with thumbnail cache and storage
        icon_cache_dir = db_path.parent / "thumbnails"
        self.icon_generator = IconGenerator(icon_cache_dir, self.storage)

        # Initialize output parser for reading Director processing results
        self.output_parser = DirectorOutputParser()

        # Store library path for file operations
        self.library_path = db_path.parent

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
                # Link to external location (store reference but also create library workspace)
                collection.source_path = source_path
                # Create library workspace for this external collection (for outputs, cache, etc.)
                workspace_path = self.library_path / "collections" / str(collection.id)
                workspace_path.mkdir(parents=True, exist_ok=True)
                collection.local_path = str(workspace_path)
                logger.debug(f"Created library workspace for external collection: {workspace_path}")
            elif collection_type == "url" and source_path:
                # Store URL reference and create workspace
                collection.source_path = source_path
                collection.metadata["url"] = source_path
                # Create library workspace for URL collection
                workspace_path = self.library_path / "collections" / str(collection.id)
                workspace_path.mkdir(parents=True, exist_ok=True)
                collection.local_path = str(workspace_path)
                logger.debug(f"Created library workspace for URL collection: {workspace_path}")
            
            # Save to storage
            if self.storage.add_collection(collection):
                # Clear cache
                self._clear_cache()
                logger.info(f"Collection added: {name} ({collection_type})")

                # Emit event to notify views
                emit_navigation_event("collection_added", {
                    "collection_id": collection.id,
                    "collection_name": name,
                    "collection_type": collection_type
                })

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

            # Create library collection directory using self.library_path
            library_collection_path = self.library_path / "collections" / collection.name
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
    
    async def get_collection_by_id(self, collection_id: str) -> Optional[Collection]:
        """Get a collection by ID (alias for get_collection)"""
        return await self.get_collection(collection_id)

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

            # Clean up thumbnails for items in this collection
            await self._delete_collection_thumbnails(collection_id)

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
            collection_name = collection.name  # Save name before deletion for event
            if self.storage.delete_collection(collection_id):
                self._clear_cache()
                logger.info(f"Collection deleted: {collection_name}")

                # Emit event to notify views
                emit_navigation_event("collection_deleted", {
                    "collection_id": collection_id,
                    "collection_name": collection_name
                })

                return True
            else:
                logger.error(f"Failed to delete collection {collection_id} from storage - check storage.delete_collection method")
                return False

        except Exception as e:
            logger.error(f"Failed to delete collection: {e}")
            return False

    async def rename_collection(self, collection_id: str, new_name: str) -> bool:
        """
        Rename a collection

        Args:
            collection_id: ID of collection to rename
            new_name: New name for the collection

        Returns:
            bool: True if rename succeeded, False otherwise
        """
        try:
            collection = await self.get_collection(collection_id)
            if not collection:
                logger.error(f"Collection not found: {collection_id}")
                return False

            # Check for duplicate name
            existing = await self.get_collection_by_name(new_name)
            if existing and existing.id != collection_id:
                logger.error(f"Collection with name '{new_name}' already exists")
                return False

            # Update name
            collection.name = new_name.strip()
            collection.updated_at = datetime.now()

            if self.storage.update_collection(collection):
                self._clear_cache()
                logger.info(f"Collection renamed to: {new_name}")
                return True
            else:
                logger.error(f"Failed to update collection in storage")
                return False

        except Exception as e:
            logger.error(f"Failed to rename collection: {e}")
            return False

    # ===== ITEM MANAGEMENT =====
    
    async def add_item_to_collection(self,
                                   collection_id: str,
                                   item_type: Literal["file", "folder", "url", "camera", "audio"],
                                   source: str,
                                   name: str,
                                   operation: Literal["link", "copy", "move"] = "link",
                                   metadata: Optional[Dict[str, Any]] = None,
                                   parent_id: Optional[str] = None) -> Optional[str]:
        """Add an item to a collection - automatically extracts ZIP files

        Args:
            collection_id: ID of the collection to add item to
            item_type: Type of item (file, folder, url, camera, audio)
            source: Source path or URL
            name: Display name for the item
            operation: How to add (link, copy, move)
            metadata: Optional metadata dictionary
            parent_id: Optional parent folder item ID for hierarchical organization
        """
        try:
            # Smart ZIP detection and extraction
            if item_type == "file" and source.lower().endswith('.zip'):
                logger.info(f"📦 ZIP file detected: {name} - extracting and importing contents")

                # Use ZIP import plugin to extract and import
                try:
                    from fichero.library.import_plugins.registry import PluginRegistry
                    from fichero.library.import_plugins.zip_plugin import ZipImportPlugin

                    # Create registry and register ZIP plugin
                    registry = PluginRegistry()
                    zip_plugin = ZipImportPlugin(self)
                    registry.register(zip_plugin)

                    # Get plugin from registry
                    zip_plugin = registry.get_plugin_by_name("ZIP Import")

                    if zip_plugin:
                        # Create collection name from ZIP file
                        zip_collection_name = Path(source).stem

                        # Import the ZIP file (extract and import contents)
                        result = await zip_plugin.download_and_import(
                            url=source,  # Local file path
                            collection_name=zip_collection_name,
                            collection_description=f"Imported from {name}"
                        )

                        if result.success:
                            logger.info(f"✅ ZIP import successful: {result.files_imported} files imported")

                            # Clear cache to show new collection
                            self._clear_cache()

                            # Emit event to notify views
                            emit_navigation_event("collection_added", {
                                "collection_id": result.collection_id,
                                "collection_name": zip_collection_name,
                                "collection_type": "local"
                            })

                            # Return the collection ID from ZIP import result
                            return result.collection_id
                        else:
                            logger.error(f"❌ ZIP import failed: {result.error_message}")
                            # Fall through to normal file handling if ZIP import fails
                    else:
                        logger.warning("ZIP import plugin not available - treating as regular file")

                except Exception as zip_error:
                    logger.error(f"Failed to import ZIP file: {zip_error}")
                    # Fall through to normal file handling if ZIP import fails

            # Normal file/folder handling (non-ZIP or ZIP import fallback)
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
                parent_id=parent_id,  # Support hierarchical organization
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

    async def add_folder_items_to_collection(
        self,
        collection_id: str,
        folder_path: str,
        operation: Literal["link", "copy", "move"] = "link",
        recursive: bool = True
    ) -> Dict[str, Any]:
        """
        Add all files and folders as hierarchical items to collection

        This method preserves folder structure by creating folder items and
        linking files to their parent folders via parent_id.

        Args:
            collection_id: Collection to add items to
            folder_path: Path to folder
            operation: How to handle files (link, copy, or move)
            recursive: Whether to recurse into subdirectories

        Returns:
            Dict with stats: {"added": int, "skipped": int, "errors": int, "item_ids": List[str]}
        """
        try:
            folder = Path(folder_path)
            if not folder.exists() or not folder.is_dir():
                logger.error(f"Folder does not exist: {folder_path}")
                return {"added": 0, "skipped": 0, "errors": 1, "item_ids": []}

            # Validate collection exists
            collection = await self.get_collection(collection_id)
            if not collection:
                logger.error(f"Collection not found: {collection_id}")
                return {"added": 0, "skipped": 0, "errors": 1, "item_ids": []}

            # Stats tracking
            stats = {
                "added": 0,
                "skipped": 0,
                "errors": 0,
                "item_ids": []
            }

            # Map relative paths to folder item IDs for parent_id linking
            folder_item_map: Dict[str, str] = {}

            # Track thumbnail generation tasks
            thumbnail_tasks = []

            # Helper to process directory recursively with hierarchy
            async def process_directory(dir_path: Path, parent_id: Optional[str] = None):
                """Recursively process a directory, creating folder and file items"""
                try:
                    # Get directory contents
                    for entry in sorted(dir_path.iterdir()):
                        # Skip hidden files/folders
                        if entry.name.startswith('.'):
                            continue

                        if entry.is_dir():
                            if recursive:
                                # Create folder item
                                folder_item = CollectionItem(
                                    collection_id=collection_id,
                                    type="folder",
                                    name=entry.name,
                                    parent_id=parent_id,
                                    source_path=str(entry),
                                    storage_type="external",
                                    metadata={
                                        "relative_path": str(entry.relative_to(folder)) if entry.is_relative_to(folder) else None
                                    }
                                )

                                # Save folder item
                                if self.storage.add_collection_item(folder_item):
                                    logger.debug(f"📁 Created folder item: {entry.name}")
                                    stats["added"] += 1
                                    stats["item_ids"].append(folder_item.id)

                                    # Map relative path to folder ID
                                    rel_path = str(entry.relative_to(folder)) if entry.is_relative_to(folder) else entry.name
                                    folder_item_map[rel_path] = folder_item.id

                                    # Recursively process subfolder
                                    await process_directory(entry, parent_id=folder_item.id)
                                else:
                                    logger.error(f"Failed to save folder item: {entry.name}")
                                    stats["errors"] += 1

                        elif entry.is_file():
                            # Calculate file hash for deduplication
                            file_hash = self.icon_generator.calculate_file_hash(entry)

                            # Check if file already exists
                            existing_items = self.storage.get_collection_items(collection_id)
                            file_exists = any(
                                item.metadata.get('file_hash') == file_hash
                                for item in existing_items
                            )

                            if file_exists:
                                logger.debug(f"File already in collection (hash: {file_hash[:8]}...): {entry.name}")
                                stats["skipped"] += 1
                                continue

                            # Create file item metadata
                            metadata = {
                                "file_hash": file_hash,
                                "original_path": str(entry),
                                "relative_path": str(entry.relative_to(folder)) if entry.is_relative_to(folder) else None
                            }

                            # Create file item with parent_id link
                            file_item = CollectionItem(
                                collection_id=collection_id,
                                type="file",
                                name=entry.name,
                                parent_id=parent_id,  # Link to parent folder
                                metadata=metadata
                            )

                            # Handle different operations
                            if operation == "link":
                                file_item.source_path = str(entry)
                                file_item.storage_type = "external"
                            elif operation in ["copy", "move"]:
                                local_path = await self._add_item_to_library(collection, str(entry), entry.name, operation)
                                file_item.local_path = str(local_path)
                                file_item.storage_type = "local"

                            # Save file item
                            if self.storage.add_collection_item(file_item):
                                logger.debug(f"📄 Added file: {entry.name} (parent: {parent_id or 'root'})")
                                stats["added"] += 1
                                stats["item_ids"].append(file_item.id)

                                # Generate thumbnail asynchronously
                                try:
                                    task = asyncio.create_task(
                                        asyncio.to_thread(
                                            self.icon_generator.get_item_icon,
                                            str(entry),
                                            "file",
                                            self.icon_generator.thumbnail_size
                                        )
                                    )
                                    thumbnail_tasks.append(task)
                                except Exception as thumb_error:
                                    logger.warning(f"Failed to generate thumbnail for {entry.name}: {thumb_error}")
                            else:
                                logger.error(f"Failed to save file item: {entry.name}")
                                stats["errors"] += 1

                except Exception as e:
                    logger.error(f"Error processing directory {dir_path}: {e}")
                    stats["errors"] += 1

            # Start processing from root folder
            logger.info(f"📦 Starting hierarchical import from: {folder_path}")
            await process_directory(folder, parent_id=None)

            # Wait for all thumbnail generation tasks
            if thumbnail_tasks:
                logger.info(f"Waiting for {len(thumbnail_tasks)} thumbnail tasks...")
                await asyncio.gather(*thumbnail_tasks, return_exceptions=True)
                logger.info(f"All thumbnails generated")

            logger.info(
                f"✅ Hierarchical import complete - Added: {stats['added']}, "
                f"Skipped: {stats['skipped']}, Errors: {stats['errors']}"
            )

            # Emit event if items were added
            if stats['added'] > 0:
                emit_navigation_event("collection_items_changed", {
                    "collection_id": collection_id,
                    "added_count": stats['added'],
                    "total_items": stats['added'] + stats['skipped']
                })

            return stats

        except Exception as e:
            logger.error(f"Failed to add folder items to collection: {e}")
            import traceback
            traceback.print_exc()
            return {"added": 0, "skipped": 0, "errors": 1, "item_ids": []}

    async def _add_item_to_library(self, collection: Collection, source: str, name: str, operation: str) -> Path:
        """Add item to library directory"""
        try:
            source_path = Path(source)
            if not source_path.exists():
                raise FileNotFoundError(f"Source does not exist: {source}")

            # Create library item directory using self.library_path
            library_item_path = self.library_path / "collections" / collection.name / "items"
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
            # Create captured content directory using self.library_path
            captured_path = self.library_path / "collections" / collection.name / "captured"
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

    async def update_item(self, item: CollectionItem) -> bool:
        """Update an item in storage"""
        try:
            self.storage.update_item(item)
            logger.debug(f"Item updated: {item.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update item {item.id}: {e}")
            return False

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

    async def get_latest_processing_result(self, item_id: str) -> Optional[ProcessingResult]:
        """Get the most recent successful processing result for an item"""
        try:
            history = await self.get_processing_history(item_id)
            if not history:
                return None

            # Filter for successful results only
            successful = [r for r in history if r.status == "success" and r.output_paths]

            if not successful:
                return None

            # Sort by completed_at descending (most recent first)
            successful.sort(key=lambda r: r.completed_at or datetime.min, reverse=True)

            return successful[0]

        except Exception as e:
            logger.error(f"Failed to get latest processing result: {e}")
            return None

    async def get_file_processing_steps(self, source_file_path: Path, processing_result: ProcessingResult) -> List[ProcessingStep]:
        """
        Get ordered list of processing steps for a file from a processing result

        This method parses the Director output folder to discover what processing
        steps were performed and returns them in order.

        Args:
            source_file_path: Path to the original source file
            processing_result: ProcessingResult containing output_paths

        Returns:
            List of ProcessingStep objects showing the workflow progression
        """
        try:
            if not processing_result or not processing_result.output_paths:
                logger.debug("No processing result or output paths provided")
                return []

            output_path = Path(processing_result.output_paths[0])
            if not output_path.exists():
                logger.warning(f"Processing output path does not exist: {output_path}")
                return []

            # Get file outputs for this specific file
            filename = source_file_path.name
            file_outputs = self.output_parser.get_file_outputs(output_path, filename)

            if not file_outputs:
                logger.debug(f"No file outputs found for {filename} in {output_path}")
                return []

            # Get processing steps from the first file output
            # (usually there's only one, unless it's a batch with duplicates)
            steps = self.output_parser.get_processing_steps(file_outputs[0])

            logger.info(f"Found {len(steps)} processing steps for {filename}")
            return steps

        except Exception as e:
            logger.error(f"Failed to get processing steps: {e}")
            import traceback
            traceback.print_exc()
            return []

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

            # Get demo collection paths (skip if app.paths not available - e.g., CLI mode)
            # Check if app.paths exists AND is not a Mock (Mock returns Mock for any attribute)
            try:
                if not hasattr(self.app, 'paths') or not hasattr(self.app.paths, 'app'):
                    logger.debug("App paths not available (likely CLI mode), skipping demo setup")
                    return

                # Try to convert to Path - will fail if it's a Mock
                demo_resources_path = Path(self.app.paths.app) / "resources" / "demo_collection"
            except (TypeError, AttributeError) as path_error:
                logger.debug(f"App paths not functional (likely CLI mode): {path_error}, skipping demo setup")
                return
            
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
    
    async def _delete_collection_thumbnails(self, collection_id: str):
        """Delete thumbnails for items in collection (only if not shared with other collections)"""
        try:
            logger.info(f"🗑️ Starting thumbnail deletion for collection {collection_id}")

            # Get all items in the collection
            items = self.storage.get_collection_items(collection_id)
            logger.info(f"Found {len(items) if items else 0} items in collection")

            if not items:
                logger.info("No items found, skipping thumbnail deletion")
                return

            deleted_files = 0
            deleted_records = 0
            skipped_shared = 0
            cache_dir = self.icon_generator.cache_dir

            if not cache_dir or not cache_dir.exists():
                logger.warning(f"Cache directory doesn't exist: {cache_dir}")
                return

            # Track unique file hashes to avoid processing duplicates within this collection
            processed_hashes = set()

            # Process each item's thumbnails
            for item in items:
                # Get file hash from item metadata
                file_hash = item.metadata.get('file_hash')

                if not file_hash:
                    logger.debug(f"No file_hash in metadata for item: {item.name}")
                    continue

                # Skip if we already processed this hash
                if file_hash in processed_hashes:
                    continue
                processed_hashes.add(file_hash)

                # Check if OTHER collections have items with this same file_hash
                other_refs = self.storage.count_items_with_file_hash(file_hash, exclude_collection_id=collection_id)

                if other_refs > 0:
                    # Other collections reference this file - DON'T delete thumbnail
                    logger.debug(f"Keeping thumbnail for {file_hash[:8]}... ({other_refs} other references)")
                    skipped_shared += 1
                    continue

                # No other references - safe to delete
                try:
                    # Get all thumbnail records for this file_hash
                    thumbnails = self.storage.get_thumbnails_by_file_hash(file_hash)

                    for thumb in thumbnails:
                        # Delete thumbnail file
                        thumbnail_path = cache_dir / thumb.thumbnail_path
                        if thumbnail_path.exists():
                            thumbnail_path.unlink()
                            deleted_files += 1
                            logger.debug(f"✅ Deleted thumbnail file: {thumb.thumbnail_path}")

                        # Delete database record
                        if self.storage.delete_thumbnail(thumb.id):
                            deleted_records += 1
                            logger.debug(f"✅ Deleted thumbnail record: {thumb.id}")

                except Exception as e:
                    logger.error(f"Failed to delete thumbnails for hash {file_hash[:8]}...: {e}", exc_info=True)
                    continue

            logger.info(
                f"🗑️ Thumbnail deletion complete - "
                f"Deleted: {deleted_files} files, {deleted_records} records, "
                f"Skipped (shared): {skipped_shared}"
            )

        except Exception as e:
            logger.error(f"Failed to delete collection thumbnails: {e}", exc_info=True)

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
                "library_path": str(self.library_path),
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

    # ===== FILE AND ICON OPERATIONS =====

    async def get_item_file(self, item_id: str, download_if_url: bool = True) -> Optional[Path]:
        """
        Get file path for an item, downloading URL if needed

        Args:
            item_id: ID of the item
            download_if_url: If True, download and cache URL items

        Returns:
            Path to file or None if not available
        """
        try:
            item = self.storage.get_item(item_id)
            if not item:
                logger.error(f"Item not found: {item_id}")
                return None

            # For file and folder items, return source or local path
            if item.type in ["file", "folder"]:
                if item.local_path and Path(item.local_path).exists():
                    return Path(item.local_path)
                elif item.source_path and Path(item.source_path).exists():
                    return Path(item.source_path)
                else:
                    logger.warning(f"File not found for item {item_id}")
                    return None

            # For URL items, check cache or download
            if item.type == "url":
                # Check if already cached
                if item.local_path and Path(item.local_path).exists():
                    return Path(item.local_path)

                # Download if requested
                if download_if_url and item.source_path:
                    logger.info(f"Downloading URL for item {item_id}")
                    success = await self.download_url_item(item_id)
                    if success:
                        # Reload item to get updated local_path
                        item = self.storage.get_item(item_id)
                        if item and item.local_path and Path(item.local_path).exists():
                            return Path(item.local_path)

                return None

            logger.warning(f"Unsupported item type: {item.type}")
            return None

        except Exception as e:
            logger.error(f"Failed to get file for item {item_id}: {e}")
            return None

    async def get_item_icon(self, item_id: str, size: tuple = None) -> Optional['toga.Image']:
        """
        Get icon/thumbnail for an item

        Args:
            item_id: ID of the item
            size: Optional (width, height) for icon size

        Returns:
            toga.Image or None
        """
        try:
            item = self.storage.get_item(item_id)
            if not item:
                logger.error(f"Item not found: {item_id}")
                return None

            # Get file path (prefer cached for URLs)
            file_path = None
            if item.local_path and Path(item.local_path).exists():
                file_path = item.local_path
            elif item.source_path and Path(item.source_path).exists():
                file_path = item.source_path

            # Generate icon
            return self.icon_generator.get_item_icon(file_path, item.type, size)

        except Exception as e:
            logger.error(f"Failed to get icon for item {item_id}: {e}")
            return None

    async def get_collection_icon(self, collection_id: str, size: tuple = None) -> Optional['toga.Image']:
        """
        Get icon for a collection (uses first image item)

        Args:
            collection_id: ID of the collection
            size: Optional (width, height) for icon size

        Returns:
            toga.Image or None
        """
        try:
            collection = self.storage.get_collection(collection_id)
            if not collection:
                logger.error(f"Collection not found: {collection_id}")
                return None

            # Get first image item for icon
            items = await self.get_collection_items(collection_id)
            for item in items:
                # Try to get icon from first available image
                icon = await self.get_item_icon(item.id, size)
                if icon:
                    return icon

            # No items or no images, return default collection icon
            return self.icon_generator._get_default_icon('folder')

        except Exception as e:
            logger.error(f"Failed to get collection icon: {e}")
            return None

    def get_filesystem_icon(self, path: Path, size: tuple = None, generate: bool = True) -> Optional['toga.Image']:
        """
        Get icon for a filesystem path (not necessarily a library item)

        Args:
            path: Path to file or directory
            size: Optional (width, height) for icon size
            generate: Whether to generate thumbnail if not cached (default: True)

        Returns:
            toga.Image or None
        """
        try:
            import toga

            if path.is_dir():
                # Use static folder icon from resources (only available in GUI mode)
                if hasattr(self.app, 'paths'):
                    folder_icon_path = self.app.paths.app / "resources" / "icons" / "files_folders" / "folder_small_icon.png"
                    if folder_icon_path.exists():
                        return toga.Image(str(folder_icon_path))
                return None

            elif path.is_file():
                # Determine file type
                suffix = path.suffix.lower()
                image_formats = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp'}

                if suffix in image_formats:
                    # For images, use icon_generator which handles caching and generation
                    if generate:
                        icon = self.icon_generator.get_item_icon(str(path), 'file', size)
                        return icon
                    else:
                        # Only check cache, don't generate
                        cache_dir = Path(self.icon_generator.cache_dir)
                        cache_key = f"{path.stem}_64x64.png" if not size else f"{path.stem}_{size[0]}x{size[1]}.png"
                        cached_thumb = cache_dir / cache_key

                        if cached_thumb.exists():
                            return toga.Image(str(cached_thumb))
                        else:
                            return None
                else:
                    # For non-images, use default file icon
                    return self.icon_generator._get_default_icon('file', suffix)

            return None

        except Exception as e:
            logger.error(f"Error loading icon for {path}: {e}")
            return None

    async def preload_thumbnails(self, collection_id: str) -> int:
        """
        Pre-generate thumbnails for all items in a collection

        Args:
            collection_id: ID of the collection

        Returns:
            Number of thumbnails generated
        """
        try:
            items = await self.get_collection_items(collection_id)
            generated = 0

            for item in items:
                try:
                    icon = await self.get_item_icon(item.id)
                    if icon:
                        generated += 1
                except Exception as e:
                    logger.warning(f"Failed to generate thumbnail for item {item.id}: {e}")

            logger.info(f"Pre-generated {generated} thumbnails for collection {collection_id}")
            return generated

        except Exception as e:
            logger.error(f"Failed to preload thumbnails: {e}")
            return 0

    async def export_collection(self, collection_id: str, output_path: Path) -> bool:
        """
        Export collection with all files and metadata to zip archive

        Args:
            collection_id: ID of collection to export
            output_path: Path where zip file should be created

        Returns:
            bool: True if export succeeded, False otherwise
        """
        import json
        import zipfile
        import tempfile
        import shutil

        try:
            # Get collection
            collection = self.storage.get_collection(collection_id)
            if not collection:
                logger.error(f"Collection not found: {collection_id}")
                return False

            # Get all items
            items = await self.get_collection_items(collection_id)

            # Create temporary directory for building export
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Create export structure
                files_dir = temp_path / "files"
                cache_dir = temp_path / "cache"
                files_dir.mkdir()
                cache_dir.mkdir()

                # Export manifest
                manifest = {
                    "collection_id": collection.id,
                    "collection_name": collection.name,
                    "collection_type": collection.type,
                    "description": collection.metadata.get("description", ""),
                    "created_at": collection.created_at.isoformat(),
                    "updated_at": collection.updated_at.isoformat(),
                    "metadata": collection.metadata,
                    "export_version": "1.0",
                    "export_date": datetime.now().isoformat(),
                    "item_count": len(items)
                }

                with open(temp_path / "manifest.json", 'w') as f:
                    json.dump(manifest, f, indent=2)

                # Export items and collect files
                items_export = []
                for item in items:
                    item_export = {
                        "id": item.id,
                        "type": item.type,
                        "name": item.name,
                        "status": item.status,
                        "created_at": item.created_at.isoformat(),
                        "updated_at": item.updated_at.isoformat(),
                        "metadata": item.metadata
                    }

                    # Handle file/folder items
                    if item.type in ["file", "folder"] and item.source_path:
                        source = Path(item.source_path)
                        if source.exists():
                            item_dir = files_dir / item.id
                            item_dir.mkdir()

                            if source.is_file():
                                shutil.copy2(source, item_dir / source.name)
                                item_export["file_path"] = f"files/{item.id}/{source.name}"
                            elif source.is_dir():
                                shutil.copytree(source, item_dir / source.name)
                                item_export["folder_path"] = f"files/{item.id}/{source.name}"

                    # Handle URL items with cached files
                    if item.type == "url":
                        item_export["original_url"] = item.source_path

                        if item.local_path:
                            cached_file = Path(item.local_path)
                            if cached_file.exists():
                                cache_filename = f"{item.id}_{cached_file.name}"
                                shutil.copy2(cached_file, cache_dir / cache_filename)
                                item_export["cached_path"] = f"cache/{cache_filename}"

                    items_export.append(item_export)

                # Save items list
                with open(temp_path / "items.json", 'w') as f:
                    json.dump(items_export, f, indent=2)

                # Create zip file
                output_path = Path(output_path)
                if not output_path.suffix.lower() == '.zip':
                    output_path = output_path.with_suffix('.zip')

                output_path.parent.mkdir(parents=True, exist_ok=True)

                with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file_path in temp_path.rglob('*'):
                        if file_path.is_file():
                            arcname = file_path.relative_to(temp_path)
                            zipf.write(file_path, arcname)

                file_size = output_path.stat().st_size
                logger.info(f"Exported collection '{collection.name}' to {output_path} ({file_size / (1024*1024):.1f} MB)")
                return True

        except Exception as e:
            logger.error(f"Failed to export collection: {e}")
            return False

    async def import_collection(self, zip_path: Path, name: Optional[str] = None) -> Optional[str]:
        """
        Import collection from export zip archive

        Args:
            zip_path: Path to exported zip file
            name: Optional new name for collection (uses original if not provided)

        Returns:
            str: New collection ID if import succeeded, None otherwise
        """
        import json
        import zipfile
        import tempfile
        import shutil

        try:
            if not zip_path.exists():
                logger.error(f"Zip file not found: {zip_path}")
                return None

            # Extract zip to temp directory
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                with zipfile.ZipFile(zip_path, 'r') as zipf:
                    zipf.extractall(temp_path)

                # Read manifest
                manifest_path = temp_path / "manifest.json"
                if not manifest_path.exists():
                    logger.error("Invalid export: manifest.json not found")
                    return None

                with open(manifest_path, 'r') as f:
                    manifest = json.load(f)

                # Read items
                items_path = temp_path / "items.json"
                if not items_path.exists():
                    logger.error("Invalid export: items.json not found")
                    return None

                with open(items_path, 'r') as f:
                    items_data = json.load(f)

                # Create new collection
                collection_name = name or manifest["collection_name"]
                collection_id = await self.add_collection(
                    name=collection_name,
                    collection_type=manifest["collection_type"],
                    description=manifest.get("description", f"Imported from {zip_path.name}"),
                    metadata=manifest.get("metadata", {})
                )

                if not collection_id:
                    logger.error("Failed to create collection")
                    return None

                # Import items
                for item_data in items_data:
                    item_id = item_data["id"]
                    item_type = item_data["type"]
                    item_name = item_data["name"]

                    # Handle file items
                    if "file_path" in item_data:
                        src_file = temp_path / item_data["file_path"]
                        if src_file.exists():
                            # Copy file to library storage
                            dest_dir = self.library_path / collection_id / "files"
                            dest_dir.mkdir(parents=True, exist_ok=True)
                            dest_file = dest_dir / src_file.name
                            shutil.copy2(src_file, dest_file)

                            await self.add_item_to_collection(
                                collection_id=collection_id,
                                item_type="file",
                                source=str(dest_file),
                                name=item_name,
                                operation="link"
                            )

                    # Handle folder items
                    elif "folder_path" in item_data:
                        src_folder = temp_path / item_data["folder_path"]
                        if src_folder.exists():
                            # Copy folder to library storage
                            dest_dir = self.library_path / collection_id / "folders"
                            dest_dir.mkdir(parents=True, exist_ok=True)
                            dest_folder = dest_dir / src_folder.name
                            shutil.copytree(src_folder, dest_folder)

                            await self.add_item_to_collection(
                                collection_id=collection_id,
                                item_type="folder",
                                source=str(dest_folder),
                                name=item_name,
                                operation="link"
                            )

                    # Handle URL items
                    elif item_type == "url":
                        original_url = item_data.get("original_url")
                        if original_url:
                            # Add URL item
                            new_item_id = await self.add_item_to_collection(
                                collection_id=collection_id,
                                item_type="url",
                                source=original_url,
                                name=item_name,
                                operation="link"
                            )

                            # Restore cached file if present
                            if "cached_path" in item_data:
                                src_cache = temp_path / item_data["cached_path"]
                                if src_cache.exists() and new_item_id:
                                    # Copy to cache directory
                                    cache_dest = self.downloader.cache_root / collection_id
                                    cache_dest.mkdir(parents=True, exist_ok=True)
                                    cache_file = cache_dest / src_cache.name
                                    shutil.copy2(src_cache, cache_file)

                                    # Update item with cache info
                                    item = self.storage.get_item(new_item_id)
                                    if item:
                                        item.local_path = str(cache_file)
                                        item.metadata.update(item_data.get("metadata", {}))
                                        self.storage.update_item(item)

                    # Handle items without physical files (metadata-only or broken references)
                    else:
                        # Import as metadata-only item, preserving original data
                        await self.add_item_to_collection(
                            collection_id=collection_id,
                            item_type=item_type,
                            source=item_data.get("metadata", {}).get("original_path", ""),
                            name=item_name,
                            operation="link",
                            metadata=item_data.get("metadata", {})
                        )

                logger.info(f"Imported collection '{collection_name}' with {len(items_data)} items")
                return collection_id

        except zipfile.BadZipFile:
            logger.error(f"Invalid zip file: {zip_path}")
            return None
        except Exception as e:
            logger.error(f"Failed to import collection: {e}")
            return None

 