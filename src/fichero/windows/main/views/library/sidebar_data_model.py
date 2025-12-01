"""
Sidebar Data Model for Library View

Provides hierarchical organization of collections similar to Apple Mail:
- Favorites (system collections like Inbox)
- Local Collections (internal storage)
- External Collections (linked folders)
- Smart Collections (future: filter-based dynamic collections)

Each section can have its own icon, styling, and behavior.
"""

import logging
from typing import List, Dict, Any, Optional, Literal
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SidebarSection:
    """Represents a section in the sidebar"""

    id: str  # Unique identifier (e.g., "inbox", "local", "external", "smart")
    title: str  # Display title (e.g., "Inbox", "Local Collections")
    icon: Optional[str] = None  # SF Symbol name or path to PNG
    is_header: bool = True  # Whether to render as a section header
    is_expanded: bool = True  # Whether section is expanded (for future collapsible sections)
    sort_order: int = 0  # Order in sidebar (lower = higher)
    font_weight: Optional[str] = 'semibold'  # Font weight (section headers are semibold by default)
    font_style: Optional[str] = None  # Font style ('italic' for special sections)
    is_collapsible: bool = False  # Whether user can collapse this section

    def to_widget_item(self) -> Dict[str, Any]:
        """Convert section to widget item format"""
        item = {
            'text': self.title,
            'icon': self.icon,
            'subtitle': '',
            '_item_id': f'section_{self.id}',
            '_is_section_header': True,
            '_section_id': self.id,
            '_collection_data': None,
            '_can_accept_files': True,  # Sections can accept file drops (create collection)
            '_can_accept_collections': False,  # Can't drop collections on section headers
            '_is_expanded': self.is_expanded,
            # Data-driven drag & drop flags
            '_draggable': False,  # Section headers cannot be dragged
            '_can_accept_drops': False,  # Don't drop directly on section headers
            '_drop_types': [],  # Sections don't accept drops directly
        }

        # Add font styling if specified
        if self.font_weight:
            item['font_weight'] = self.font_weight
        if self.font_style:
            item['font_style'] = self.font_style

        # Add metadata for NSOutlineView hierarchy support
        item['_node_type'] = 'section'
        # Sections are always treated as having children (their collections)
        item['_has_children'] = True

        return item


@dataclass
class SidebarCollection:
    """Represents a collection in the sidebar with enhanced metadata"""

    id: str
    name: str
    type: Literal["local", "external", "url", "hybrid"]
    section_id: str  # Which section this belongs to
    item_count: int = 0
    icon: Optional[str] = None  # Custom icon (SF Symbol or path)
    icon_badge: Optional[str] = None  # Badge icon for type (e.g., "🔗" for external)
    status_icon: Optional[str] = None  # Status indicator (e.g., "⚠️" for offline)
    subtitle: Optional[str] = None  # Custom subtitle
    metadata: Dict[str, Any] = field(default_factory=dict)
    sort_order: int = 0  # Manual sort order within section
    font_weight: Optional[str] = None  # Font weight ('semibold' for inbox, 'bold' for unread)
    font_style: Optional[str] = None  # Font style ('italic' for external collections)
    trailing_icon: Optional[str] = None  # SF Symbol for status (cloud, lock, etc.)
    badge_text: Optional[str] = None  # Right-aligned numeric count (e.g., "42", "1,234")

    def to_widget_item(self, folder_icon_cache=None) -> Dict[str, Any]:
        """Convert collection to widget item format

        Args:
            folder_icon_cache: Cached folder icon to use as default

        Returns:
            Dict formatted for ListWidget with full feature support
        """
        # Determine icon to use
        icon = folder_icon_cache  # Default
        if self.icon:
            # Custom icon specified (would load SF Symbol or PNG)
            icon = self.icon

        # Build subtitle with badges (CLEAN - no count, just type badge + status)
        subtitle_parts = []

        # Add type badge emoji
        if self.icon_badge:
            subtitle_parts.append(self.icon_badge)

        # Add custom subtitle
        if self.subtitle:
            subtitle_parts.append(self.subtitle)

        # Add status icon emoji (legacy support)
        if self.status_icon:
            subtitle_parts.append(self.status_icon)

        subtitle = " • ".join(subtitle_parts) if subtitle_parts else ""

        # Determine if this collection can accept drops
        is_inbox = self.metadata.get('is_inbox', False)
        is_system = self.metadata.get('system_collection', False)

        # Build widget item with all features
        item = {
            'icon': icon,
            'text': self.name,
            'subtitle': subtitle,
            '_item_id': self.id,
            '_collection_data': {
                'id': self.id,
                'name': self.name,
                'type': self.type,
                'section_id': self.section_id,
                'item_count': self.item_count,
                'metadata': self.metadata,
                'sort_order': self.sort_order
            },
            '_can_accept_files': not (is_inbox or is_system),
            '_can_accept_collections': not (is_inbox or is_system),
            # Data-driven drag & drop flags
            '_draggable': not (is_inbox or is_system),  # Inbox and system collections not draggable
            '_can_accept_drops': not (is_inbox or is_system),  # Inbox and system collections don't accept drops
            '_drop_types': ['collection', 'folder', 'file'] if not (is_inbox or is_system) else [],
        }

        # Add badge_text (right-aligned count) if provided
        if self.badge_text:
            item['badge_text'] = self.badge_text

        # Add trailing_icon (right-side SF Symbol) if provided
        if self.trailing_icon:
            item['trailing_icon'] = self.trailing_icon

        # Add font styling if specified
        if self.font_weight:
            item['font_weight'] = self.font_weight
        if self.font_style:
            item['font_style'] = self.font_style

        # Add metadata for NSOutlineView hierarchy support
        item['_node_type'] = 'collection'
        # Will be updated to True in to_widget_data() if folders are added
        item['_has_children'] = False

        return item


