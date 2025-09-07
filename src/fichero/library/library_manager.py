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
except ImportError:
    try:
        from .models import Collection, CollectionItem, ProcessingResult, ExternalPath
        from .storage import LibraryStorage
        from .import_export import CollectionExporter, CollectionImporter
    except ImportError:
        # Direct import for testing
        import models
        import storage
        import import_export
        Collection = models.Collection
        CollectionItem = models.CollectionItem
        ProcessingResult = models.ProcessingResult
        ExternalPath = models.ExternalPath
        LibraryStorage = storage.LibraryStorage
        CollectionExporter = import_export.CollectionExporter
        CollectionImporter = import_export.CollectionImporter

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
        
        # Collection cache
        self._collections_cache: Optional[List[Collection]] = None
        self._cache_timestamp: Optional[datetime] = None
        
        logger.info(f"Library manager initialized successfully with database: {db_path}")
    
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
    
    async def get_all_collections(self, force_refresh: bool = False) -> List[Collection]:
        """Get all collections with caching"""
        try:
            # Check cache
            if (not force_refresh and 
                self._collections_cache is not None and 
                self._cache_timestamp and 
                (datetime.now() - self._cache_timestamp).seconds < 30):
                return self._collections_cache.copy()
            
            # Load from storage
            collections = self.storage.get_all_collections()
            
            # Update cache
            self._collections_cache = collections
            self._cache_timestamp = datetime.now()
            
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
                    shutil.rmtree(local_path)
                    logger.debug(f"Removed local collection files: {local_path}")
            
            # Remove from storage
            if self.storage.delete_collection(collection_id):
                self._clear_cache()
                logger.info(f"Collection deleted: {collection.name}")
                return True
            else:
                logger.error("Failed to delete collection from storage")
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