"""
KVO-compliant Node class for NSTreeController binding.

This mirrors Apple's Node.swift pattern for use with NSTreeController.
NSTreeController requires KVO-compliant model objects to track tree changes.

Key requirements for NSTreeController:
1. children property must be KVO-observable
2. isLeaf property determines if node can have children
3. All properties that NSOutlineView displays should be observable

IMPORTANT: This implementation uses a global dictionary for storage instead of
Python instance variables. This is necessary because Rubicon-ObjC creates fresh
ObjCInstance wrappers on each callback from Objective-C, which lose access to
Python's self._* attributes.

Usage:
    node = SidebarNode.create_from_dict(item_data)
    tree_controller.setContent_([node, ...])

See: /Users/dtubb/code/docs/NavigatingHierarchicalDataUsingOutlineAndSplitViews/SourceView/Node.swift
"""

import logging
import uuid
from typing import Dict, Any, List, Optional

from .constants import RUBICON_AVAILABLE

logger = logging.getLogger(__name__)

# Cache for the SidebarNode class
_sidebar_node_class = None

# Global storage to keep references to Python objects alive
# Key: ObjC pointer (int), Value: dict of Python data
_node_storage: Dict[int, Dict[str, Any]] = {}


def _get_ptr(obj) -> int:
    """Get the ObjC pointer from an ObjCInstance to use as storage key."""
    # The ptr property gives us the stable Objective-C object pointer
    return int(obj.ptr.value) if hasattr(obj, 'ptr') else id(obj)


def _get_array_count(arr) -> int:
    """
    Safely get the count of an NSMutableArray or ObjCListInstance.

    Rubicon-ObjC has different behaviors for .count depending on context:
    - Sometimes it's an integer property
    - Sometimes it's a bound method that needs to be called
    - ObjCListInstance wraps it differently (count() needs a value arg)

    This function handles all these cases.
    """
    if arr is None:
        return 0
    try:
        # Try using Python's len() first - works for ObjCListInstance
        return len(arr)
    except (TypeError, AttributeError):
        pass
    try:
        # Try .count as property
        cnt = arr.count
        if callable(cnt):
            return int(cnt())
        return int(cnt)
    except (TypeError, AttributeError):
        return 0


def _get_storage(obj) -> Dict[str, Any]:
    """Get the storage dict for an ObjCInstance node."""
    ptr = _get_ptr(obj)
    if ptr not in _node_storage:
        # Create storage if it doesn't exist
        from rubicon.objc import ObjCClass
        NSMutableArray = ObjCClass("NSMutableArray")
        _node_storage[ptr] = {
            'title': "",
            'identifier': "",
            'icon_name': "",
            'node_type': "item",
            'badge_text': "",
            'trailing_icon': "",
            'can_accept_drops': False,
            'is_draggable': True,
            'children': NSMutableArray.alloc().init(),
            'original_data': None,
        }
    return _node_storage[ptr]