@dataclass
class SidebarFolder:
    """Represents a folder within a collection in the sidebar"""

    id: str  # CollectionItem.id
    name: str
    collection_id: str
    parent_collection_name: str
    item_count: int = 0
    icon: Optional[str] = "📂"  # Open folder emoji by default
    metadata: Dict[str, Any] = field(default_factory=dict)
    sort_order: int = 0  # Manual sort order within collection
    badge_text: Optional[str] = None  # Right-aligned numeric count (cleaner than subtitle)

    def to_widget_item(self) -> Dict[str, Any]:
        """Convert folder to widget item format

        Returns:
            Dict formatted for ListWidget with badge support
        """
        # Build widget item (clean - no subtitle, use badge for count)
        item = {
            'icon': self.icon,
            'text': self.name,
            'subtitle': '',  # Keep subtitle empty for cleaner look
            '_item_id': self.id,
            '_folder_data': {
                'id': self.id,
                'name': self.name,
                'collection_id': self.collection_id,
                'parent_collection_name': self.parent_collection_name,
                'item_count': self.item_count,
                'metadata': self.metadata,
                'sort_order': self.sort_order,
                'is_folder': True  # Mark this as a folder for navigation
            },
            '_can_accept_files': True,  # Folders can accept file drops
            '_can_accept_collections': False,  # Can't drop collections into folders
            # Data-driven drag & drop flags
            '_draggable': True,  # Folders are always draggable
            '_can_accept_drops': True,  # Folders accept drops
            '_drop_types': ['file'],  # Only files, not collections
        }

        # Add badge_text (right-aligned count) if provided
        if self.badge_text:
            item['badge_text'] = self.badge_text

        # Add metadata for NSOutlineView hierarchy support
        item['_node_type'] = 'folder'
        # Folders can potentially have subfolders (not yet implemented)
        item['_has_children'] = False

        return item


