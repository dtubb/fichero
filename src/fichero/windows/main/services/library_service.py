"""
Library Service for Fichero GUI

Handles all library operations for the GUI, providing a clean interface
between the UI and the LibraryManager. This service layer eliminates
duplication and provides proper async handling.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from fichero.library.library_manager import LibraryManager
from fichero.library.models import Collection, CollectionItem

logger = logging.getLogger(__name__)


class LibraryService:
    """Service layer for library operations in the GUI"""
    
    def __init__(self, library_manager: LibraryManager):
        """Initialize library service with library manager"""
        self.library_manager = library_manager
        logger.info("Library service initialized")
    
    # ===== COLLECTION OPERATIONS =====
    
    async def get_collections_for_ui(self, sort_by: str = "manual") -> List[Dict[str, Any]]:
        """Get all collections formatted for UI display with sorting

        Args:
            sort_by: Sort mode - "manual", "name", "date_created", "date_updated", "type"
        """
        try:
            # Get collections with requested sort mode
            collections = await self.library_manager.get_all_collections(sort_by=sort_by)

            # Convert to UI format
            ui_collections = []
            for collection in collections:
                # Get item count
                items = await self.library_manager.get_collection_items(collection.id)
                item_count = len(items)

                collection_data = {
                    'id': collection.id,
                    'name': collection.name,
                    'type': collection.type,
                    'item_count': item_count,
                    'description': collection.metadata.get('description', ''),
                    'created_at': collection.created_at,
                    'updated_at': collection.updated_at,
                    'source_path': collection.source_path,
                    'local_path': collection.local_path,
                    'sort_order': collection.sort_order,
                    'status': self._get_collection_status(collection),
                    'source_type': collection.type  # Alias for compatibility
                }
                ui_collections.append(collection_data)

            # Collections are already sorted by library_manager based on sort_by parameter
            logger.debug(f"Retrieved {len(ui_collections)} collections for UI (sorted by {sort_by})")
            return ui_collections

        except Exception as e:
            logger.error(f"Failed to get collections for UI: {e}")
            return []
    
    async def get_collection_items_for_ui(self, collection_id: str) -> List[Dict[str, Any]]:
        """Get collection items formatted for UI display"""
        try:
            items = await self.library_manager.get_collection_items(collection_id)
            
            # Convert to UI format
            ui_items = []
            for item in items:
                item_data = {
                    'id': item.id,
                    'name': item.name,
                    'type': item.type,
                    'status': item.status,
                    'source_path': item.source_path,
                    'local_path': item.local_path,
                    'created_at': item.created_at,
                    'updated_at': item.updated_at,
                    'metadata': item.metadata
                }
                ui_items.append(item_data)
            
            logger.debug(f"Retrieved {len(ui_items)} items for collection {collection_id}")
            return ui_items
            
        except Exception as e:
            logger.error(f"Failed to get collection items for UI: {e}")
            return []
    
    async def add_collection_for_ui(self, 
                                  name: str,
                                  collection_type: str,
                                  source_path: Optional[str] = None,
                                  description: str = "") -> Optional[str]:
        """Add a new collection from UI"""
        try:
            collection_id = await self.library_manager.add_collection(
                name=name,
                collection_type=collection_type,
                source_path=source_path,
                description=description
            )
            
            if collection_id:
                logger.info(f"Added collection '{name}' with ID: {collection_id}")
            else:
                logger.error(f"Failed to add collection '{name}'")
            
            return collection_id
            
        except Exception as e:
            logger.error(f"Failed to add collection '{name}': {e}")
            return None
    
    async def delete_collection_for_ui(self, collection_id: str) -> bool:
        """Delete a collection from UI"""
        try:
            success = await self.library_manager.delete_collection(collection_id)

            if success:
                logger.info(f"Deleted collection with ID: {collection_id}")
            else:
                logger.error(f"Failed to delete collection with ID: {collection_id}")

            return success

        except Exception as e:
            logger.error(f"Failed to delete collection {collection_id}: {e}")
            return False

    async def reorder_collection_for_ui(self, collection_id: str, new_position: int) -> bool:
        """Reorder a collection to a new position from UI

        Args:
            collection_id: ID of collection to move
            new_position: New position (1-based index)
        """
        try:
            success = await self.library_manager.reorder_collection(collection_id, new_position)

            if success:
                logger.info(f"Reordered collection {collection_id} to position {new_position}")
            else:
                logger.error(f"Failed to reorder collection {collection_id}")

            return success

        except Exception as e:
            logger.error(f"Failed to reorder collection {collection_id}: {e}")
            return False
    
    async def add_item_to_collection_for_ui(self,
                                          collection_id: str,
                                          item_type: str,
                                          source: str,
                                          name: str,
                                          operation: str = "link") -> Optional[str]:
        """Add an item to a collection from UI"""
        try:
            item_id = await self.library_manager.add_item_to_collection(
                collection_id=collection_id,
                item_type=item_type,
                source=source,
                name=name,
                operation=operation
            )
            
            if item_id:
                logger.info(f"Added item '{name}' to collection {collection_id}")
            else:
                logger.error(f"Failed to add item '{name}' to collection {collection_id}")
            
            return item_id
            
        except Exception as e:
            logger.error(f"Failed to add item '{name}' to collection {collection_id}: {e}")
            return None
    
    # ===== SYNC WRAPPERS FOR UI =====
    
    def get_collections_sync(self) -> List[Dict[str, Any]]:
        """Synchronous wrapper for get_collections_for_ui - returns Toga DetailedList compatible format"""
        try:
            # Call the library manager directly (it has sync methods)
            collections = self.library_manager.storage.get_all_collections()
            
            # Convert to Toga DetailedList format
            toga_collections = []
            for collection in collections:
                # Get item count
                items = self.library_manager.storage.get_collection_items(collection.id)
                item_count = len(items)
                
                # Create Toga DetailedList compatible data
                collection_data = {
                    # Toga DetailedList attributes
                    'title': collection.name,
                    'subtitle': f"{item_count} items • {collection.type}",
                    'icon': "📁",  # Collection icon
                    
                    # Additional data for navigation
                    'id': collection.id,
                    'name': collection.name,
                    'type': collection.type,
                    'item_count': item_count,
                    'created_at': collection.created_at.isoformat() if collection.created_at else None,
                    'description': collection.metadata.get('description', f"Collection with {item_count} items")
                }
                
                toga_collections.append(collection_data)
            
            # Sort by title (name)
            toga_collections.sort(key=lambda x: x.get('title', ''))
            
            logger.debug(f"Returned {len(toga_collections)} collections in Toga format")
            return toga_collections
            
        except Exception as e:
            logger.error(f"Failed to get collections sync: {e}")
            return []
    
    def get_collection_items_sync(self, collection_id: str) -> List[Dict[str, Any]]:
        """Synchronous wrapper for get_collection_items_for_ui - returns Toga DetailedList compatible format"""
        try:
            # Get collection info
            collection = self.library_manager.storage.get_collection(collection_id)
            if not collection:
                logger.warning(f"Collection {collection_id} not found")
                return []
            
            # Get items from storage
            items = self.library_manager.storage.get_collection_items(collection_id)
            
            # Convert to Toga DetailedList format
            toga_items = []
            for item in items:
                # Determine icon based on item type
                if hasattr(item, 'source_path') and item.source_path:
                    file_path = Path(item.source_path)
                    if file_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif']:
                        icon = "🖼️"
                    elif file_path.suffix.lower() in ['.txt', '.md']:
                        icon = "📄" 
                    elif file_path.suffix.lower() in ['.pdf']:
                        icon = "📕"
                    else:
                        icon = "📎"
                else:
                    icon = "📄"
                
                # Create subtitle with size info if available
                subtitle_parts = [item.type or "File"]
                if hasattr(item, 'source_path') and item.source_path:
                    try:
                        file_path = Path(item.source_path)
                        if file_path.exists():
                            size = file_path.stat().st_size
                            if size > 1024 * 1024:
                                subtitle_parts.append(f"{size / (1024*1024):.1f} MB")
                            elif size > 1024:
                                subtitle_parts.append(f"{size / 1024:.1f} KB")
                            else:
                                subtitle_parts.append(f"{size} B")
                    except Exception:
                        pass
                
                item_data = {
                    # Toga DetailedList attributes
                    'title': item.name,
                    'subtitle': " • ".join(subtitle_parts),
                    'icon': icon,
                    
                    # Additional data for navigation/preview
                    'id': item.id,
                    'name': item.name,
                    'type': item.type,
                    'file_path': getattr(item, 'source_path', None),
                    'description': item.metadata.get('description', ""),
                    'created_at': item.created_at.isoformat() if item.created_at else None
                }
                
                toga_items.append(item_data)
            
            # Sort by title (name)
            toga_items.sort(key=lambda x: x.get('title', ''))
            
            logger.debug(f"Returned {len(toga_items)} items for collection {collection_id} in Toga format")
            return toga_items
            
        except Exception as e:
            logger.error(f"Failed to get collection items sync: {e}")
            return []

    def get_collection_structure_sync(self, collection_id: str, current_path: str = "") -> List[Dict[str, Any]]:
        """Get hierarchical collection structure for GUI navigation
        
        Args:
            collection_id: The collection ID
            current_path: Current path within collection (empty for root)
            
        Returns:
            List of folders and files in Toga DetailedList format
        """
        try:
            # Get collection info
            collection = self.library_manager.storage.get_collection(collection_id)
            if not collection:
                logger.warning(f"Collection {collection_id} not found")
                return []
            
            # Use source_path (for imported collections) or local_path
            collection_path = collection.source_path or collection.local_path
            if collection_path:
                return self._get_filesystem_structure(Path(collection_path), current_path)
            else:
                # Fall back to flat items if no filesystem structure
                return self.get_collection_items_sync(collection_id)
                
        except Exception as e:
            logger.error(f"Failed to get collection structure sync: {e}")
            return []
    
    def _get_file_type_and_icon(self, file_path: Path) -> tuple[str, None]:
        """Determine file type (icon will be generated by icon_generator if needed)"""
        if file_path.is_dir():
            return "folder", None

        # Get file extension
        suffix = file_path.suffix.lower()

        # File type mapping (no icons - use icon_generator for actual thumbnails)
        type_mapping = {
            # Images
            '.jpg': 'image',
            '.jpeg': 'image',
            '.png': 'image',
            '.gif': 'image',
            '.bmp': 'image',
            '.tiff': 'image',
            '.webp': 'image',

            # Documents
            '.pdf': 'document',
            '.doc': 'document',
            '.docx': 'document',
            '.txt': 'text',
            '.rtf': 'document',
            '.odt': 'document',

            # Spreadsheets
            '.xls': 'spreadsheet',
            '.xlsx': 'spreadsheet',
            '.csv': 'spreadsheet',
            '.ods': 'spreadsheet',

            # Presentations
            '.ppt': 'presentation',
            '.pptx': 'presentation',
            '.odp': 'presentation',

            # Archives
            '.zip': 'archive',
            '.rar': 'archive',
            '.7z': 'archive',
            '.tar': 'archive',
            '.gz': 'archive',

            # Audio
            '.mp3': 'audio',
            '.wav': 'audio',
            '.flac': 'audio',
            '.aac': 'audio',
            '.ogg': 'audio',

            # Video
            '.mp4': 'video',
            '.avi': 'video',
            '.mkv': 'video',
            '.mov': 'video',
            '.wmv': 'video',

            # Code
            '.py': 'code',
            '.js': 'code',
            '.html': 'code',
            '.css': 'code',
            '.json': 'code',
            '.xml': 'code',
            '.yml': 'code',
            '.yaml': 'code',
        }

        return type_mapping.get(suffix, 'file'), None

    def _get_filesystem_structure(self, base_path: Path, current_relative_path: str) -> List[Dict[str, Any]]:
        """
        Get hierarchical filesystem structure from a collection's source path
        
        Args:
            base_path: The collection's source path (absolute)
            current_relative_path: The current path within the collection (relative to base_path)
        
        Returns:
            List of dictionaries compatible with Toga DetailedList
        """
        try:
            # Determine the actual path to scan
            if current_relative_path:
                current_path = base_path / current_relative_path
            else:
                current_path = base_path
            
            if not current_path.exists() or not current_path.is_dir():
                logger.warning(f"Path does not exist or is not a directory: {current_path}")
                return []
            
            items = []
            
            # Note: Back navigation is now handled by toolbar back button
            # No need for ".." entry in the list
            
            # Get all items in the current directory
            try:
                entries = list(current_path.iterdir())
                # Sort: directories first, then files, alphabetically within each group
                entries.sort(key=lambda x: (not x.is_dir(), x.name.lower()))
            except PermissionError:
                logger.warning(f"Permission denied accessing: {current_path}")
                return items
            
            for entry in entries:
                try:
                    # Skip hidden files (starting with .)
                    if entry.name.startswith('.') and entry.name not in ['..']:
                        continue
                    
                    # Get file type and icon
                    file_type, icon = self._get_file_type_and_icon(entry)
                    
                    # Create item data compatible with Toga DetailedList
                    # Note: 'path' should just be the entry name for navigation
                    # The collection view handles the full path construction
                    item_data = {
                        'id': entry.name,
                        'title': entry.name,
                        'subtitle': self._get_item_subtitle(entry, file_type),
                        'icon': icon,
                        'type': file_type,
                        'is_folder': entry.is_dir(),
                        'path': entry.name,  # Just the name, not full path
                        'file_path': str(entry.absolute()) if entry.is_file() else ''
                    }
                    
                    items.append(item_data)
                    
                except (OSError, PermissionError) as e:
                    logger.warning(f"Cannot access {entry}: {e}")
                    continue
            
            logger.debug(f"Generated {len(items)} items for path: {current_path}")
            return items
            
        except Exception as e:
            logger.error(f"Failed to get filesystem structure: {e}")
            return []
    
    def _get_item_subtitle(self, path: Path, file_type: str) -> str:
        """Generate subtitle for an item"""
        try:
            if path.is_dir():
                # Count items in directory
                try:
                    item_count = len(list(path.iterdir()))
                    return f"Folder • {item_count} items"
                except PermissionError:
                    return "Folder • Access denied"
            else:
                # File size and type
                try:
                    size = path.stat().st_size
                    if size < 1024:
                        size_str = f"{size} B"
                    elif size < 1024 * 1024:
                        size_str = f"{size / 1024:.1f} KB"
                    elif size < 1024 * 1024 * 1024:
                        size_str = f"{size / (1024 * 1024):.1f} MB"
                    else:
                        size_str = f"{size / (1024 * 1024 * 1024):.1f} GB"
                    
                    return f"{file_type.title()} • {size_str}"
                except OSError:
                    return f"{file_type.title()}"
        except Exception:
            return "Unknown"
    
    def add_collection_sync(self, 
                           name: str,
                           collection_type: str,
                           source_path: Optional[str] = None,
                           description: str = "") -> Optional[str]:
        """Synchronous wrapper for add_collection_for_ui"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.add_collection_for_ui(
                    name, collection_type, source_path, description
                ))
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Failed to add collection sync: {e}")
            return None
    
    def delete_collection_sync(self, collection_id: str) -> bool:
        """Synchronous wrapper for delete_collection_for_ui"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.delete_collection_for_ui(collection_id))
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Failed to delete collection sync: {e}")
            return False
    
    # ===== HELPER METHODS =====
    
    def _get_collection_status(self, collection: Collection) -> str:
        """Get status string for a collection"""
        try:
            if collection.local_path and Path(collection.local_path).exists():
                return "Available"
            elif collection.type == "url":
                return "URL Collection"
            elif collection.type == "external":
                return "External"
            else:
                return "Unknown"
        except Exception:
            return "Unknown"
    
    def get_collections_sync(self) -> List[Dict[str, Any]]:
        """Synchronous wrapper for get_collections_for_ui"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.get_collections_for_ui())
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Failed to get collections sync: {e}")
            return []
    
    def get_library_stats(self) -> Dict[str, Any]:
        """Get library statistics"""
        try:
            # This would be async in the real implementation
            # For now, return basic stats
            return {
                'total_collections': 0,  # Would be calculated from library_manager
                'total_items': 0,       # Would be calculated from library_manager
                'status': 'Ready'
            }
        except Exception as e:
            logger.error(f"Failed to get library stats: {e}")
            return {'status': 'Error', 'error': str(e)}