def get_sidebar_node_class():
    """Get or create the KVO-compliant SidebarNode class."""
    global _sidebar_node_class

    if _sidebar_node_class is not None:
        return _sidebar_node_class

    if not RUBICON_AVAILABLE:
        logger.warning("Rubicon-ObjC not available - SidebarNode unavailable")
        return None

    from rubicon.objc import ObjCClass, ObjCInstance, objc_method, send_super

    NSObject = ObjCClass("NSObject")
    NSMutableArray = ObjCClass("NSMutableArray")

    class SidebarNode(NSObject):
        """
        KVO-compliant node class for NSTreeController.

        This class stores all data in a global Python dictionary keyed by
        the object's ObjC pointer. This ensures data survives across Rubicon-ObjC's
        bridging callbacks where Python instance variables would be lost.

        Key properties:
        - children: NSMutableArray of child SidebarNode objects (KVO-observed)
        - isLeaf: Boolean indicating if node can have children
        """

        @objc_method
        def init(self) -> ObjCInstance:
            """Initialize the node with default values."""
            # Call super init using send_super, wrap result in ObjCInstance
            self = ObjCInstance(send_super(__class__, self, 'init'))
            if self is None:
                return None

            # Initialize storage for this node (using module-level function)
            ptr = _get_ptr(self)
            _node_storage[ptr] = {
                'title': "",
                'identifier': "",
                'icon_name': "",
                'node_type': "item",
                'badge_text': "",
                'trailing_icon': "",
                'can_accept_drops': False,
                'is_draggable': True,
                'children': NSMutableArray.alloc().init(),
                'original_data': None,
            }

            return self

        # =====================================================================
        # KVO-compliant properties using manual KVO notifications
        # =====================================================================

        @objc_method
        def title(self):
            return _get_storage(self)['title']

        @objc_method
        def setTitle_(self, value):
            self.willChangeValueForKey_("title")
            _get_storage(self)['title'] = str(value) if value else ""
            self.didChangeValueForKey_("title")

        @objc_method
        def identifier(self):
            return _get_storage(self)['identifier']

        @objc_method
        def setIdentifier_(self, value):
            self.willChangeValueForKey_("identifier")
            _get_storage(self)['identifier'] = str(value) if value else ""
            self.didChangeValueForKey_("identifier")

        @objc_method
        def iconName(self):
            return _get_storage(self)['icon_name']

        @objc_method
        def setIconName_(self, value):
            self.willChangeValueForKey_("iconName")
            _get_storage(self)['icon_name'] = str(value) if value else ""
            self.didChangeValueForKey_("iconName")

        @objc_method
        def nodeType(self):
            return _get_storage(self)['node_type']

        @objc_method
        def setNodeType_(self, value):
            self.willChangeValueForKey_("nodeType")
            self.willChangeValueForKey_("isLeaf")
            _get_storage(self)['node_type'] = str(value) if value else "item"
            self.didChangeValueForKey_("isLeaf")
            self.didChangeValueForKey_("nodeType")

        @objc_method
        def badgeText(self):
            return _get_storage(self)['badge_text']

        @objc_method
        def setBadgeText_(self, value):
            self.willChangeValueForKey_("badgeText")
            _get_storage(self)['badge_text'] = str(value) if value else ""
            self.didChangeValueForKey_("badgeText")

        @objc_method
        def trailingIcon(self):
            return _get_storage(self)['trailing_icon']

        @objc_method
        def setTrailingIcon_(self, value):
            self.willChangeValueForKey_("trailingIcon")
            _get_storage(self)['trailing_icon'] = str(value) if value else ""
            self.didChangeValueForKey_("trailingIcon")

        @objc_method
        def canAcceptDrops(self):
            return _get_storage(self)['can_accept_drops']

        @objc_method
        def setCanAcceptDrops_(self, value):
            self.willChangeValueForKey_("canAcceptDrops")
            _get_storage(self)['can_accept_drops'] = bool(value)
            self.didChangeValueForKey_("canAcceptDrops")

        @objc_method
        def isDraggable(self):
            return _get_storage(self)['is_draggable']

        @objc_method
        def setIsDraggable_(self, value):
            self.willChangeValueForKey_("isDraggable")
            _get_storage(self)['is_draggable'] = bool(value)
            self.didChangeValueForKey_("isDraggable")

        # =====================================================================
        # Children array - THE KEY PROPERTY for NSTreeController
        # Using NSMutableArray for proper KVO compliance
        # =====================================================================

        @objc_method
        def children(self):
            """Return children array. NSTreeController observes this."""
            return _get_storage(self)['children']

        @objc_method
        def setChildren_(self, value) -> None:
            """Set children array with KVO notification.

            IMPORTANT: Returns None (void) for KVO autonotifying compliance.
            Modifies in-place to preserve NSTreeController's internal references.
            """
            self.willChangeValueForKey_("children")
            self.willChangeValueForKey_("isLeaf")
            storage = _get_storage(self)

            # Get existing array - modify in-place, don't replace
            existing = storage['children']
            if existing is None:
                existing = NSMutableArray.alloc().init()
                storage['children'] = existing

            # Clear and refill in-place (keeps same array object)
            existing.removeAllObjects()
            if value:
                count = _get_array_count(value)
                for i in range(count):
                    try:
                        obj = value.objectAtIndex_(i)
                        existing.addObject_(obj)
                    except Exception:
                        # Handle Python list
                        if hasattr(value, '__iter__'):
                            for child in value:
                                existing.addObject_(child)
                            break

            self.didChangeValueForKey_("isLeaf")
            self.didChangeValueForKey_("children")

        @objc_method
        def countOfChildren(self):
            """KVO-compliant count accessor."""
            children = _get_storage(self)['children']
            return _get_array_count(children)

        @objc_method
        def objectInChildrenAtIndex_(self, index):
            """KVO-compliant indexed accessor."""
            children = _get_storage(self)['children']
            idx = int(index)
            count = _get_array_count(children)
            if 0 <= idx < count:
                return children.objectAtIndex_(idx)
            return None

        @objc_method
        def insertObject_inChildrenAtIndex_(self, obj, index) -> None:
            """KVO-compliant indexed mutator for insert. Returns void."""
            self.willChangeValueForKey_("children")
            children = _get_storage(self)['children']
            if children is None:
                children = NSMutableArray.alloc().init()
                _get_storage(self)['children'] = children
            children.insertObject_atIndex_(obj, int(index))
            self.didChangeValueForKey_("children")

        @objc_method
        def removeObjectFromChildrenAtIndex_(self, index) -> None:
            """KVO-compliant indexed mutator for remove. Returns void."""
            self.willChangeValueForKey_("children")
            children = _get_storage(self)['children']
            idx = int(index)
            count = _get_array_count(children)
            if 0 <= idx < count:
                children.removeObjectAtIndex_(idx)
            self.didChangeValueForKey_("children")

        # =====================================================================
        # Computed properties for NSTreeController
        # =====================================================================

        @objc_method
        def isLeaf(self):
            """
            NSTreeController uses this to determine if node can have children.

            Leaf nodes:
            - Don't show disclosure triangle
            - Can't have children dropped into them

            Container nodes (non-leaf):
            - Show disclosure triangle if they have children
            - Can accept child drops
            """
            storage = _get_storage(self)
            node_type = storage['node_type']
            children = storage['children']

            # Section headers and folders are containers (not leaves)
            if node_type in ('section', 'folder'):
                return False
            # Collections can be containers if they have children
            if node_type == 'collection' and _get_array_count(children) > 0:
                return False
            # Items are always leaves
            return True

        @objc_method
        def isDirectory(self):
            """Convenience for checking if node is a container."""
            node_type = _get_storage(self)['node_type']
            return node_type in ('section', 'folder', 'collection')

        @objc_method
        def isSectionHeader(self):
            """Check if node is a section header."""
            return _get_storage(self)['node_type'] == 'section'

        # =====================================================================
        # Original data access (for sync back to Python dicts)
        # =====================================================================

        @objc_method
        def originalData(self):
            """Get the original Python dict this node was created from."""
            return _get_storage(self)['original_data']

        @objc_method
        def setOriginalData_(self, value):
            """Set the original Python dict reference."""
            _get_storage(self)['original_data'] = value

        # =====================================================================
        # Cleanup
        # =====================================================================

        @objc_method
        def dealloc(self):
            """Clean up storage when node is deallocated."""
            ptr = _get_ptr(self)
            if ptr in _node_storage:
                del _node_storage[ptr]
            # Note: Don't call super().dealloc() in Rubicon-ObjC

    _sidebar_node_class = SidebarNode
    return SidebarNode


