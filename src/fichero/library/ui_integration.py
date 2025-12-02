"""
UI Integration Layer for Fichero Library

Connects the library backend to existing UI components without breaking current functionality.
"""

import logging
import asyncio
from typing import List, Optional, Dict, Any, Callable
from pathlib import Path

try:
    from fichero.library.library_manager import LibraryManager
    from fichero.library.models import Collection, CollectionItem, ProcessingResult
except ImportError:
    try:
        from .library_manager import LibraryManager
        from .models import Collection, CollectionItem, ProcessingResult
    except ImportError:
        # Direct import for testing
        import library_manager
        import models
        LibraryManager = library_manager.LibraryManager
        Collection = models.Collection
        CollectionItem = models.CollectionItem
        ProcessingResult = models.ProcessingResult

logger = logging.getLogger(__name__)


class LibraryUIIntegration:
    """Integrates library manager with existing UI components"""
    
    def __init__(self, library_manager: LibraryManager):
        """Initialize UI integration with library manager"""
        self.library_manager = library_manager
        
        # UI callbacks
        self.on_collection_added: Optional[Callable[[Collection], None]] = None
        self.on_collection_updated: Optional[Callable[[Collection], None]] = None
        self.on_collection_deleted: Optional[Callable[[str], None]] = None
        self.on_item_added: Optional[Callable[[CollectionItem], None]] = None
        self.on_processing_result: Optional[Callable[[ProcessingResult], None]] = None
        
        logger.info("Library UI integration initialized")
    
    # ===== COLLECTION OPERATIONS =====
    
    async def add_collection_from_ui(self, 
                                   name: str,
                                   collection_type: str,
                                   source_path: Optional[str] = None,
                                   description: str = "") -> bool:
        """Add collection from UI (folder picker, etc.)"""
        try:
            collection_id = await self.library_manager.add_collection(
                name=name,
                collection_type=collection_type,
                source_path=source_path,
                description=description
            )
            
            if collection_id:
                # Notify UI
                if self.on_collection_added:
                    collection = await self.library_manager.get_collection(collection_id)
                    if collection:
                        self.on_collection_added(collection)
                
                logger.info(f"Collection added from UI: {name}")
                return True
            else:
                logger.error("Failed to add collection from UI")
                return False
                
        except Exception as e:
            logger.error(f"Failed to add collection from UI: {e}")
            return False
    
    async def add_external_collection_from_ui(self, path: str, name: str) -> bool:
        """Add external collection from UI (external drive, network path)"""
        return await self.add_collection_from_ui(
            name=name,
            collection_type="external",
            source_path=path,
            description=f"External collection at {path}"
        )
    
    async def add_url_collection_from_ui(self, url: str, name: str) -> bool:
        """Add URL collection from UI (web resource)"""
        return await self.add_collection_from_ui(
            name=name,
            collection_type="url",
            source_path=url,
            description=f"URL collection: {url}"
        )
    
    async def add_folder_to_collection_from_ui(self, 
                                             collection_id: str,
                                             folder_path: str,
                                             operation: str = "link") -> bool:
        """Add folder to collection from UI (folder picker)"""
        try:
            folder_name = Path(folder_path).name
            
            item_id = await self.library_manager.add_item_to_collection(
                collection_id=collection_id,
                item_type="folder",
                source=folder_path,
                name=folder_name,
                operation=operation
            )
            
            if item_id:
                # Notify UI
                if self.on_item_added:
                    items = await self.library_manager.get_collection_items(collection_id)
                    item = next((i for i in items if i.id == item_id), None)
                    if item:
                        self.on_item_added(item)
                
                logger.info(f"Folder added to collection: {folder_name}")
                return True
            else:
                logger.error("Failed to add folder to collection")
                return False
                
        except Exception as e:
            logger.error(f"Failed to add folder to collection: {e}")
            return False
    
    async def add_file_to_collection_from_ui(self, 
                                           collection_id: str,
                                           file_path: str,
                                           operation: str = "link") -> bool:
        """Add file to collection from UI (file picker)"""
        try:
            file_name = Path(file_path).name
            
            item_id = await self.library_manager.add_item_to_collection(
                collection_id=collection_id,
                item_type="file",
                source=file_path,
                name=file_name,
                operation=operation
            )
            
            if item_id:
                # Notify UI
                if self.on_item_added:
                    items = await self.library_manager.get_collection_items(collection_id)
                    item = next((i for i in items if i.id == item_id), None)
                    if item:
                        self.on_item_added(item)
                
                logger.info(f"File added to collection: {file_name}")
                return True
            else:
                logger.error("Failed to add file to collection")
                return False
                
        except Exception as e:
            logger.error(f"Failed to add file to collection: {e}")
            return False

    async def rename_collection(self, collection_id: str, new_name: str) -> bool:
        """Rename a collection via library manager

        Args:
            collection_id: ID of collection to rename
            new_name: New name for collection

        Returns:
            True if rename succeeded, False otherwise
        """
        try:
            success = await self.library_manager.rename_collection(collection_id, new_name)
            if success and self.on_collection_updated:
                # Get updated collection for callback
                collections = await self.library_manager.get_all_collections()
                collection = next((c for c in collections if c.id == collection_id), None)
                if collection:
                    self.on_collection_updated(collection)
            return success
        except Exception as e:
            logger.error(f"Failed to rename collection: {e}")
            return False

    async def delete_collection(self, collection_id: str) -> bool:
        """Delete a collection via library manager

        Args:
            collection_id: ID of collection to delete

        Returns:
            True if delete succeeded, False otherwise
        """
        try:
            success = await self.library_manager.delete_collection(collection_id)
            if success and self.on_collection_deleted:
                self.on_collection_deleted(collection_id)
            return success
        except Exception as e:
            logger.error(f"Failed to delete collection: {e}")
            return False

    async def duplicate_collection(self, collection_id: str) -> Optional[str]:
        """Duplicate a collection via library manager

        Args:
            collection_id: ID of collection to duplicate

        Returns:
            ID of new collection if successful, None otherwise
        """
        try:
            # Get existing collection
            collection = await self.library_manager.get_collection(collection_id)
            if not collection:
                logger.error(f"Collection not found: {collection_id}")
                return None

            # Create new collection with "(Copy)" suffix
            new_name = f"{collection.name} (Copy)"
            new_collection_id = await self.library_manager.add_collection(
                name=new_name,
                collection_type=collection.type,
                source_path=collection.source_path,
                description=collection.metadata.get("description", ""),
                metadata=collection.metadata
            )

            if new_collection_id and self.on_collection_added:
                new_collection = await self.library_manager.get_collection(new_collection_id)
                if new_collection:
                    self.on_collection_added(new_collection)

            return new_collection_id
        except Exception as e:
            logger.error(f"Failed to duplicate collection: {e}")
            return None

    # ===== COLLECTION RETRIEVAL =====
    
    async def get_collections_for_ui(self) -> List[Dict[str, Any]]:
        """Get collections formatted for UI display"""
        try:
            collections = await self.library_manager.get_all_collections()
            
            ui_collections = []
            for collection in collections:
                # Get item count
                items = await self.library_manager.get_collection_items(collection.id)
                
                # Get processing status
                processing_status = "idle"
                if items:
                    processing_items = [item for item in items if item.status == "processing"]
                    if processing_items:
                        processing_status = "processing"
                    elif any(item.status == "completed" for item in items):
                        processing_status = "completed"
                
                ui_collection = {
                    "id": collection.id,
                    "name": collection.name,
                    "type": collection.type,
                    "description": collection.metadata.get("description", ""),
                    "item_count": len(items),
                    "processing_status": processing_status,
                    "created_at": collection.created_at.isoformat(),
                    "updated_at": collection.updated_at.isoformat(),
                    "source_path": collection.source_path,
                    "local_path": collection.local_path,
                    "metadata": collection.metadata  # Include full metadata for is_inbox, etc.
                }
                ui_collections.append(ui_collection)
            
            return ui_collections
            
        except Exception as e:
            logger.error(f"Failed to get collections for UI: {e}")
            return []
    
    async def get_collection_items_for_ui(self, collection_id: str) -> List[Dict[str, Any]]:
        """Get collection items formatted for UI display with icons"""
        try:
            items = await self.library_manager.get_collection_items(collection_id)

            ui_items = []
            for item in items:
                # Get processing history
                history = await self.library_manager.get_processing_history(item.id)
                latest_result = history[0] if history else None

                # Get icon/thumbnail for item
                icon = await self._get_item_icon(item)

                # Format subtitle with useful info
                subtitle_parts = [item.type]
                if item.status != "pending":
                    subtitle_parts.append(item.status)
                if latest_result:
                    subtitle_parts.append(latest_result.status)
                subtitle = " • ".join(subtitle_parts)

                # Format for DetailedList (title, subtitle, icon)
                ui_item = {
                    # DetailedList required fields
                    "title": item.name,
                    "subtitle": subtitle,
                    "icon": icon,

                    # Additional data for handlers
                    "id": item.id,
                    "name": item.name,
                    "type": item.type,
                    "status": item.status,
                    "storage_type": item.storage_type,
                    "source_path": item.source_path,
                    "local_path": item.local_path,
                    "created_at": item.created_at.isoformat(),
                    "updated_at": item.updated_at.isoformat(),
                    "processing_status": latest_result.status if latest_result else "not_processed",
                    "last_workflow": latest_result.workflow if latest_result else None,
                    "last_processed": latest_result.completed_at.isoformat() if latest_result else None,

                    # For compatibility with existing code
                    "is_folder": item.type == "folder",
                    "path": item.source_path or item.local_path or "",
                    "file_path": item.local_path or item.source_path or ""
                }
                ui_items.append(ui_item)

            return ui_items

        except Exception as e:
            logger.error(f"Failed to get collection items for UI: {e}")
            return []

    async def _get_item_icon(self, item: CollectionItem):
        """
        Get icon for an item (toga.Image or None)

        Args:
            item: CollectionItem to get icon for

        Returns:
            toga.Image if thumbnail available, otherwise None
        """
        try:
            # Try to get actual thumbnail
            icon = await self.library_manager.get_item_icon(item.id, size=(64, 64))
            return icon  # toga.Image or None

        except Exception as e:
            logger.debug(f"Failed to get icon for item {item.id}: {e}")
            return None
    
    # ===== PROCESSING INTEGRATION =====
    
    async def process_collection_from_ui(self, collection_id: str, workflow: str = "default") -> bool:
        """Process collection from UI (start processing workflow)"""
        try:
            # This would integrate with your director system
            # For now, just update item statuses
            items = await self.library_manager.get_collection_items(collection_id)
            
            for item in items:
                # Update status to processing
                await self.library_manager.update_item_status(item.id, "processing")
                
                # Add processing result
                result_id = await self.library_manager.add_processing_result(
                    item_id=item.id,
                    workflow=workflow,
                    status="partial",  # Will be updated when processing completes
                    metadata={"started_from_ui": True}
                )
                
                if result_id and self.on_processing_result:
                    # Get the result and notify UI
                    history = await self.library_manager.get_processing_history(item.id)
                    latest_result = history[0] if history else None
                    if latest_result:
                        self.on_processing_result(latest_result)
            
            logger.info(f"Collection processing started from UI: {collection_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to process collection from UI: {e}")
            return False
    
    # ===== IMPORT/EXPORT =====
    
    async def export_collection_from_ui(self, collection_id: str, output_path: Path, include_files: bool = False) -> bool:
        """Export collection from UI"""
        try:
            success = await self.library_manager.export_collection(collection_id, output_path, include_files)
            
            if success:
                logger.info(f"Collection exported from UI: {output_path}")
            else:
                logger.error("Failed to export collection from UI")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to export collection from UI: {e}")
            return False
    
    async def import_collection_from_ui(self, import_path: Path, target_name: Optional[str] = None) -> bool:
        """Import collection from UI"""
        try:
            collection_id = await self.library_manager.import_collection(import_path, target_name)
            
            if collection_id:
                # Notify UI
                if self.on_collection_added:
                    collection = await self.library_manager.get_collection(collection_id)
                    if collection:
                        self.on_collection_added(collection)
                
                logger.info(f"Collection imported from UI: {collection_id}")
                return True
            else:
                logger.error("Failed to import collection from UI")
                return False
                
        except Exception as e:
            logger.error(f"Failed to import collection from UI: {e}")
            return False
    
    # ===== UTILITY METHODS =====
    
    async def get_library_stats_for_ui(self) -> Dict[str, Any]:
        """Get library statistics formatted for UI"""
        try:
            stats = await self.library_manager.get_library_stats()
            
            # Format for UI display
            ui_stats = {
                "total_collections": stats.get("total_collections", 0),
                "total_items": stats.get("total_items", 0),
                "total_processing_results": stats.get("total_processing_results", 0),
                "library_path": stats.get("library_path", "Unknown"),
                "last_updated": stats.get("last_updated", "Unknown"),
                "status": "healthy" if stats.get("total_collections", 0) > 0 else "empty"
            }
            
            return ui_stats
            
        except Exception as e:
            logger.error(f"Failed to get library stats for UI: {e}")
            return {
                "total_collections": 0,
                "total_items": 0,
                "total_processing_results": 0,
                "library_path": "Error",
                "last_updated": "Error",
                "status": "error"
            }
    
    def register_ui_callbacks(self,
                            on_collection_added: Optional[Callable[[Collection], None]] = None,
                            on_collection_updated: Optional[Callable[[Collection], None]] = None,
                            on_collection_deleted: Optional[Callable[[str], None]] = None,
                            on_item_added: Optional[Callable[[CollectionItem], None]] = None,
                            on_processing_result: Optional[Callable[[ProcessingResult], None]] = None):
        """Register UI callbacks for library events"""
        self.on_collection_added = on_collection_added
        self.on_collection_updated = on_collection_updated
        self.on_collection_deleted = on_collection_deleted
        self.on_item_added = on_item_added
        self.on_processing_result = on_processing_result
        
        logger.debug("UI callbacks registered") 