class SidebarDataModel:
    """
    Hierarchical data model for library sidebar

    Organizes collections into sections similar to Apple Mail:
    - Favorites: System collections (Inbox)
    - Local Collections: Collections stored in app library
    - External Collections: Collections linked to external folders
    - Smart Collections: Filter-based dynamic collections (future)
    """

    def __init__(self):
        """Initialize sidebar data model"""
        self.sections: List[SidebarSection] = []
        self.collections: Dict[str, List[SidebarCollection]] = {}  # section_id -> collections
        self.folders: Dict[str, List[SidebarFolder]] = {}  # collection_id -> folders

        # Initialize default sections
        self._initialize_default_sections()

    def _initialize_default_sections(self):
        """Create default sidebar sections"""
        self.sections = [
            SidebarSection(
                id="favorites",
                title="Favorites",
                icon="star@10x.png",  # Star icon for Favorites
                is_header=True,
                is_expanded=True,
                sort_order=0
            ),
            SidebarSection(
                id="local",
                title="Library",
                icon="NSFolder",
                is_header=True,
                is_expanded=True,
                sort_order=1
            ),
            SidebarSection(
                id="external",
                title="External Folders",
                icon="NSFolderSmart",
                is_header=True,
                is_expanded=True,
                sort_order=2,
                font_style='italic'  # Italic to distinguish from local
            ),
            # SidebarSection(
            #     id="smart",
            #     title="Smart Collections",
            #     icon="NSFolderSmart",
            #     is_header=True,
            #     is_expanded=True,
            #     sort_order=3
            # ),
        ]

        # Initialize empty collection lists for each section
        for section in self.sections:
            self.collections[section.id] = []

    def add_collection(self, collection: SidebarCollection):
        """Add a collection to its section

        Args:
            collection: SidebarCollection to add
        """
        section_id = collection.section_id
        if section_id not in self.collections:
            logger.warning(f"Section '{section_id}' not found, adding to 'local'")
            section_id = "local"
            collection.section_id = "local"

        self.collections[section_id].append(collection)

    def remove_collection(self, collection_id: str) -> bool:
        """Remove a collection by ID

        Args:
            collection_id: ID of collection to remove

        Returns:
            True if removed, False if not found
        """
        for section_id, collections in self.collections.items():
            for i, collection in enumerate(collections):
                if collection.id == collection_id:
                    collections.pop(i)
                    return True
        return False

    def get_collection(self, collection_id: str) -> Optional[SidebarCollection]:
        """Get a collection by ID

        Args:
            collection_id: ID of collection to find

        Returns:
            SidebarCollection if found, None otherwise
        """
        for collections in self.collections.values():
            for collection in collections:
                if collection.id == collection_id:
                    return collection
        return None

    def update_collection(self, collection_id: str, **updates):
        """Update collection properties

        Args:
            collection_id: ID of collection to update
            **updates: Properties to update
        """
        collection = self.get_collection(collection_id)
        if collection:
            for key, value in updates.items():
                if hasattr(collection, key):
                    setattr(collection, key, value)

    def reorder_collection(self, collection_id: str, new_position: int, within_section: bool = True) -> bool:
        """Reorder a collection within its section or globally

        Args:
            collection_id: ID of collection to move
            new_position: New position (0-based index)
            within_section: If True, reorder within section only. If False, reorder globally.

        Returns:
            True if reordered successfully, False otherwise
        """
        collection = self.get_collection(collection_id)
        if not collection:
            return False

        if within_section:
            # Reorder within the collection's section
            section_id = collection.section_id
            collections = self.collections[section_id]

            # Find current index
            current_index = next((i for i, c in enumerate(collections) if c.id == collection_id), None)
            if current_index is None:
                return False

            # Remove and reinsert
            collections.pop(current_index)
            collections.insert(new_position, collection)

            # Update sort_order for all collections in section
            for i, col in enumerate(collections):
                col.sort_order = i

            return True
        else:
            # Global reordering not yet implemented
            logger.warning("Global collection reordering not yet implemented")
            return False

    def to_widget_data(self, folder_icon_cache=None, include_section_headers: bool = True) -> List[Dict[str, Any]]:
        """Convert model to flat list for ListWidget

        Args:
            folder_icon_cache: Cached folder icon to use for collections
            include_section_headers: Whether to include section headers in output

        Returns:
            List of dicts formatted for ListWidget
        """
        widget_data = []

        # Sort sections by sort_order
        sorted_sections = sorted(self.sections, key=lambda s: s.sort_order)
        logger.info(f"🔍 SIDEBAR MODEL: Processing {len(sorted_sections)} sections")

        for section in sorted_sections:
            section_collections = self.collections.get(section.id, [])
            logger.info(f"🔍   Section '{section.title}' (id={section.id}) has {len(section_collections)} collections")

            # Skip empty sections
            if not section_collections:
                logger.info(f"🔍     Skipping empty section '{section.title}'")
                continue

            # Sort collections by sort_order (manual) or name
            sorted_collections = sorted(section_collections, key=lambda c: (c.sort_order, c.name.lower()))

            # Build collection items with their folders as children
            collection_items = []
            for collection in sorted_collections:
                collection_item = collection.to_widget_item(folder_icon_cache)

                # Add folders as children if collection has folders
                collection_folders = self.folders.get(collection.id, [])
                if collection_folders:
                    # Sort folders by sort_order or name
                    sorted_folders = sorted(collection_folders, key=lambda f: (f.sort_order, f.name.lower()))
                    collection_item['_children'] = [folder.to_widget_item() for folder in sorted_folders]
                    collection_item['_has_children'] = True  # Mark as expandable
                    logger.debug(f"Collection '{collection.name}' has {len(collection_folders)} folders")
                else:
                    collection_item['_has_children'] = False  # No children

                collection_items.append(collection_item)

            # Add section with collections as its _children (hierarchical structure like demo)
            if include_section_headers and section.is_header:
                section_item = section.to_widget_item()
                section_item['_children'] = collection_items  # Collections are children of section
                widget_data.append(section_item)
            else:
                # If not including headers, add collections directly (flat list)
                widget_data.extend(collection_items)

        return widget_data

    @staticmethod
    def _format_count(count: int) -> str:
        """Format count for badge display

        Args:
            count: Item count

        Returns:
            Formatted string suitable for badge_text
        """
        if count == 0:
            return ''  # Don't show zero
        if count < 1000:
            return str(count)
        if count < 1_000_000:
            return f"{count:,}"  # 1,234
        return f"{count / 1_000_000:.1f}M"  # 1.2M

    def _get_trailing_icon(self, col_data: Dict[str, Any]) -> Optional[str]:
        """Determine trailing icon based on collection state

        Args:
            col_data: Collection data dict

        Returns:
            SF Symbol name for trailing icon, or None
        """
        metadata = col_data.get('metadata', {})

        # Priority order (highest to lowest):
        if metadata.get('is_locked'):
            return 'lock.fill'
        if metadata.get('sync_error'):
            return 'exclamationmark.triangle.fill'
        if metadata.get('is_syncing'):
            return 'arrow.triangle.2.circlepath'
        if metadata.get('is_synced'):
            return 'icloud.fill'
        if metadata.get('is_smart_collection'):
            return 'gearshape.fill'

        return None

    def load_from_library_data(self, collections_data: List[Dict[str, Any]]):
        """Load collections from library manager data

        Args:
            collections_data: List of collection dicts from library_manager
        """
        # DEBUG: Log what we received
        logger.info(f"🔍 LOAD: Received {len(collections_data)} collections from library")
        for c in collections_data[:10]:
            logger.info(f"🔍 LOAD INPUT: '{c.get('name')}' type='{c.get('type')}' is_inbox={c.get('metadata', {}).get('is_inbox')}")

        # Clear existing collections
        for section_id in self.collections:
            self.collections[section_id] = []

        # Map collections to sections based on type and metadata
        for col_data in collections_data:
            collection_type = col_data.get('type', 'local')
            metadata = col_data.get('metadata', {})

            # Check if this is the inbox (system collection)
            # Fallback: also check name == 'Inbox' for collections created before is_inbox flag
            collection_name = col_data.get('name', '')
            if metadata.get('is_inbox') or collection_name == 'Inbox':
                section_id = 'favorites'
            # Determine section based on type
            elif collection_type == 'local':
                section_id = 'local'
            elif collection_type in ['external', 'hybrid']:
                section_id = 'external'
            elif collection_type == 'url':
                section_id = 'external'  # URL collections go to external for now
            else:
                section_id = 'local'  # Default to local

            # Determine badges and styling
            icon_badge = self._get_type_badge(collection_type)
            status_icon = self._get_status_icon(col_data)
            trailing_icon = self._get_trailing_icon(col_data)

            # Determine font styling
            font_weight = None
            font_style = None

            # Make Inbox semibold (Mail.app style)
            if metadata.get('is_inbox'):
                font_weight = 'semibold'

            # Make external collections italic
            if collection_type in ['external', 'url', 'hybrid']:
                font_style = 'italic'

            # Format item count as badge text
            item_count = col_data.get('item_count', 0)
            badge_text = self._format_count(item_count)

            # Create SidebarCollection with all new features
            sidebar_col = SidebarCollection(
                id=col_data.get('id', ''),
                name=col_data.get('name', 'Unknown'),
                type=collection_type,
                section_id=section_id,
                item_count=item_count,
                icon=col_data.get('metadata', {}).get('icon'),  # Custom icon from metadata
                icon_badge=icon_badge,
                status_icon=status_icon,
                metadata=col_data.get('metadata', {}),
                sort_order=col_data.get('sort_order', 0),
                font_weight=font_weight,
                font_style=font_style,
                trailing_icon=trailing_icon,
                badge_text=badge_text
            )

            self.add_collection(sidebar_col)
            logger.info(f"🔍 LOAD: Added '{sidebar_col.name}' to section '{section_id}'")

    def _get_type_badge(self, collection_type: str) -> Optional[str]:
        """Get badge icon for collection type

        Args:
            collection_type: Type of collection

        Returns:
            Badge string or None
        """
        badges = {
            'local': '📁',  # Folder
            'external': '🔗',  # Link
            'url': '🌐',  # Globe
            'hybrid': '🔄',  # Arrows
        }
        return badges.get(collection_type)

    def _get_status_icon(self, col_data: Dict[str, Any]) -> Optional[str]:
        """Get status icon for collection

        Args:
            col_data: Collection data dict

        Returns:
            Status icon string or None
        """
        # Check if external path is available
        if col_data.get('type') in ['external', 'url', 'hybrid']:
            is_available = col_data.get('is_available', True)
            if not is_available:
                return '⚠️'  # Warning for offline/unavailable

        return None

    def get_section(self, section_id: str) -> Optional[SidebarSection]:
        """Get a section by ID

        Args:
            section_id: ID of section to find

        Returns:
            SidebarSection if found, None otherwise
        """
        for section in self.sections:
            if section.id == section_id:
                return section
        return None

    async def load_collection_folders(self, collection_id: str, collection_name: str, library_manager) -> int:
        """Load top-level folders for a collection

        Args:
            collection_id: ID of the collection
            collection_name: Name of the collection (for display)
            library_manager: LibraryManager instance

        Returns:
            Number of folders loaded
        """
        try:
            # Get all items in the collection
            items = await library_manager.get_collection_items(collection_id)

            # Filter to folders only (type="folder" and parent_id is None for root level)
            folders = [
                item for item in items
                if item.type == "folder" and item.parent_id is None
            ]

            logger.debug(f"Found {len(folders)} top-level folders in collection {collection_name}")

            # Convert to SidebarFolder objects
            sidebar_folders = []
            for folder in folders:
                # Count items in this folder
                folder_item_count = await library_manager.count_items_in_folder(folder.id)

                # Format count as badge text
                badge_text = self._format_count(folder_item_count)

                sidebar_folder = SidebarFolder(
                    id=folder.id,
                    name=folder.name,
                    collection_id=collection_id,
                    parent_collection_name=collection_name,
                    item_count=folder_item_count,
                    icon="📂",  # Open folder emoji
                    metadata=folder.metadata,
                    sort_order=0,  # TODO: Support custom sort order
                    badge_text=badge_text  # Clean right-aligned count
                )
                sidebar_folders.append(sidebar_folder)

            # Store folders for this collection
            self.folders[collection_id] = sidebar_folders

            return len(sidebar_folders)

        except Exception as e:
            logger.error(f"Failed to load folders for collection {collection_id}: {e}")
            self.folders[collection_id] = []
            return 0

    def add_folder(self, collection_id: str, folder: SidebarFolder):
        """Add a folder to a collection

        Args:
            collection_id: ID of the parent collection
            folder: SidebarFolder to add
        """
        if collection_id not in self.folders:
            self.folders[collection_id] = []

        self.folders[collection_id].append(folder)

    def remove_folder(self, folder_id: str) -> bool:
        """Remove a folder by ID

        Args:
            folder_id: ID of folder to remove

        Returns:
            True if removed, False if not found
        """
        for collection_id, folders in self.folders.items():
            for i, folder in enumerate(folders):
                if folder.id == folder_id:
                    folders.pop(i)
                    return True
        return False

    def get_folder(self, folder_id: str) -> Optional[SidebarFolder]:
        """Get a folder by ID

        Args:
            folder_id: ID of folder to find

        Returns:
            SidebarFolder if found, None otherwise
        """
        for folders in self.folders.values():
            for folder in folders:
                if folder.id == folder_id:
                    return folder
        return None