def create_node_from_dict(item_data: Dict[str, Any]) -> Any:
    """
    Create a SidebarNode from a Python dict.

    This is the main entry point for converting existing sidebar data
    to KVO-compliant nodes for NSTreeController.

    Args:
        item_data: Dict with sidebar item properties:
            - text: Display text
            - icon: Icon name
            - _is_section_header: True for section headers
            - _can_accept_drops: True for folders that accept drops
            - _draggable: True if item can be dragged
            - _children: List of child dicts
            - _collection_data: {'id': ..., 'name': ...} for library items
            - badge_text: Badge count/text
            - trailing_icon: SF Symbol name for trailing icon

    Returns:
        SidebarNode instance, or None if Rubicon-ObjC unavailable
    """
    SidebarNode = get_sidebar_node_class()
    if SidebarNode is None:
        return None

    node = SidebarNode.alloc().init()

    # Set title
    node.setTitle_(item_data.get('text', ''))

    # Set identifier (from collection data or generate)
    collection_data = item_data.get('_collection_data', {})
    if collection_data and collection_data.get('id'):
        node.setIdentifier_(str(collection_data['id']))
    elif item_data.get('text'):
        node.setIdentifier_(item_data['text'])
    else:
        node.setIdentifier_(str(uuid.uuid4()))

    # Set icon
    node.setIconName_(item_data.get('icon', ''))

    # Determine node type
    if item_data.get('_is_section_header'):
        node.setNodeType_('section')
    elif item_data.get('_can_accept_drops'):
        node.setNodeType_('folder')
    elif item_data.get('_node_type'):
        node.setNodeType_(item_data['_node_type'])
    else:
        node.setNodeType_('collection')

    # Set other properties
    badge = item_data.get('badge_text')
    node.setBadgeText_(str(badge) if badge else '')
    node.setTrailingIcon_(item_data.get('trailing_icon', ''))
    node.setCanAcceptDrops_(bool(item_data.get('_can_accept_drops', False)))
    node.setIsDraggable_(bool(item_data.get('_draggable', True)))

    # Store original data for sync-back
    node.setOriginalData_(item_data)

    # Recursively convert children
    children_data = item_data.get('_children', [])
    if children_data:
        child_nodes = []
        for child_data in children_data:
            child_node = create_node_from_dict(child_data)
            if child_node:
                child_nodes.append(child_node)
        node.setChildren_(child_nodes)

    return node


