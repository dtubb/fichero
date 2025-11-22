"""
Platform-adaptive list widget with source-based architecture and extensible renderer system.

This is the new implementation that uses Toga Sources (ListSource/TreeSource) for
uniform data management and selection handling across all widget types.
"""

import logging
import sys
from typing import Any, Callable, Optional, List, Dict
from enum import Enum

import toga
from toga.sources import ListSource, TreeSource
from toga.style.pack import Pack

from .renderers import Renderer
from .renderers.native import NativeRenderer
from .renderers.card import CardRenderer
from .renderers.html import HTMLRenderer
from .renderers.sidebar import SidebarRenderer

# Conditional import for macOS native sidebar
try:
    from .renderers.macos_sidebar import MacOSSidebarRenderer, RUBICON_AVAILABLE
except ImportError:
    RUBICON_AVAILABLE = False
    MacOSSidebarRenderer = None


logger = logging.getLogger(__name__)


class Platform(Enum):
    """Platform types for widget selection."""
    MACOS = "macOS"
    LINUX = "Linux"
    WINDOWS = "Windows"
    IOS = "iOS"
    ANDROID = "Android"


class ListWidget:
    """
    Platform-adaptive list widget with source-based architecture.

    Key features:
    - Manages ListSource/TreeSource internally
    - Uniform Row object selection across all widget types
    - Extensible renderer system (Native, HTML, Card, etc.)
    - Multiple rendering styles per renderer type
    - Platform-adaptive widget selection

    Automatically selects the appropriate widget based on platform:
    - Desktop (macOS/Linux/Windows): toga.Table for flat lists
    - Mobile (iOS/Android): toga.DetailedList for touch-optimized lists
    - Hierarchical (when hierarchical=True): toga.Tree for tree data
    """

    def __init__(
        self,
        headings: List[str],
        data: Optional[List[Dict[str, Any]]] = None,
        on_select: Optional[Callable] = None,
        on_activate: Optional[Callable] = None,
        multiple_select: bool = False,
        style: Optional[Pack] = None,
        renderer: str = 'native',
        renderer_style: str = 'default',
        force_widget_type: Optional[str] = None,  # 'table', 'tree', or 'detailedlist' for testing
        navigable: bool = False,  # Enable folder navigation
        on_navigate: Optional[Callable] = None,  # Called when path changes: on_navigate(new_path)
        app: Optional[Any] = None,  # App instance for SelectionManager access
        view_id: Optional[str] = None,  # View context ('library', 'collection', 'preview')
    ):
        """
        Initialize the list widget.

        Args:
            headings: Column headings for the widget
            data: Initial data (list of dicts with 'icon', 'text', 'children' keys)
                  For navigable lists, items should have 'path' and 'is_folder' properties
            on_select: Callback when item is selected (receives selected item)
            on_activate: Callback when item is activated/double-clicked
            multiple_select: Whether to allow multiple selection
            style: Toga Pack style for the widget
            renderer: Renderer type ('native', 'html', 'card')
            renderer_style: Rendering style ('default', 'compact', 'detailed')
            force_widget_type: Force specific widget type for testing ('table', 'tree', 'detailedlist')
            navigable: Enable folder navigation (filters data by current_path)
            on_navigate: Callback when navigation path changes (receives new path)
            app: App instance for SelectionManager access
            view_id: View context for SelectionManager ('library', 'collection', 'preview')
        """
        logger.info(f"🎬 ListWidget.__init__: renderer={renderer}, navigable={navigable}, data_count={len(data) if data else 0}")
        if data:
            logger.info(f"🎬   Sample data paths: {[item.get('path', 'NO_PATH') for item in data[:3]]}")

        self.headings = headings
        self._all_data = data or []  # Store all data (including nested items)
        self._data = data or []  # Current view data (filtered by path if navigable)
        self._on_select_callback = on_select
        self._on_activate = on_activate
        self._on_navigate_callback = on_navigate
        self.multiple_select = multiple_select
        self.toga_style = style or Pack(flex=1)
        self.force_widget_type = force_widget_type

        # SelectionManager integration
        self.app = app
        self.view_id = view_id

        # Navigation state
        self.navigable = navigable
        self.current_path = ""  # Empty string = root level

        # Double-click detection for Table/DetailedList (since on_activate doesn't work on macOS Table)
        self._last_click_time = 0
        self._last_clicked_item_id = None
        self._double_click_threshold = 0.5  # 500ms

        # Source management
        self._source = None  # Will be ListSource or TreeSource
        self._renderer_type = renderer
        self._renderer_style = renderer_style

        # Platform detection and renderer creation
        self.platform = self._detect_platform()
        logger.info(f"🎬 Platform detected: {self.platform.value}")

        self.renderer = self._create_renderer()
        logger.info(f"🎬 Renderer created: {type(self.renderer).__name__}, widget_type={getattr(self.renderer, 'widget_type', 'N/A')}")

        # Create widget via renderer
        self.widget = self.renderer.create_widget()
        logger.info(f"🎬 Widget created: {type(self.widget).__name__}")

        # Ensure widget always fills available space
        # When parent has fixed width, Toga defaults to minimum height
        # Explicitly set flex=1 to fill container height
        if not self.widget.style:
            self.widget.style = Pack(flex=1)
        else:
            self.widget.style.flex = 1
            # If width is set but height isn't, ensure height fills container
            if hasattr(self.widget.style, 'width') and self.widget.style.width:
                # Width is fixed, ensure height is flexible
                if hasattr(self.widget.style, 'height'):
                    del self.widget.style.height

        # For Tree widgets: don't filter, use all data to build hierarchy
        # For Table/DetailedList: filter by current path for flat navigation
        is_tree_widget = (hasattr(self.renderer, 'widget_type') and
                         self.renderer.widget_type == 'tree')

        if self.navigable and not is_tree_widget:
            # Flat navigation (Table/DetailedList): filter by path
            self._data = self._filter_items_by_path(self.current_path)
            logger.info(f"🎬 Filtered to {len(self._data)} items at path '{self.current_path}' (flat navigation)")
        elif is_tree_widget:
            # Tree navigation: use ALL data, conversion will build hierarchy
            logger.info(f"🎬 Using all {len(self._data)} items for tree hierarchy")

        # Populate with initial data
        if self._data:
            self.set_data(self._data)

        logger.debug(
            f"ListWidget created: platform={self.platform.value}, "
            f"renderer={self._renderer_type}, widget_type={type(self.widget).__name__}"
        )

    def _detect_platform(self) -> Platform:
        """Detect the current platform."""
        import os

        # First check for FORCE_MOBILE_UI environment variable (for testing)
        env_mobile = os.environ.get('FORCE_MOBILE_UI')
        if env_mobile is not None:
            is_mobile = env_mobile.lower() in ('true', '1', 'yes', 'on')
            if is_mobile:
                logger.info("FORCE_MOBILE_UI=true detected, using mobile platform")
                # Return iOS for mobile simulation on macOS
                platform_str = sys.platform
                if platform_str == "darwin":
                    return Platform.IOS
                elif platform_str == "linux":
                    return Platform.ANDROID
                else:
                    return Platform.IOS  # Default mobile

        platform_str = sys.platform

        if platform_str == "darwin":
            # Check if iOS (via toga backend detection)
            try:
                import toga
                backend_name = toga.platform.current_platform
                if "ios" in backend_name.lower():
                    return Platform.IOS
            except:
                pass
            return Platform.MACOS
        elif platform_str == "win32":
            return Platform.WINDOWS
        elif platform_str == "linux":
            return Platform.LINUX
        elif "android" in platform_str.lower():
            return Platform.ANDROID
        else:
            # Default to Linux for unknown platforms
            logger.warning(f"Unknown platform '{platform_str}', defaulting to Linux")
            return Platform.LINUX

    def _create_renderer(self) -> Renderer:
        """Create the appropriate renderer based on renderer_type."""
        # Native renderer types: native, tree, table, detailedlist
        if self._renderer_type in ('native', 'tree', 'table', 'detailedlist'):
            # Map renderer type to widget type
            if self._renderer_type == 'tree':
                widget_type = 'tree'
            elif self._renderer_type == 'table':
                widget_type = 'table'
            elif self._renderer_type == 'detailedlist':
                widget_type = 'detailedlist'
            elif self.force_widget_type:
                widget_type = self.force_widget_type.lower()
                logger.info(f"🔧 FORCING {widget_type} widget (test mode)")
            else:
                # Normal platform-based selection for 'native'
                if self.platform == Platform.MACOS or self.platform == Platform.LINUX:
                    widget_type = 'tree'  # Mac/Linux uses Tree for hierarchical navigation
                elif self.platform == Platform.WINDOWS:
                    widget_type = 'table'  # Windows uses Table for flat lists
                else:  # iOS, Android
                    widget_type = 'detailedlist'  # Mobile uses DetailedList

            return NativeRenderer(
                headings=self.headings,
                on_select=self._handle_select,
                on_activate=self._handle_activate,
                style=self._renderer_style,
                platform=self.platform.value,
                widget_type=widget_type,
                multiple_select=self.multiple_select,
                toga_style=self.toga_style,
            )
        elif self._renderer_type == 'html':
            logger.debug("Creating HTMLRenderer")
            return HTMLRenderer(
                headings=self.headings,
                on_select=self._handle_select,
                style=self._renderer_style,
                platform=self.platform.value,
                toga_style=self.toga_style,
                on_navigate_back=self.navigate_up if self.navigable else None,
            )
        elif self._renderer_type == 'card':
            logger.debug("Creating CardRenderer")
            return CardRenderer(
                headings=self.headings,
                on_select=self._handle_select,
                style=self._renderer_style,
                platform=self.platform.value,
                toga_style=self.toga_style,
                multiple_select=self.multiple_select,
                on_navigate_back=self.navigate_up if self.navigable else None,
            )
        elif self._renderer_type == 'sidebar':
            # Use native macOS sidebar if available and on macOS platform
            use_native_macos = (
                self.platform == Platform.MACOS and
                RUBICON_AVAILABLE and
                MacOSSidebarRenderer is not None
            )

            if use_native_macos:
                logger.info("Creating MacOSSidebarRenderer (native NSOutlineView)")
                try:
                    return MacOSSidebarRenderer(
                        headings=self.headings,
                        on_select=self._handle_select,
                        style=self._renderer_style,
                    )
                except Exception as e:
                    logger.warning(f"Failed to create MacOSSidebarRenderer: {e}. Falling back to Canvas SidebarRenderer")
                    # Fall through to create regular SidebarRenderer

            # Use Canvas-based SidebarRenderer (cross-platform fallback)
            logger.debug("Creating SidebarRenderer (Canvas-based)")
            return SidebarRenderer(
                headings=self.headings,
                on_select=self._handle_select,
                style=self._renderer_style,
                platform=self.platform.value,
                toga_style=self.toga_style,
                multiple_select=self.multiple_select,
            )
        else:
            raise ValueError(f"Unknown renderer type: {self._renderer_type}")

    def _convert_flat_to_tree(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert flat path-based data to hierarchical tree structure with children.

        Input format:
        [
            {'text': 'Folder1', 'path': 'Folder1', 'is_folder': True, ...},
            {'text': 'File1', 'path': 'Folder1/File1', 'is_folder': False, ...},
            {'text': 'Folder2', 'path': 'Folder1/Folder2', 'is_folder': True, ...},
            {'text': 'File2', 'path': 'Folder1/Folder2/File2', 'is_folder': False, ...},
        ]

        Output format:
        [
            {
                'text': 'Folder1', 'path': 'Folder1', 'is_folder': True, ...,
                'children': [
                    {'text': 'File1', 'path': 'Folder1/File1', 'is_folder': False, ...},
                    {
                        'text': 'Folder2', 'path': 'Folder1/Folder2', 'is_folder': True, ...,
                        'children': [
                            {'text': 'File2', 'path': 'Folder1/Folder2/File2', 'is_folder': False, ...},
                        ]
                    }
                ]
            }
        ]

        Args:
            data: Flat list with 'path' property

        Returns:
            Hierarchical list with 'children' property
        """
        if not data:
            logger.info("🌳 _convert_flat_to_tree: No data to convert")
            return []

        logger.info(f"🌳 _convert_flat_to_tree: Converting {len(data)} flat items to tree")
        logger.debug(f"🌳 Sample paths: {[item.get('path', '') for item in data[:5]]}")

        # Build a path -> item mapping
        path_to_item = {}
        for item in data:
            path = item.get('path', '')
            # Create a copy to avoid mutating original data
            item_copy = dict(item)
            item_copy['children'] = []
            path_to_item[path] = item_copy
            logger.debug(f"🌳   Item: '{item.get('text', 'NO TEXT')}' path='{path}' is_folder={item.get('is_folder', False)}")

        # Build hierarchy by assigning children to parents
        root_items = []
        for path, item in path_to_item.items():
            if not path or '/' not in path:
                # Root level item
                root_items.append(item)
                logger.debug(f"🌳   ROOT: '{item.get('text', 'NO TEXT')}' path='{path}'")
            else:
                # Find parent path
                parent_path = path.rsplit('/', 1)[0]
                if parent_path in path_to_item:
                    path_to_item[parent_path]['children'].append(item)
                    logger.debug(f"🌳   CHILD: '{item.get('text', 'NO TEXT')}' → parent '{parent_path}'")
                else:
                    # Parent not found, treat as root
                    root_items.append(item)
                    logger.warning(f"🌳   ORPHAN: '{item.get('text', 'NO TEXT')}' parent '{parent_path}' not found, treating as root")

        # Clean up empty children arrays
        def clean_empty_children(items):
            for item in items:
                if 'children' in item:
                    if not item['children']:
                        del item['children']
                    else:
                        clean_empty_children(item['children'])

        clean_empty_children(root_items)

        logger.info(f"🌳 Converted {len(data)} flat items to {len(root_items)} root items with hierarchy")

        # Log structure summary
        def count_children(items):
            total = 0
            for item in items:
                if 'children' in item:
                    total += len(item['children'])
                    total += count_children(item['children'])
            return total

        total_children = count_children(root_items)
        logger.info(f"🌳 Tree structure: {len(root_items)} roots, {total_children} total descendants")

        return root_items

    def set_data(self, data: List[Dict[str, Any]]) -> None:
        """
        Update the widget's data using source-based architecture.

        This is the key method that implements the source-based approach:
        1. Convert app data to source format (via renderer)
        2. Create or update the ListSource or TreeSource (based on widget type)
        3. Attach source to widget (widgets auto-update)

        Args:
            data: New data in app format (see renderer's convert_to_source_format)
        """
        self._data = data

        # For Tree widgets, convert flat path-based data to hierarchical structure
        is_tree_widget = (hasattr(self.renderer, 'widget_type') and
                         self.renderer.widget_type == 'tree')

        logger.info(f"📊 set_data: Received {len(data)} items, is_tree_widget={is_tree_widget}")

        if is_tree_widget and data and any('path' in item for item in data):
            # Convert flat data with 'path' property to hierarchical with 'children'
            logger.info("📊 set_data: Converting flat path-based data to tree hierarchy")
            data = self._convert_flat_to_tree(data)
            logger.info(f"📊 set_data: After conversion, have {len(data)} root items")
        elif is_tree_widget:
            logger.info("📊 set_data: Tree widget but no path-based data detected")

        # Convert to source format via renderer
        logger.info(f"📊 set_data: Converting to source format via renderer")
        source_data = self.renderer.convert_to_source_format(data)
        logger.info(f"📊 set_data: Source conversion complete, got {len(source_data) if isinstance(source_data, list) else 'non-list'} items")

        # Determine if we need TreeSource (for Tree widgets) or ListSource
        is_tree_widget = (hasattr(self.renderer, 'widget_type') and
                         self.renderer.widget_type == 'tree')

        # Check if renderer uses native source or handles raw data
        if not self.renderer.uses_native_source:
            # Custom renderers (Card, HTML) handle raw data directly
            logger.debug(f"Passing raw data to custom renderer ({len(source_data)} items)")

            # Pass current path to renderer for header display
            if hasattr(self.renderer, 'current_path'):
                self.renderer.current_path = self.current_path

            self.renderer.attach_source(source_data)
        else:
            # Native renderers use ListSource/TreeSource
            # ALWAYS recreate source - Toga doesn't properly refresh when using clear()/append()
            accessors = self.renderer.get_accessors(self.headings)

            if is_tree_widget:
                logger.debug(f"Creating new TreeSource with accessors: {accessors}, {len(source_data)} items")
                self._source = TreeSource(accessors=accessors, data=source_data)
            else:
                logger.debug(f"Creating new ListSource with accessors: {accessors}, {len(source_data)} items")
                self._source = ListSource(accessors=accessors, data=source_data)

            # Always re-attach the new source to the widget
            self.renderer.attach_source(self._source)

    def update_width(self) -> None:
        """
        Notify renderer that container width has changed.

        Call this method after changing the container's width to allow
        renderers (Card, Sidebar) to recalculate their layout.
        """
        renderer_name = self.renderer.__class__.__name__
        logger.debug(f"update_width() called for renderer: {renderer_name}")

        # Card renderer has update_container_width method
        if hasattr(self.renderer, 'update_container_width'):
            width = self.renderer._get_container_width()
            if width > 0:
                logger.debug(f"Calling update_container_width({width}) on {renderer_name}")
                self.renderer.update_container_width(width)
            else:
                logger.warning(f"Container width is 0, skipping update for {renderer_name}")

        # Sidebar renderer has _update_column_width_from_container method
        elif hasattr(self.renderer, '_update_column_width_from_container'):
            logger.debug(f"Calling _update_column_width_from_container() on {renderer_name}")
            self.renderer._update_column_width_from_container()

        else:
            logger.debug(f"Renderer {renderer_name} does not support dynamic width updates")

    def _handle_select(self, widget_or_item) -> None:
        """
        Unified selection handler.

        For native renderers: widget_or_item is a Toga widget, get selection from widget.selection
        For custom renderers (Card, HTML, Canvas): widget_or_item is the item data directly

        If navigable and item is a folder, navigates into it instead of selecting.
        """
        try:
            logger.info(f"🎯 _handle_select called with: {type(widget_or_item)}")

            # Check if this is a widget (has .selection attribute) or direct item data
            if hasattr(widget_or_item, 'selection'):
                # Native renderer: get selection from widget
                selection = widget_or_item.selection
                logger.info(f"🔍 Native widget selection - type: {type(selection)}, value: {selection}")
                if selection:
                    logger.debug(f"🔍   Selection attributes: {dir(selection)}")
            else:
                # Custom renderer: item data passed directly
                selection = widget_or_item
                logger.info(f"🔍 Custom renderer - direct item data")

            # Double-click detection for Table/DetailedList (since on_activate doesn't fire on macOS)
            import time
            current_time = time.time()
            is_double_click = False

            if selection is not None and self.renderer and hasattr(self.renderer, 'widget_type'):
                widget_type = self.renderer.widget_type

                # Extract item ID for comparison
                item_id = None
                if isinstance(selection, list) and len(selection) > 0:
                    sel_item = selection[0]
                    if hasattr(sel_item, '_collection_data') and sel_item._collection_data:
                        item_id = sel_item._collection_data.get('id')
                    elif hasattr(sel_item, '_item_id'):
                        item_id = sel_item._item_id
                elif hasattr(selection, '_collection_data') and selection._collection_data:
                    item_id = selection._collection_data.get('id')
                elif hasattr(selection, '_item_id'):
                    item_id = selection._item_id

                # Check if this is a double-click (same item clicked within threshold)
                if widget_type in ('table', 'detailedlist') and item_id:
                    time_diff = current_time - self._last_click_time
                    if item_id == self._last_clicked_item_id and time_diff < self._double_click_threshold:
                        is_double_click = True
                        logger.info(f"⚡ Double-click detected on {widget_type}! time_diff={time_diff:.3f}s, item_id={item_id}")

                    # Update last click state
                    self._last_click_time = current_time
                    self._last_clicked_item_id = item_id

            # For navigable lists, handle folder navigation differently based on widget type:
            # - Tree: Navigate on single-click (natural tree expand/collapse)
            # - Table/DetailedList: Only navigate on double-click (detected above)
            navigate_on_select = False
            if self.navigable and selection is not None:
                # Tree widget navigates on single-click
                if self.renderer and hasattr(self.renderer, 'widget_type') and self.renderer.widget_type == 'tree':
                    navigate_on_select = True
                # Table/DetailedList navigate on double-click
                elif is_double_click:
                    navigate_on_select = True
                    logger.info(f"📂 Double-click navigation triggered for {self.renderer.widget_type}")

                if navigate_on_select:
                    # Extract item data from selection
                    if isinstance(selection, dict):
                        item_data = selection
                    elif hasattr(selection, '__dict__'):
                        # Row/Node object - convert to dict
                        item_data = {
                            'path': getattr(selection, 'path', ''),
                            'is_folder': getattr(selection, 'is_folder', False),
                            'title': getattr(selection, 'title', ''),
                        }
                    else:
                        item_data = None

                    # Navigate into folder if it's a folder (unless we're already there)
                    if item_data and item_data.get('is_folder', False):
                        folder_path = item_data.get('path', '')
                        # Check if we're already at this folder (e.g., clicking header)
                        if folder_path and folder_path == self.current_path:
                            logger.debug(f"Already at folder '{item_data.get('title', 'Unknown')}' - calling on_select only (no navigation)")
                            # Call on_select to update inspector, but don't navigate
                            if self._on_select_callback:
                                self._on_select_callback(item_data)
                            return
                        else:
                            logger.debug(f"🌳 Tree: Navigating into folder on single-click: {item_data.get('title', 'Unknown')}")
                            self.navigate_into_folder(item_data)
                            return  # Don't call on_select for folder navigation

            # Call selection callback for non-folders or non-navigable lists
            # For Table/DetailedList, this will just select the item
            if self._on_select_callback:
                self._on_select_callback(selection)

            # Update SelectionManager if available
            if self.app and self.view_id and hasattr(self.app, 'selection_manager'):
                try:
                    # Extract item IDs and metadata from selection
                    item_ids = []
                    metadata = []

                    if selection:
                        # Handle different selection formats
                        if isinstance(selection, list):
                            # Multiple selection
                            for item in selection:
                                item_id = self._extract_item_id(item)
                                if item_id:
                                    item_ids.append(item_id)
                                    metadata.append(self._extract_item_metadata(item))
                        else:
                            # Single selection
                            item_id = self._extract_item_id(selection)
                            if item_id:
                                item_ids = [item_id]
                                metadata = [self._extract_item_metadata(selection)]

                    # Update SelectionManager
                    self.app.selection_manager.set_selection(
                        view_id=self.view_id,
                        item_ids=item_ids,
                        metadata=metadata if metadata else None
                    )
                    logger.debug(f"✅ SelectionManager updated: {len(item_ids)} items selected in {self.view_id}")
                except Exception as e:
                    logger.error(f"Failed to update SelectionManager: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Error in selection handler: {e}", exc_info=True)

    def _handle_activate(self, widget: toga.Widget, **kwargs) -> None:
        """
        Handle activation event (double-click, enter key, etc.).

        For navigable lists with Table/DetailedList widgets, this handles folder navigation.
        Tree widgets handle navigation on single-click in _handle_select.
        """
        try:
            logger.info(f"🚀 _handle_activate FIRED! widget={type(widget).__name__}, kwargs={kwargs}")

            # Extract selection
            if 'node' in kwargs:
                selection = kwargs['node']
            else:
                selection = widget.selection

            logger.info(f"🎯 _handle_activate: widget={type(widget).__name__}, selection={type(selection).__name__ if selection else 'None'}")

            # Unwrap single-item lists (Table/DetailedList with multiple_select returns list)
            if isinstance(selection, list):
                if len(selection) == 1:
                    selection = selection[0]
                    logger.debug(f"🎯 Unwrapped single-item list: {type(selection).__name__}")
                elif len(selection) == 0:
                    selection = None
                    logger.debug(f"🎯 Empty selection list")

            # For navigable lists, handle folder navigation on activate (double-click)
            # Only for Table/DetailedList - Tree handles navigation in _handle_select
            if self.navigable and selection is not None:
                widget_type = None
                if self.renderer and hasattr(self.renderer, 'widget_type'):
                    widget_type = self.renderer.widget_type

                # Only Table/DetailedList navigate on activate (double-click)
                # Tree navigates on select (single-click)
                if widget_type in ('table', 'detailedlist'):
                    logger.debug(f"🎯 Activate on {widget_type} - checking if folder...")

                    # Extract item data from selection
                    item_data = None
                    if isinstance(selection, dict):
                        item_data = selection
                    elif hasattr(selection, '_collection_data'):
                        logger.debug(f"🎯 Extracting from _collection_data attribute")

                        # Row/Node with _collection_data attribute
                        collection_data = selection._collection_data
                        item_data = {
                            'path': collection_data.get('path', ''),
                            'is_folder': collection_data.get('is_folder', False),
                            'title': collection_data.get('title', ''),
                        }
                    elif hasattr(selection, '__dict__'):
                        # Row/Node object - convert to dict
                        item_data = {
                            'path': getattr(selection, 'path', ''),
                            'is_folder': getattr(selection, 'is_folder', False),
                            'title': getattr(selection, 'title', ''),
                        }

                    # Navigate into folder if it's a folder
                    if item_data and item_data.get('is_folder', False):
                        folder_path = item_data.get('path', '')
                        if folder_path:
                            logger.debug(f"📂 {widget_type.capitalize()}: Navigating into folder on double-click: {item_data.get('title', 'Unknown')}")
                            self.navigate_into_folder(item_data)
                            return  # Don't call on_activate callback for folder navigation

                    logger.debug(f"🎯 Not a folder or no path - calling on_activate callback")

            # Call activation callback for non-folders or custom handling
            if self._on_activate:
                self._on_activate(selection)
        except Exception as e:
            logger.error(f"Error in activation handler: {e}", exc_info=True)

    def get_selection(self) -> Any:
        """
        Get the currently selected item(s).

        Returns:
            Row object (or None) with accessors from get_accessors()
        """
        if isinstance(self.widget, (toga.Table, toga.Tree, toga.DetailedList)):
            return self.widget.selection
        return None

    def _filter_items_by_path(self, path: str) -> List[Dict[str, Any]]:
        """
        Filter items to show only those in the specified path.

        For navigable lists, returns items where:
        - item['path'] == path (items directly in this folder)
        - OR item['path'] starts with path + '/' (subfolders)

        Args:
            path: Path to filter by (empty string = root)

        Returns:
            Filtered list of items
        """
        if not self.navigable:
            return self._all_data

        filtered = []
        for item in self._all_data:
            item_path = item.get('path', '')

            if path == '':
                # Root level: show items with empty path or no '/' in path
                if item_path == '' or '/' not in item_path:
                    filtered.append(item)
            else:
                # Inside folder: show direct children only
                # Direct child if item_path == path OR starts with path + '/'
                if item_path == path:
                    filtered.append(item)
                elif item_path.startswith(path + '/'):
                    # Check if this is a direct child (no additional '/')
                    remainder = item_path[len(path) + 1:]
                    if '/' not in remainder:
                        filtered.append(item)

        return filtered

    def navigate_to(self, path: str) -> None:
        """
        Navigate to a specific path in the list.

        Args:
            path: Path to navigate to (empty string = root)
        """
        if not self.navigable:
            logger.warning("Cannot navigate: ListWidget is not navigable")
            return

        logger.debug(f"Navigating from '{self.current_path}' to '{path}'")
        self.current_path = path

        # Filter data and refresh
        self._data = self._filter_items_by_path(path)
        self.set_data(self._data)

        # Notify callback
        if self._on_navigate_callback:
            self._on_navigate_callback(path)

    def navigate_up(self) -> None:
        """Navigate to parent folder."""
        if not self.navigable:
            logger.warning("Cannot navigate: ListWidget is not navigable")
            return

        if self.current_path == '':
            logger.debug("Already at root, cannot navigate up")
            return

        # Get parent path
        if '/' in self.current_path:
            parent_path = '/'.join(self.current_path.split('/')[:-1])
        else:
            parent_path = ''

        self.navigate_to(parent_path)

    def navigate_into_folder(self, item: Dict[str, Any]) -> None:
        """
        Navigate into a folder item.

        Args:
            item: Item to navigate into (must have is_folder=True)
        """
        if not self.navigable:
            logger.warning("Cannot navigate: ListWidget is not navigable")
            return

        if not item.get('is_folder', False):
            logger.debug(f"Item is not a folder: {item.get('title', 'Unknown')}")
            return

        new_path = item.get('path', '')
        self.navigate_to(new_path)

    def clear(self) -> None:
        """Clear all data from the widget."""
        self.set_data([])

    # ========================================================================
    # Advanced Operations
    # ========================================================================

    def add_item(self, item: Dict[str, Any]) -> None:
        """
        Add a single item to the list.

        Args:
            item: Item data in app format
        """
        self._data.append(item)

        # Convert to source format and add to source
        source_items = self.renderer.convert_to_source_format([item])
        if source_items:
            if self.renderer.widget_type == 'tree':
                # For tree, we need to rebuild the entire data
                self.set_data(self._data)
            else:
                # For table/detailedlist, append to source
                self._source.append(source_items[0])

    def add_items(self, items: List[Dict[str, Any]]) -> None:
        """
        Add multiple items to the list.

        Args:
            items: List of item data in app format
        """
        self._data.extend(items)

        # Convert to source format and add to source
        source_items = self.renderer.convert_to_source_format(items)
        if self.renderer.widget_type == 'tree':
            # For tree, we need to rebuild the entire data
            self.set_data(self._data)
        else:
            # For table/detailedlist, append to source
            for source_item in source_items:
                self._source.append(source_item)

    def remove_item(self, item_id: str) -> bool:
        """
        Remove an item by its ID.

        Args:
            item_id: The _item_id of the item to remove

        Returns:
            True if item was found and removed, False otherwise
        """
        # Find index of item to remove
        item_index = None
        for i, item in enumerate(self._data):
            if item.get('_item_id') == item_id:
                item_index = i
                break

        if item_index is None:
            return False  # Item not found

        # Try incremental remove if renderer supports it
        if self.renderer and self.renderer.supports_incremental_updates():
            # Remove from data first
            removed_item = self._data.pop(item_index)

            # Try incremental remove from widget
            if self.renderer.remove_item_at_index(item_index):
                logger.info(f"✅ Incremental remove: Removed item at index {item_index}")
                return True
            else:
                # Incremental remove failed, restore item and fall back to full rebuild
                self._data.insert(item_index, removed_item)
                logger.warning(f"Incremental remove failed, falling back to full rebuild")

        # Fall back to full rebuild (for Toga widgets or if incremental failed)
        original_len = len(self._data)
        self._data = [item for item in self._data if item.get('_item_id') != item_id]

        if len(self._data) == original_len:
            return False  # Item not found

        # Rebuild the widget data
        self.set_data(self._data)
        return True

    def remove_selected(self) -> int:
        """
        Remove all currently selected items.

        Returns:
            Number of items removed
        """
        selection = self.get_selection()
        if not selection:
            return 0

        # Handle both single and multiple selection
        if isinstance(selection, list):
            items_to_remove = selection
        else:
            items_to_remove = [selection]

        # Collect IDs to remove
        ids_to_remove = set()
        for item in items_to_remove:
            item_id = getattr(item, '_item_id', None)
            if item_id:
                ids_to_remove.add(item_id)

        # Remove items
        original_len = len(self._data)
        self._data = [item for item in self._data if item.get('_item_id') not in ids_to_remove]
        removed_count = original_len - len(self._data)

        # Rebuild the widget data
        if removed_count > 0:
            self.set_data(self._data)

        return removed_count

    def select_all(self) -> None:
        """Select all items in the list."""
        if not self.multiple_select:
            logger.warning("select_all called but multiple_select is False")
            return

        # Only Table and Tree support select_all in Toga
        if isinstance(self.widget, (toga.Table, toga.Tree)):
            # Select all by setting selection to all rows
            if self._source and len(self._source) > 0:
                self.widget.selection = list(self._source)

    def deselect_all(self) -> None:
        """Deselect all items in the list."""
        if isinstance(self.widget, (toga.Table, toga.Tree, toga.DetailedList)):
            self.widget.selection = None

    def select_item_by_id(self, item_id: str) -> bool:
        """
        Select an item by its ID.

        Args:
            item_id: The ID of the item to select

        Returns:
            True if item was found and selected, False otherwise
        """
        if not self._source:
            logger.warning("Cannot select item - no data source")
            return False

        if not self.widget:
            logger.warning("Cannot select item - widget not initialized")
            return False

        # Find the row with matching ID
        try:
            for row in self._source:
                if getattr(row, 'id', None) == item_id:
                    # Set selection to this row
                    if isinstance(self.widget, (toga.Table, toga.Tree, toga.DetailedList)):
                        try:
                            self.widget.selection = row
                            logger.debug(f"Selected item with ID: {item_id}")
                            return True
                        except Exception as e:
                            logger.warning(f"Failed to set widget selection: {e}")
                            return False
                    else:
                        logger.warning(f"Widget type {type(self.widget).__name__} doesn't support selection")
                        return False

            logger.debug(f"Item with ID {item_id} not found in list")
            return False
        except Exception as e:
            logger.error(f"Error in select_item_by_id: {e}")
            return False

    def get_all_selected(self) -> List[Any]:
        """
        Get all currently selected items.

        Returns:
            List of selected Row objects (or empty list if nothing selected)
        """
        selection = self.get_selection()
        if not selection:
            return []

        if isinstance(selection, list):
            return selection
        else:
            return [selection]

    def search(self, query: str, fields: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Search for items matching the query.

        Args:
            query: Search string
            fields: List of fields to search in (defaults to all text fields)

        Returns:
            List of matching items in app format
        """
        if not query:
            return self._data

        query_lower = query.lower()
        results = []

        for item in self._data:
            # Search in specified fields or all string fields
            if fields:
                search_values = [str(item.get(field, '')) for field in fields]
            else:
                search_values = [str(v) for v in item.values() if isinstance(v, (str, int, float))]

            # Check if any value contains the query
            for value in search_values:
                if query_lower in value.lower():
                    results.append(item)
                    break

        return results

    def filter_items(self, predicate: callable) -> List[Dict[str, Any]]:
        """
        Filter items using a predicate function.

        Args:
            predicate: Function that takes an item and returns True/False

        Returns:
            List of items matching the predicate
        """
        return [item for item in self._data if predicate(item)]

    def sort_by(self, field: str, reverse: bool = False) -> None:
        """
        Sort items by a field.

        Args:
            field: Field name to sort by
            reverse: If True, sort in descending order
        """
        try:
            self._data.sort(key=lambda item: item.get(field, ''), reverse=reverse)
            self.set_data(self._data)
        except Exception as e:
            logger.error(f"Error sorting by field '{field}': {e}")

    def get_item_count(self) -> int:
        """Get the total number of items in the list."""
        return len(self._data)

    def get_item_by_id(self, item_id: str) -> Optional[Dict[str, Any]]:
        """
        Get an item by its ID.

        Args:
            item_id: The _item_id to search for

        Returns:
            Item data in app format, or None if not found
        """
        for item in self._data:
            if item.get('_item_id') == item_id:
                return item
        return None

    # ========================================================================
    # Column Operations (Table/Tree only - DetailedList doesn't support columns)
    # ========================================================================

    def reorder_columns(self, new_column_order: List[str]) -> None:
        """
        Reorder columns (Table/Tree only).

        Args:
            new_column_order: List of column names in the desired order

        Note:
            DetailedList doesn't support multiple columns, so this is a no-op
            for DetailedList widgets.
        """
        if self.renderer.widget_type == 'detailedlist':
            logger.warning("Column reordering not supported for DetailedList")
            return

        # Validate that all columns exist
        if not all(col in self.headings for col in new_column_order):
            logger.error("Invalid column order - some columns don't exist")
            return

        # Update headings
        self.headings = new_column_order

        # Recreate the widget with new column order
        # This requires recreating the renderer and widget
        old_widget_type = self.renderer.widget_type
        self.renderer = self._create_renderer()
        self.widget = self.renderer.create_widget()

        # Re-populate with data
        self.set_data(self._data)

        logger.info(f"Reordered columns to: {new_column_order}")

    def add_column(self, column_name: str, position: Optional[int] = None) -> None:
        """
        Add a new column (Table/Tree only).

        Args:
            column_name: Name of the new column
            position: Index to insert the column (default: append to end)

        Note:
            DetailedList doesn't support multiple columns, so this is a no-op
            for DetailedList widgets.
        """
        if self.renderer.widget_type == 'detailedlist':
            logger.warning("Adding columns not supported for DetailedList")
            return

        if column_name in self.headings:
            logger.warning(f"Column '{column_name}' already exists")
            return

        # Add to headings
        if position is None:
            self.headings.append(column_name)
        else:
            self.headings.insert(position, column_name)

        # Recreate the widget with new columns
        self.renderer = self._create_renderer()
        self.widget = self.renderer.create_widget()

        # Re-populate with data
        self.set_data(self._data)

        logger.info(f"Added column '{column_name}' at position {position or len(self.headings)-1}")

    def remove_column(self, column_name: str) -> bool:
        """
        Remove a column (Table/Tree only).

        Args:
            column_name: Name of the column to remove

        Returns:
            True if column was removed, False if not found

        Note:
            DetailedList doesn't support multiple columns, so this is a no-op
            for DetailedList widgets.
        """
        if self.renderer.widget_type == 'detailedlist':
            logger.warning("Removing columns not supported for DetailedList")
            return False

        if column_name not in self.headings:
            logger.warning(f"Column '{column_name}' not found")
            return False

        # Remove from headings
        self.headings.remove(column_name)

        # Recreate the widget with new columns
        self.renderer = self._create_renderer()
        self.widget = self.renderer.create_widget()

        # Re-populate with data
        self.set_data(self._data)

        logger.info(f"Removed column '{column_name}'")
        return True

    def get_column_count(self) -> int:
        """Get the number of columns."""
        return len(self.headings)

    def get_columns(self) -> List[str]:
        """Get the list of column names."""
        return self.headings.copy()

    def _extract_item_id(self, item: Any) -> Optional[str]:
        """
        Extract item ID from a selection object.

        Handles different selection formats:
        - Row/Node with _collection_data attribute
        - Row/Node with item_id/id attribute
        - Dict with 'id' or 'item_id' key

        Args:
            item: Selection item (Row, Node, dict, etc.)

        Returns:
            Item ID as string, or None if not found
        """
        if item is None:
            return None

        # Try _collection_data attribute first (our custom metadata)
        if hasattr(item, '_collection_data') and item._collection_data:
            return item._collection_data.get('id') or item._collection_data.get('item_id')

        # Try item_id or id attributes
        if hasattr(item, 'item_id') and item.item_id:
            return str(item.item_id)
        if hasattr(item, 'id') and item.id:
            return str(item.id)

        # Try dict keys
        if isinstance(item, dict):
            return item.get('id') or item.get('item_id')

        return None

    def _extract_item_metadata(self, item: Any) -> Dict[str, Any]:
        """
        Extract metadata from a selection object.

        Args:
            item: Selection item (Row, Node, dict, etc.)

        Returns:
            Metadata dict with item properties (name, type, path, etc.)
        """
        metadata = {}

        if item is None:
            return metadata

        # Extract from _collection_data if available
        if hasattr(item, '_collection_data') and item._collection_data:
            return dict(item._collection_data)

        # Extract common attributes
        for attr in ['id', 'item_id', 'title', 'name', 'type', 'path', 'file_path', 'is_folder']:
            if hasattr(item, attr):
                value = getattr(item, attr)
                if value is not None:
                    metadata[attr] = value

        # If item is a dict, use it directly
        if isinstance(item, dict):
            metadata.update(item)

        return metadata

    @property
    def impl(self) -> toga.Widget:
        """Get the underlying Toga widget implementation."""
        return self.widget


__all__ = ['ListWidget', 'Platform']
