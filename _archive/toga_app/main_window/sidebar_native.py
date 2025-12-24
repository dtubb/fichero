"""
Native Sidebar using NSTreeController.

================================================================================
ARCHITECTURE OVERVIEW
================================================================================

Data Flow:
    models.py (Document)
        │
        ▼
    db.py (query/save)
        │
        ▼
    sidebar_native.py (builds tree from db.query)
        │
        ▼
    NSTreeController (automatic data source, selection, expand/collapse)
        │
        ▼
    NSOutlineView (native macOS sidebar UI)

This sidebar uses Apple's NSTreeController to manage the tree data. NSTreeController
provides automatic:
- Data source (no manual outlineView:numberOfChildrenOfItem: etc.)
- Selection tracking via KVO (Key-Value Observing)
- Expand/collapse state persistence
- Drag-drop reordering (via arrangedObjects bindings)

================================================================================
WHAT IS KVO (Key-Value Observing)?
================================================================================

KVO is Apple's observer pattern built into Objective-C/Cocoa. It allows objects
to be notified when properties on other objects change.

How it works:

    ┌─────────────────────┐         ┌─────────────────────┐
    │   NSTreeController  │         │  _SelectionObserver │
    │                     │         │                     │
    │  selectionIndexPaths│◄────────│  observeValue...()  │
    │  (KVO property)     │  KVO    │  (callback)         │
    └─────────────────────┘  notify └─────────────────────┘
              │                              │
              │ changes when                 │ receives notification
              │ user clicks                  │ when selection changes
              ▼                              ▼
    User clicks item ──────────► Observer callback fires
                                         │
                                         ▼
                                 sidebar.on_select(doc_id)

In Python with rubicon-objc:

    # 1. Create observer (must be ObjC object)
    observer = _SelectionObserver.alloc().init()

    # 2. Register for KVO notifications
    tree_controller.addObserver_forKeyPath_options_context_(
        observer,              # Who receives notifications
        "selectionIndexPaths", # What property to observe
        0,                     # Options (0 = just notify, no old/new values)
        None                   # Context (not used)
    )

    # 3. Observer receives callback when property changes
    @objc_method
    def observeValueForKeyPath_ofObject_change_context_(self, keyPath, obj, change, ctx):
        # This fires whenever selectionIndexPaths changes
        selected = tree_controller.selectedObjects
        ...

    # 4. IMPORTANT: Remove observer before deallocation
    tree_controller.removeObserver_forKeyPath_(observer, "selectionIndexPaths")

KVO is REQUIRED when using NSTreeController because it manages selection internally.
There's no delegate callback for selection changes - you MUST use KVO.

================================================================================
NODE DATA MODEL
================================================================================

NSTreeController requires nodes with specific keypaths:
- children: Array of child nodes
- isLeaf: Boolean, true if node has no children

We use SidebarNode (NSObject subclass) with objc_property declarations:

    class SidebarNode(NSObject):
        _title = objc_property(object)     # Display text
        _icon = objc_property(object)      # SF Symbol name
        _children = objc_property(object)  # NSMutableArray of child nodes
        _isLeaf = objc_property(bool)      # True if no children
        _document_id = objc_property(object)  # Reference to Document.id
        _is_header = objc_property(bool)   # True for section headers

NSTreeController is configured to use these keypaths:
    tree_controller.setChildrenKeyPath_("children")
    tree_controller.setLeafKeyPath_("isLeaf")

================================================================================
THUMBNAIL/ICON STRATEGY
================================================================================

Icons in the sidebar come from SF Symbols (Apple's icon font), NOT from
the thumbnail system. Thumbnails are for the Browser view.

    Sidebar: SF Symbols (folder.fill, doc, photo, etc.)
    Browser: storage.ensure_thumbnail(doc) - generates JPEGs

This is intentional:
- SF Symbols are vector, scale perfectly, match system appearance
- Thumbnails are raster, meant for content preview
- Sidebar icons represent document TYPE, thumbnails show CONTENT

================================================================================
USAGE
================================================================================

    sidebar = NativeSidebar(on_select=handle_select)
    sidebar.reload()  # Builds tree from db.query()
    container.addSubview_(sidebar.native)

    def handle_select(document_id: str):
        # Load document in browser
        doc = db.get(Document, document_id)
        browser.load(doc)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from fichero.ui.i18n import _

from rubicon.objc import (
    ObjCClass,
    ObjCInstance,
    objc_method,
    objc_property,
    at,
    send_super,
    SEL,
)
from rubicon.objc.runtime import objc_id

logger = logging.getLogger(__name__)


# =============================================================================
# Cocoa Classes
# =============================================================================

NSObject = ObjCClass("NSObject")
NSTreeController = ObjCClass("NSTreeController")
NSOutlineView = ObjCClass("NSOutlineView")
NSScrollView = ObjCClass("NSScrollView")
NSTableColumn = ObjCClass("NSTableColumn")
NSTableCellView = ObjCClass("NSTableCellView")
# NOTE: NSVisualEffectView is NOT needed here - NSSplitViewItem.sidebarWithViewController_()
# automatically adds vibrancy when added to the split view controller.
NSColor = ObjCClass("NSColor")
NSImage = ObjCClass("NSImage")
NSImageView = ObjCClass("NSImageView")
NSTextField = ObjCClass("NSTextField")
NSFont = ObjCClass("NSFont")
NSIndexPath = ObjCClass("NSIndexPath")
NSMutableArray = ObjCClass("NSMutableArray")
NSArray = ObjCClass("NSArray")
NSURL = ObjCClass("NSURL")
NSMenu = ObjCClass("NSMenu")
NSMenuItem = ObjCClass("NSMenuItem")
NSIndexSet = ObjCClass("NSIndexSet")


# =============================================================================
# Constants (Apple HIG compliant)
# =============================================================================

# NOTE: MATERIAL_SIDEBAR and BLENDING_BEHIND_WINDOW removed - vibrancy is
# handled automatically by NSSplitViewItem.sidebarWithViewController_()
HIGHLIGHT_SOURCE_LIST = 1
AUTORESIZE_FLEX = 18
ROW_HEIGHT = 24
HEADER_HEIGHT = 28
ICON_SIZE = 16
INDENT = 12
FILE_UTI = "public.file-url"


# =============================================================================
# Section Colors (vibrant, distinguishable)
# =============================================================================

SECTION_COLORS = {
    "Library": (0.0, 0.478, 1.0, 1.0),      # Blue #007AFF
    "Searches": (0.96, 0.65, 0.14, 1.0),    # Orange #F5A623
    "Workflows": (0.608, 0.349, 0.714, 1.0), # Purple #9B59B6
    "TOOLS": (0.306, 0.804, 0.769, 1.0),    # Teal #4ECDC4
    "PROVIDERS": (0.655, 0.208, 0.718, 1.0), # Magenta #A735B7
}


# =============================================================================
# SF Symbol Icons for Document Types
# =============================================================================

ICON_FOR_DOC_TYPE = {
    "collection": "folder",
    "folder": "folder",
    "group": "doc.on.doc",
    "file": "doc",
    "page": "doc.text",
    "chunk": "text.alignleft",
}

ICON_FOR_FILE_TYPE = {
    "image": "photo",
    "pdf": "doc.richtext",
    "audio": "waveform",
    "video": "film",
    "text": "doc.text",
    "word": "doc.richtext",
    "epub": "book",
}


def icon_for_document(doc) -> str:
    """Get SF Symbol name for document.

    Args:
        doc: Document model or dict with doc_type/file_type

    Returns:
        SF Symbol name (e.g., "folder.fill", "photo")
    """
    # Get doc_type
    doc_type = getattr(doc, "doc_type", None)
    if doc_type:
        type_str = doc_type.value if hasattr(doc_type, "value") else str(doc_type)
        if type_str in ICON_FOR_DOC_TYPE:
            return ICON_FOR_DOC_TYPE[type_str]

    # Get file_type
    file_type = getattr(doc, "file_type", None)
    if file_type:
        type_str = file_type.value if hasattr(file_type, "value") else str(file_type)
        if type_str in ICON_FOR_FILE_TYPE:
            return ICON_FOR_FILE_TYPE[type_str]

    return "doc"


# =============================================================================
# SidebarNode - KVO-compliant tree node
# =============================================================================

class SidebarNode(NSObject):
    """
    KVO-compliant tree node for NSTreeController.

    Properties are declared with objc_property for KVO compatibility.
    NSTreeController observes 'children' and 'isLeaf' keypaths.
    """

    _title = objc_property(object)
    _icon = objc_property(object)
    _children = objc_property(object)
    _isLeaf = objc_property(bool)
    _document_id = objc_property(object)
    _is_header = objc_property(bool)
    _section = objc_property(object)  # Section name for color lookup

    @objc_method
    def init(self) -> objc_id:
        """Initialize node with empty children array."""
        self = ObjCInstance(
            send_super(__class__, self, "init", restype=objc_id, argtypes=[])
        )
        if self:
            self._children = NSMutableArray.alloc().init()
            self._isLeaf = True
            self._is_header = False
            self._section = None
        return self

    # Keypaths for NSTreeController binding
    @objc_method
    def title(self):
        return self._title

    @objc_method
    def setTitle_(self, value):
        self._title = value

    @objc_method
    def icon(self):
        return self._icon

    @objc_method
    def children(self):
        return self._children

    @objc_method
    def isLeaf(self) -> bool:
        return self._isLeaf

    @objc_method
    def addChild_(self, child) -> None:
        """Add child node and mark as non-leaf."""
        self._children.addObject_(child)
        self._isLeaf = False


def create_node(
    title: str,
    icon: str | None = None,
    document_id: str | None = None,
    is_leaf: bool = True,
    is_header: bool = False,
    section: str | None = None,
) -> SidebarNode:
    """Create a SidebarNode.

    Args:
        title: Display text
        icon: SF Symbol name (e.g., "folder.fill")
        document_id: Reference to Document.id
        is_leaf: True if node has no children
        is_header: True for section headers
        section: Section name for color (e.g., "LIBRARY", "TOOLS")

    Returns:
        Configured SidebarNode
    """
    node = SidebarNode.alloc().init()
    node._title = title
    node._icon = icon
    node._document_id = document_id
    node._isLeaf = is_leaf
    node._is_header = is_header
    node._section = section
    return node


# =============================================================================
# Tree Builder - Loads ALL sections from db.py
# =============================================================================

def build_sidebar_tree() -> list[SidebarNode]:
    """Build sidebar tree from database.

    Sections:
    - LIBRARY: Document collections
    - SEARCHES: SavedSearch queries
    - WORKFLOWS: Workflow pipelines

    Note: Providers are managed in the Inspector workflow section, not sidebar.

    Returns:
        List of root-level SidebarNode objects (section headers)
    """
    return [
        _build_library_section(),
        _build_searches_section(),
        _build_workflows_section(),
    ]


# -----------------------------------------------------------------------------
# LIBRARY - Document collections
# -----------------------------------------------------------------------------

def _build_library_section() -> SidebarNode:
    """Build LIBRARY section from Document table."""
    library = create_node(
        title=_("sidebar_library"),
        icon="books.vertical.fill",
        is_leaf=False,
        is_header=True,
        section="Library",
    )

    try:
        from fichero.db import db
        from fichero.models import Document, DocType

        # Query collections - convert to list to avoid generator issues during tree building
        collections = list(db.query(Document, doc_type=DocType.collection))
        logger.info(f"Loading {len(collections)} collections into sidebar")

        for doc in collections:
            node = create_node(
                title=doc.name,
                icon=icon_for_document(doc),
                document_id=f"doc:{doc.id}",
                is_leaf=True,  # addChild_ sets to False when children added
                section="Library",
            )
            _load_document_children(node, doc.id, depth=0)
            library.addChild_(node)

    except Exception as e:
        logger.error(f"Error loading library: {e}", exc_info=True)

    return library


def _load_document_children(parent: SidebarNode, parent_id: str, depth: int = 0):
    """Load folder children with depth limit to prevent crashes.

    Sidebar only shows containers (collections/folders) - like DEVONthink.
    Individual items are shown in the browser when a folder is selected.

    Args:
        parent: Parent SidebarNode to add children to
        parent_id: Document ID of the parent
        depth: Current recursion depth (max 3 levels to prevent crashes)
    """
    MAX_DEPTH = 3  # Prevent deep recursion that can crash

    if depth >= MAX_DEPTH:
        logger.debug(f"Max depth {MAX_DEPTH} reached for {parent_id}, stopping recursion")
        return

    try:
        from fichero.db import db
        from fichero.models import Document, DocType

        # Query folders only - convert to list immediately to avoid generator issues
        children = list(db.query(Document, parent_id=parent_id, doc_type=DocType.folder))
        logger.debug(f"Loading {len(children)} folders under {parent_id} (depth={depth})")

        for doc in children:
            node = create_node(
                title=doc.name,
                icon=icon_for_document(doc),
                document_id=f"doc:{doc.id}",
                is_leaf=True,  # addChild_ sets to False when children added
                section="Library",
            )
            # Recurse with incremented depth
            _load_document_children(node, doc.id, depth + 1)
            parent.addChild_(node)

    except Exception as e:
        logger.error(f"Error loading children for {parent_id}: {e}", exc_info=True)


# -----------------------------------------------------------------------------
# SEARCHES - Saved search queries
# -----------------------------------------------------------------------------

def _build_searches_section() -> SidebarNode:
    """Build SEARCHES section from SavedSearch table."""
    from fichero.db import db
    from fichero.models import SavedSearch

    searches = create_node(
        title=_("sidebar_searches"),
        icon="magnifyingglass",
        is_leaf=False,
        is_header=True,
        section="Searches",
    )

    try:
        for search in db.all(SavedSearch):
            node = create_node(
                title=search.name,
                icon=search.icon or "magnifyingglass",
                document_id=f"search:{search.id}",
                section="Searches",
            )
            searches.addChild_(node)
    except Exception as e:
        logger.error(f"Error loading searches: {e}")

    return searches


# -----------------------------------------------------------------------------
# WORKFLOWS - Processing pipelines
# -----------------------------------------------------------------------------

def _build_workflows_section() -> SidebarNode:
    """Build WORKFLOWS section from Workflow table."""
    from fichero.db import db
    from fichero.models import Workflow

    workflows = create_node(
        title=_("sidebar_workflows"),
        icon="arrow.triangle.branch",
        is_leaf=False,
        is_header=True,
        section="Workflows",
    )

    try:
        for wf in db.all(Workflow):
            node = create_node(
                title=wf.name,
                icon="doc.text",
                document_id=f"workflow:{wf.id}",
                section="Workflows",
            )
            workflows.addChild_(node)
    except Exception as e:
        logger.error(f"Error loading workflows: {e}")

    return workflows


# -----------------------------------------------------------------------------
# TOOLS - Processing tools
# -----------------------------------------------------------------------------

def _build_tools_section() -> SidebarNode:
    """Build TOOLS section from Tool table."""
    from fichero.db import db
    from fichero.models import Tool

    tools = create_node(
        title="TOOLS",
        icon="wrench.and.screwdriver.fill",
        is_leaf=False,
        is_header=True,
        section="TOOLS",
    )

    try:
        for tool in db.all(Tool):
            if not tool.enabled:
                continue
            node = create_node(
                title=tool.name,
                icon=tool.icon or "wrench",
                document_id=f"tool:{tool.id}",
                section="TOOLS",
            )
            tools.addChild_(node)
    except Exception as e:
        logger.error(f"Error loading tools: {e}")

    return tools


# -----------------------------------------------------------------------------
# PROVIDERS - AI providers with models
# -----------------------------------------------------------------------------

def _build_providers_section() -> SidebarNode:
    """Build PROVIDERS section from Provider + Model tables."""
    from fichero.db import db
    from fichero.models import Provider, Model

    providers = create_node(
        title="PROVIDERS",
        icon="cpu.fill",
        is_leaf=False,
        is_header=True,
        section="PROVIDERS",
    )

    try:
        for provider in db.all(Provider):
            if not provider.enabled:
                continue

            # Provider node (expandable)
            provider_node = create_node(
                title=provider.name,
                icon="server.rack",
                document_id=f"provider:{provider.id}",
                is_leaf=False,
                section="PROVIDERS",
            )

            # Load models for this provider
            for model in db.query(Model, provider_id=provider.id):
                if not model.enabled:
                    continue
                model_node = create_node(
                    title=model.name,
                    icon="brain" if model.is_default else "brain.head.profile",
                    document_id=f"model:{model.id}",
                    section="PROVIDERS",
                )
                provider_node.addChild_(model_node)

            providers.addChild_(provider_node)
    except Exception as e:
        logger.error(f"Error loading providers: {e}")

    return providers


# =============================================================================
# Outline View Delegate
# =============================================================================

def _get_node(item):
    """Safely get node from NSTreeNode item, returns None on error."""
    if not item:
        return None
    try:
        return item.representedObject
    except (KeyError, AttributeError):
        return None


class _OutlineDelegate(NSObject):
    """NSOutlineView delegate for cell rendering."""

    _sidebar = objc_property(object, weak=True)

    @objc_method
    def outlineView_viewForTableColumn_item_(self, outline_view, column, item):
        """Create cell view for item."""
        node = _get_node(item)
        if not node:
            return None

        try:
            title = str(node.title) if getattr(node, "title", None) else ""
            is_header = bool(getattr(node, "_is_header", False))
            section = str(getattr(node, "_section", None) or "")

            cell = NSTableCellView.alloc().initWithFrame_(((0, 0), (200, ROW_HEIGHT)))

            # Text field
            text_x = 4 if is_header else ICON_SIZE + 8
            tf = NSTextField.alloc().initWithFrame_(((text_x, 4), (200 - text_x - 4, 16)))
            tf.stringValue = title
            tf.editable = False
            tf.bordered = False
            tf.drawsBackground = False
            tf.lineBreakMode = 4  # truncate tail
            tf.cell.truncatesLastVisibleLine = True
            tf.setAutoresizingMask_(2)  # width sizable

            if is_header:
                tf.font = NSFont.systemFontOfSize_weight_(NSFont.smallSystemFontSize, 0.23)
                tf.textColor = NSColor.tertiaryLabelColor
            else:
                tf.font = NSFont.systemFontOfSize_(NSFont.smallSystemFontSize)

            cell.addSubview_(tf)

            # Icon (not for headers)
            if not is_header:
                icon_name = getattr(node, "_icon", None) or "doc"
                img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(icon_name, None)
                if img:
                    iv = NSImageView.alloc().initWithFrame_(((4, 4), (ICON_SIZE, ICON_SIZE)))
                    iv.image = img
                    if section in SECTION_COLORS:
                        iv.contentTintColor = NSColor.colorWithRed_green_blue_alpha_(*SECTION_COLORS[section])
                    else:
                        img.setTemplate_(True)
                    cell.addSubview_(iv)

            return cell
        except Exception as e:
            logger.error(f"Error creating cell: {e}")
            return None

    @objc_method
    def outlineView_didAddRowView_forRow_(self, outline_view, row_view, row: int):
        """Grey selection style."""
        row_view.emphasized = False

    @objc_method
    def outlineView_isGroupItem_(self, outline_view, item) -> bool:
        """Headers are group items."""
        node = _get_node(item)
        return bool(getattr(node, "_is_header", False)) if node else False

    @objc_method
    def outlineView_shouldSelectItem_(self, outline_view, item) -> bool:
        """Headers not selectable."""
        node = _get_node(item)
        if not node:
            return True
        return not bool(getattr(node, "_is_header", False))

    @objc_method
    def outlineView_heightOfRowByItem_(self, outline_view, item) -> float:
        """Row height varies by type."""
        node = _get_node(item)
        is_header = bool(getattr(node, "_is_header", False)) if node else False
        return float(HEADER_HEIGHT if is_header else ROW_HEIGHT)

    # Drag-drop: accept file drops
    @objc_method
    def outlineView_validateDrop_proposedItem_proposedChildIndex_(
        self, outline_view, info, item, index
    ) -> int:
        """Validate file drops."""
        try:
            pb = info.draggingPasteboard
            types = [str(t) for t in (pb.types or [])]
            if FILE_UTI in types:
                return 1  # NSDragOperationCopy
            return 0  # NSDragOperationNone
        except Exception as e:
            logger.error(f"Error validating drop: {e}")
            return 0

    @objc_method
    def outlineView_acceptDrop_item_childIndex_(
        self, outline_view, info, item, index
    ) -> bool:
        """Accept file drops."""
        try:
            sidebar = self._sidebar
            if not sidebar or not sidebar.on_file_drop:
                return False

            pb = info.draggingPasteboard
            urls = pb.readObjectsForClasses_options_(
                NSArray.arrayWithObject_(NSURL), None
            )
            if not urls:
                return False

            paths = [str(u.path) for u in urls if u.isFileURL()]
            if not paths:
                return False

            # Get target document ID
            target_id = None
            if item:
                node = item.representedObject
                if node and getattr(node, "_document_id", None):
                    target_id = str(node._document_id)

            sidebar.on_file_drop(target_id, paths)
            return True
        except Exception as e:
            logger.error(f"Error accepting drop: {e}")
            return False


# =============================================================================
# Selection Observer (KVO)
# =============================================================================

class _SelectionObserver(NSObject):
    """KVO observer for NSTreeController selection changes."""

    _sidebar = objc_property(object, weak=True)

    @objc_method
    def observeValueForKeyPath_ofObject_change_context_(self, keyPath, obj, change, ctx):
        """Schedule selection handling on next event loop (Apple's pattern)."""
        sidebar = self._sidebar
        if sidebar and not getattr(sidebar, "_handling_selection", False):
            sidebar._schedule_selection_callback()


# =============================================================================
# NativeSidebar - Main Public Class
# =============================================================================

class NativeSidebar:
    """
    Native macOS sidebar using NSTreeController.

    Uses Apple's NSTreeController for automatic:
    - Data source (no manual delegate methods needed)
    - Selection tracking via KVO
    - Expand/collapse persistence
    - Drag-drop support

    Args:
        on_select: Called with document_id when selection changes
        on_file_drop: Called with (target_id, paths) when files dropped
    """

    def __init__(
        self,
        on_select: Callable[[str], None] | None = None,
        on_file_drop: Callable[[str | None, list[str]], None] | None = None,
    ):
        self.on_select = on_select
        self.on_file_drop = on_file_drop
        self._roots: list[SidebarNode] = []
        self._all_nodes: list[SidebarNode] = []  # Strong refs to prevent GC
        self._path_to_docid: dict[tuple, str] = {}  # Index path tuple → doc_id
        self._handling_selection = False  # Re-entrancy guard for KVO observer
        self._last_selected_id: str | None = None  # Track last selection to avoid duplicates
        self._selection_scheduled = False  # Debounce: prevent multiple call_soon piling up

        # Tree controller (manages data source automatically)
        self._tree_controller = NSTreeController.alloc().init()
        self._tree_controller.setChildrenKeyPath_("children")
        self._tree_controller.setLeafKeyPath_("isLeaf")
        self._tree_controller.setObjectClass_(SidebarNode)
        self._tree_controller.setAvoidsEmptySelection_(False)
        self._tree_controller.setPreservesSelection_(True)

        # KVO observer for selection changes
        self._observer = _SelectionObserver.alloc().init()
        self._observer._sidebar = self
        self._tree_controller.addObserver_forKeyPath_options_context_(
            self._observer, "selectedObjects", 0, None  # Apple's pattern: observe objects, not paths
        )

        # Scroll view
        # NOTE: We do NOT wrap in NSVisualEffectView here because
        # NSSplitViewItem.sidebarWithViewController_() automatically adds
        # vibrancy when the sidebar is added to the split view controller.
        # See: https://christiantietze.de/posts/2017/06/nssplitviewitem-kinds/
        self._scroll = NSScrollView.alloc().initWithFrame_(((0, 0), (250, 400)))
        self._scroll.hasVerticalScroller = True
        self._scroll.borderType = 0
        self._scroll.drawsBackground = False

        # Outline view
        self._outline = NSOutlineView.alloc().initWithFrame_(((0, 0), (250, 400)))
        self._outline.headerView = None
        self._outline.selectionHighlightStyle = HIGHLIGHT_SOURCE_LIST
        self._outline.draggingDestinationFeedbackStyle = 2  # sourceList (grey, not bright blue)
        self._outline.rowHeight = ROW_HEIGHT
        self._outline.indentationPerLevel = INDENT
        self._outline.backgroundColor = NSColor.clearColor
        self._outline.autosaveExpandedItems = True
        self._outline.autosaveName = "FicheroSidebar"

        # Column - expands to fill available width
        col = NSTableColumn.alloc().initWithIdentifier_("main")
        col.width = 250
        col.minWidth = 100
        col.maxWidth = 1000
        col.resizingMask = 1  # NSTableColumnAutoresizingMask
        self._outline.addTableColumn_(col)
        self._outline.outlineTableColumn = col
        self._outline.columnAutoresizingStyle = 4  # NSTableViewLastColumnOnlyAutoresizingStyle
        self._outline.sizeLastColumnToFit()

        # Register for file drops
        self._outline.registerForDraggedTypes_(NSArray.arrayWithObject_(FILE_UTI))

        # Delegate
        self._delegate = _OutlineDelegate.alloc().init()
        self._delegate._sidebar = self
        self._outline.delegate = self._delegate

        # Bind outline view to tree controller
        self._outline.bind_toObject_withKeyPath_options_(
            "content", self._tree_controller, "arrangedObjects", None
        )
        self._outline.bind_toObject_withKeyPath_options_(
            "selectionIndexPaths", self._tree_controller, "selectionIndexPaths", None
        )

        # Assemble view hierarchy
        self._scroll.documentView = self._outline
        self._scroll.setAutoresizingMask_(AUTORESIZE_FLEX)

        logger.debug("NativeSidebar initialized")

    @property
    def native(self):
        """The native NSScrollView to add to parent.

        NOTE: We return the scroll view directly, NOT wrapped in NSVisualEffectView.
        NSSplitViewItem.sidebarWithViewController_() adds vibrancy automatically.
        """
        return self._scroll

    @property
    def selected_document_id(self) -> str | None:
        """Currently selected document ID (from selectedObjects - Apple's pattern)."""
        try:
            selected = self._tree_controller.selectedObjects
            if not selected or len(selected) == 0:
                return None
            # Get first selected node directly (no path lookup needed)
            node = selected[0]
            doc_id = getattr(node, "_document_id", None)
            return str(doc_id) if doc_id else None
        except Exception:
            return None

    def reload(self):
        """Reload tree from database.

        IMPORTANT: We keep strong references to all nodes in _all_nodes to prevent
        them from being garbage collected while NSTreeController still has pointers
        to them. This prevents the rubicon KeyError cache miss when ObjC tries to
        access deallocated Python-backed objects.
        """
        self._roots = build_sidebar_tree()

        # Keep strong references to ALL nodes (not just roots) to prevent GC
        # from deallocating them while NSTreeController still holds pointers
        # Also build path→doc_id cache for fast lookup in KVO handler
        self._all_nodes = []
        self._path_to_docid = {}
        self._collect_all_nodes(self._roots, self._all_nodes, path_prefix=())
        logger.debug(f"Sidebar: keeping {len(self._all_nodes)} nodes, {len(self._path_to_docid)} paths cached")

        content = NSMutableArray.alloc().init()
        for root in self._roots:
            content.addObject_(root)
        self._tree_controller.setContent_(content)

        # Expand section headers
        for i in range(len(self._roots)):
            item = self._outline.itemAtRow_(i)
            if item:
                self._outline.expandItem_(item)

        logger.debug(f"Sidebar reloaded: {len(self._roots)} sections")

    def _schedule_selection_callback(self):
        """Schedule selection handling on next event loop iteration.

        Uses _selection_scheduled flag to debounce - prevents multiple
        call_soon() from piling up if KVO fires rapidly.
        """
        if self._selection_scheduled:
            return  # Already scheduled, don't pile up callbacks
        self._selection_scheduled = True
        import asyncio
        try:
            asyncio.get_event_loop().call_soon(self._handle_selection)
        except Exception:
            self._selection_scheduled = False  # Reset on error

    def _handle_selection(self):
        """Handle selection (called from event loop, safe to access ObjC)."""
        self._selection_scheduled = False  # Clear debounce flag first

        if self._handling_selection or not self.on_select:
            return

        doc_id = self.selected_document_id
        if not doc_id:
            return

        # Only fire callback if selection actually changed
        if doc_id == self._last_selected_id:
            return
        self._last_selected_id = doc_id

        self._handling_selection = True
        try:
            self.on_select(doc_id)
        finally:
            self._handling_selection = False

    def _collect_all_nodes(self, nodes: list, collector: list, path_prefix: tuple):
        """Recursively collect all nodes and build path→doc_id cache.

        Args:
            nodes: List of SidebarNode objects at current level
            collector: List to append nodes to (for strong references)
            path_prefix: Tuple of indices representing path to parent
        """
        for i, node in enumerate(nodes):
            collector.append(node)
            current_path = path_prefix + (i,)

            # Cache doc_id for this path
            doc_id = getattr(node, "_document_id", None)
            if doc_id:
                self._path_to_docid[current_path] = str(doc_id)

            # Recurse into children
            children = list(node._children) if node._children else []
            if children:
                self._collect_all_nodes(children, collector, current_path)

    def select(self, document_id: str) -> bool:
        """Select item by document ID."""
        index_path = self._find_index_path(document_id)
        if index_path:
            self._tree_controller.setSelectionIndexPath_(index_path)
            return True
        return False

    def _find_index_path(
        self, document_id: str, nodes: list | None = None, path: list | None = None
    ) -> NSIndexPath | None:
        """Find NSIndexPath to document."""
        if nodes is None:
            nodes = self._roots
            path = []

        for i, node in enumerate(nodes):
            current = path + [i]
            if node._document_id and str(node._document_id) == document_id:
                return NSIndexPath.indexPathWithIndexes_length_(
                    at(current), len(current)
                )

            children = list(node._children) if node._children else []
            if children:
                result = self._find_index_path(document_id, children, current)
                if result:
                    return result

        return None

    def cleanup(self):
        """Remove KVO observer. Call before destroying sidebar."""
        try:
            self._tree_controller.removeObserver_forKeyPath_(
                self._observer, "selectedObjects"
            )
        except Exception:
            pass  # Observer may already be removed

    def __del__(self):
        """Ensure observer is removed on garbage collection."""
        self.cleanup()