def create_nodes_from_data(data_list: List[Dict[str, Any]]) -> List[Any]:
    """
    Convert a list of Python dicts to SidebarNode list.

    Args:
        data_list: List of sidebar item dicts

    Returns:
        List of SidebarNode objects
    """
    nodes = []
    for item_data in data_list:
        node = create_node_from_dict(item_data)
        if node:
            nodes.append(node)
    return nodes


def sync_node_to_dict(node) -> Optional[Dict[str, Any]]:
    """
    Sync a SidebarNode's current state back to its original dict.

    This is called after NSTreeController operations (like move) to update
    the Python dict representation.

    Args:
        node: SidebarNode object

    Returns:
        The updated original_data dict, or None
    """
    if node is None:
        return None

    original = node.originalData()
    if original is None:
        return None

    # Update children in original data
    children = node.children()
    count = _get_array_count(children)
    if count > 0:
        original['_children'] = [
            sync_node_to_dict(children.objectAtIndex_(i))
            for i in range(count)
        ]
        original['_has_children'] = True
    else:
        original['_children'] = []
        original['_has_children'] = False

    return original


def sync_all_nodes_to_data(nodes: List[Any]) -> List[Dict[str, Any]]:
    """
    Sync all nodes back to their original dicts after tree operations.

    Args:
        nodes: List of root SidebarNode objects

    Returns:
        List of synced Python dicts
    """
    return [sync_node_to_dict(node) for node in nodes if node is not None]


def clear_node_storage():
    """Clear all node storage. Call this when refreshing data."""
    global _node_storage
    _node_storage.clear()


__all__ = [
    'get_sidebar_node_class',
    'create_node_from_dict',
    'create_nodes_from_data',
    'sync_node_to_dict',
    'sync_all_nodes_to_data',
    'clear_node_storage',
    '_get_array_count',  # Helper for NSMutableArray count access
]
