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

            # Load collection icon once (reuse for all collections)
            collection_icon = None
            try:
                import toga
                folder_icon_path = self.app.paths.app / "resources" / "icons" / "files_folders" / "folder_small_icon.png"
                logger.info(f"Looking for collection icon at: {folder_icon_path}")
                logger.info(f"Icon path exists: {folder_icon_path.exists()}")
                if folder_icon_path.exists():
                    collection_icon = toga.Image(str(folder_icon_path))
                    logger.info(f"✅ Loaded collection icon: {collection_icon}")
                else:
                    logger.warning(f"❌ Collection icon not found at: {folder_icon_path}")
            except Exception as e:
                logger.error(f"Could not load collection icon: {e}", exc_info=True)

            for collection in collections:
                # Get item count
                items = self.library_manager.storage.get_collection_items(collection.id)
                item_count = len(items)

                # Create Toga DetailedList compatible data
                collection_data = {
                    # Toga DetailedList attributes
                    'title': collection.name,
                    'subtitle': f"{item_count} items • {collection.type}",
                    'icon': collection_icon,  # Collection icon from resources
                    
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
                # IMPORTANT: Set icon=None for ALL files to allow async thumbnail generation
                # The async thumbnail loader in collection_view.py will generate proper thumbnails
                # Only folders get icons immediately (handled separately)
                icon = None
                
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
                
                # Determine file path: prefer local_path (downloaded files) over source_path (URL/external)
                file_path = None
                if hasattr(item, 'local_path') and item.local_path:
                    file_path = item.local_path
                elif hasattr(item, 'source_path') and item.source_path:
                    file_path = item.source_path

                item_data = {
                    # Toga DetailedList attributes
                    'title': item.name,
                    'subtitle': " • ".join(subtitle_parts),
                    'icon': icon,

                    # Additional data for navigation/preview
                    'id': item.id,
                    'name': item.name,
                    'type': item.type,
                    'file_path': file_path,
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

            # IMPORTANT: Different behavior based on collection type
            # - External collections: Browse source_path directly (files in original location)
            # - Local/URL collections: Get items from library database
            if collection.type == "external" and collection.source_path:
                # External collection: Browse filesystem directly (files not in library)
                # Pass collection_id so we can look up library item IDs for processed files
                logger.debug(f"Browsing external collection filesystem: {collection.source_path}")
                return self._get_filesystem_structure(Path(collection.source_path), current_path, collection_id)
            else:
                # Local/URL/Hybrid collections: Get items from library database
                # Use hierarchical structure based on parent_id relationships
                logger.debug(f"Getting hierarchical items from library database for collection type: {collection.type}")
                return self._get_database_hierarchical_structure(collection_id, current_path)
                
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

    def _get_filesystem_structure(self, base_path: Path, current_relative_path: str, collection_id: str = None) -> List[Dict[str, Any]]:
        """
        Get hierarchical filesystem structure from a collection's source path

        Args:
            base_path: The collection's source path (absolute)
            current_relative_path: The current path within the collection (relative to base_path)
            collection_id: Optional collection ID to look up library item IDs for processed files

        Returns:
            List of dictionaries compatible with Toga DetailedList
        """
        try:
            # Build a mapping of source_path -> item_id for folders in this collection
            # For external collections, the collection root folder is tracked as a collection item
            # All files inherit the root folder's item_id for processing result lookup
            item_id_map = {}
            parent_folder_item_id = None  # For files in current directory

            if collection_id:
                try:
                    items = self.library_manager.storage.get_collection_items(collection_id)
                    current_path = base_path / current_relative_path if current_relative_path else base_path
                    current_path_str = str(current_path.absolute())

                    for item in items:
                        if hasattr(item, 'source_path') and item.source_path:
                            abs_path = str(Path(item.source_path).absolute())
                            item_id_map[abs_path] = item.id

                            # Check if current_path is this item OR a subdirectory of this item
                            # This allows files in subfolders to use the root folder's item_id
                            if current_path_str == abs_path or current_path_str.startswith(abs_path + '/'):
                                parent_folder_item_id = item.id
                                logger.debug(f"📊 Found parent folder item_id: {parent_folder_item_id} for path: {current_path}")
                                logger.debug(f"📊   Item source_path: {abs_path}")
                                logger.debug(f"📊   Current path: {current_path_str}")

                    logger.debug(f"Built item ID map with {len(item_id_map)} entries, parent_folder_item_id: {parent_folder_item_id}")
                except Exception as e:
                    logger.debug(f"Could not build item ID map: {e}")
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

                    # Get file type
                    file_type, _ = self._get_file_type_and_icon(entry)

                    # Get icon from library (don't generate to avoid UI freezing)
                    # IMPORTANT: Set icon=None for IMAGE files to allow async thumbnail generation
                    # Only load static folder icons here; let async loader generate all file thumbnails
                    if entry.is_dir():
                        # Get folder icon immediately (static resource)
                        icon = self.library_manager.get_filesystem_icon(entry, generate=False)
                    else:
                        # For ALL files (image and non-image), set icon=None initially
                        # The async thumbnail loader in collection_view.py will generate thumbnails for images
                        icon = None

                    # Look up library item ID for this entry
                    # For folders: check if the folder itself has an item_id
                    # For files: use the parent folder's item_id (since files inherit folder processing)
                    library_item_id = None
                    if entry.is_dir():
                        # Folders may have their own item_id if added to library
                        library_item_id = item_id_map.get(str(entry.absolute()))
                    else:
                        # Files inherit their parent folder's item_id for processing result lookup
                        library_item_id = parent_folder_item_id

                    # Create item data compatible with Toga DetailedList
                    # Note: 'path' should just be the entry name for navigation
                    # The collection view handles the full path construction
                    item_data = {
                        'id': library_item_id if library_item_id else entry.name,  # Use library ID if available, else filename
                        'title': entry.name,
                        'subtitle': self._get_item_subtitle(entry, file_type),
                        'icon': icon,  # toga.Image or None
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
    
    def _get_database_hierarchical_structure(self, collection_id: str, current_path: str = "") -> List[Dict[str, Any]]:
        """Get hierarchical structure from database using parent_id relationships

        Args:
            collection_id: The collection ID
            current_path: Current path within collection (empty for root)

        Returns:
            List of folders and files at the current level in Toga DetailedList format
        """
        try:
            # Get ALL items from database
            all_items = self.library_manager.storage.get_collection_items(collection_id)

            # Build a map of folder paths to item IDs for navigation
            folder_map = {}
            for item in all_items:
                if item.type == "folder":
                    # Store folder items by their relative path from metadata
                    rel_path = item.metadata.get('relative_path', item.name)
                    folder_map[rel_path] = item.id

            # Determine the parent_id for the current level
            target_parent_id = None
            if current_path:
                # We're in a subfolder - find the folder item for current_path
                target_parent_id = folder_map.get(current_path)
                if not target_parent_id:
                    logger.warning(f"Could not find folder item for path: {current_path}")
                    # Fallback: try to find by name
                    folder_name = current_path.split('/')[-1] if '/' in current_path else current_path
                    for item in all_items:
                        if item.type == "folder" and item.name == folder_name:
                            target_parent_id = item.id
                            logger.info(f"Found folder by name fallback: {folder_name} -> {target_parent_id}")
                            break

            # Filter items that belong at this level
            # Items belong here if their parent_id matches our target
            current_level_items = []
            for item in all_items:
                # Check if this item's parent matches what we're looking for
                if item.parent_id == target_parent_id:
                    current_level_items.append(item)

            logger.info(f"Found {len(current_level_items)} items at level '{current_path}' (parent_id={target_parent_id})")

            # Convert to Toga DetailedList format
            toga_items = []

            # Load folder icon for folders
            folder_icon = None
            try:
                import toga
                folder_icon_path = self.library_manager.app.paths.app / "resources" / "icons" / "files_folders" / "folder_small_icon.png"
                if folder_icon_path.exists():
                    folder_icon = toga.Image(str(folder_icon_path))
            except Exception as e:
                logger.debug(f"Could not load folder icon: {e}")

            for item in current_level_items:
                # Folders get icon, files get None (for async thumbnail generation)
                icon = folder_icon if item.type == "folder" else None

                # Build subtitle
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
                    except Exception:
                        pass

                # Determine file path
                file_path = None
                if hasattr(item, 'local_path') and item.local_path:
                    file_path = item.local_path
                elif hasattr(item, 'source_path') and item.source_path:
                    file_path = item.source_path

                # Build Toga DetailedList item
                item_data = {
                    'id': item.id,
                    'title': item.name,
                    'subtitle': " • ".join(subtitle_parts),
                    'icon': icon,
                    'name': item.name,
                    'type': item.type,
                    'is_folder': item.type == "folder",
                    'path': item.metadata.get('relative_path', item.name) if item.type == "folder" else None,
                    'file_path': file_path if item.type != "folder" else '',
                    'description': item.metadata.get('description', ''),
                    'created_at': item.created_at.isoformat() if item.created_at else None
                }

                toga_items.append(item_data)

            # Sort: folders first, then files, alphabetically
            toga_items.sort(key=lambda x: (not x['is_folder'], x['title'].lower()))

            logger.debug(f"Returned {len(toga_items)} hierarchical items for path '{current_path}'")
            return toga_items

        except Exception as e:
            logger.error(f"Failed to get database hierarchical structure: {e}")
            import traceback
            traceback.print_exc()
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

    # ===== DIRECTOR INTEGRATION =====

    async def process_collection(self, collection_id: str, plan_name: str,
                                workflow_name: str = "default",
                                progress_callback: Optional[callable] = None,
                                output_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Process a collection using Fichero Director

        Args:
            collection_id: ID of collection to process
            plan_name: Name of the plan to use
            workflow_name: Name of workflow within the plan
            progress_callback: Optional callback for progress updates
            output_path: Optional custom output path (defaults to library storage)

        Returns:
            Dict with processing results
        """
        try:
            logger.info(f"Starting director processing for collection {collection_id}")
            logger.info(f"Plan: {plan_name}, Workflow: {workflow_name}")
            if output_path:
                logger.info(f"Custom output path: {output_path}")

            # Get collection
            collection = await self.library_manager.get_collection(collection_id)
            if not collection:
                return {
                    'success': False,
                    'error': f"Collection {collection_id} not found"
                }

            # Get director integration service
            if not hasattr(self.library_manager, 'director_integration'):
                return {
                    'success': False,
                    'error': "Director integration not available"
                }

            # Convert output path to Path object if provided
            output_base_path = Path(output_path) if output_path else None

            # Process through director
            result = await self.library_manager.director_integration.process_collection(
                collection_id=collection_id,
                plan_name=plan_name,
                workflow_name=workflow_name,
                progress_callback=progress_callback,
                output_base_path=output_base_path
            )

            logger.info(f"Director processing completed: {result.get('success', False)}")
            return result

        except Exception as e:
            logger.error(f"Failed to process collection: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }

    def process_collection_sync(self, collection_id: str, plan_name: str,
                               workflow_name: str = "default") -> Dict[str, Any]:
        """Synchronous wrapper for process_collection"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.process_collection(collection_id, plan_name, workflow_name)
                )
                return result
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Failed to process collection sync: {e}")
            return {'success': False, 'error': str(e)}

    async def get_available_plans(self) -> List[Dict[str, Any]]:
        """Get list of available processing plans"""
        try:
            # Get plan manager from director
            if hasattr(self.library_manager, 'director_integration'):
                director = self.library_manager.director_integration.director
                if hasattr(director, 'plan_manager'):
                    plans = director.plan_manager.get_all_plans()
                    return [
                        {
                            'name': name,
                            'title': plan.get('title', name),
                            'description': plan.get('description', ''),
                            'workflows': list(plan.get('workflows', {}).keys())
                        }
                        for name, plan in plans.items()
                    ]

            return []
        except Exception as e:
            logger.error(f"Failed to get available plans: {e}")
            return []

    def get_available_plans_sync(self) -> List[Dict[str, Any]]:
        """Synchronous wrapper for get_available_plans"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(self.get_available_plans())
                return result
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Failed to get plans sync: {e}")
            return []
