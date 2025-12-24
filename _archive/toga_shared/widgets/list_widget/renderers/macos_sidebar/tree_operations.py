"""
Tree manipulation operations for hierarchical sidebar data.

These are Python helper functions used by NSOutlineViewSidebar for drag-drop
reordering and tree management.

================================================================================
TREE DATA STRUCTURE
================================================================================

The sidebar uses a nested dict structure to represent hierarchical data:

    [
        {
            'text': 'SMART COLLECTIONS',      # Display text
            '_is_section_header': True,        # Collapsible section header
            '_has_children': True,             # Has child items
            '_children': [                     # Child items list
                {
                    'text': 'Flagged',
                    '_collection_data': {'id': 'flagged-uuid', 'name': 'Flagged'},
                    'icon': 'star',
                },
                {
                    'text': 'Archive',
                    '_can_accept_drops': True,  # Folder that can receive drops
                    '_children': [...],
                },
            ],
        },
        {
            'text': 'COLLECTIONS',
            '_is_section_header': True,
            '_children': [...],
        },
    ]

SPECIAL FIELDS:
---------------
- _is_section_header: bool - If True, item is a collapsible section
- _has_children: bool - If True, item has children (shows disclosure triangle)
- _children: list - List of child item dicts
- _can_accept_drops: bool - If True, item can receive drops (folder behavior)
- _collection_data: dict - Library collection metadata (contains 'id' for identification)
- text: str - Display text (also used as fallback ID)
- icon: str - Optional icon name/path

ITEM IDENTIFICATION:
--------------------
Items are identified for drag-drop by get_item_id() which checks:
1. _collection_data.id (for library collections)
2. text field (fallback for demo/generic items)

This allows the sidebar to work with both real library collections (using UUIDs)
and demo data (using text as ID).

================================================================================
FUNCTIONS IN THIS MODULE
================================================================================

Tree Search:
- get_item_id(item) -> str: Get unique identifier for an item
- find_item_by_id(data, id) -> dict|None: Find item anywhere in tree
- find_item_in_tree(data, id) -> (item, parent, index): Find with location info

Tree Validation:
- is_descendant_of(item, id) -> bool: Check if id is contained within item

Tree Modification:
- remove_item_from_parent(item, parent, data) -> bool: Remove from _children
- insert_item_into_parent(item, parent, index, data) -> bool: Insert into _children

Data Cleaning:
- clean_item_data(item) -> dict: Remove non-serializable values for ObjC

Utilities:
- flatten_tree(items) -> list: Convert tree to flat list

================================================================================
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


def clean_item_data(item) -> dict:
    """
    Clean item data for NSOutlineView storage.

    Converts various item types to clean dicts, removing None values and
    non-serializable objects (toga.Image, etc).

    Args:
        item: Item data (dict, Row object, or other)

    Returns:
        Cleaned dictionary safe for storage
    """
    # Convert Row objects to plain dicts
    if hasattr(item, '__dict__'):
        data_dict = {k: v for k, v in item.__dict__.items() if not k.startswith('_')}
    elif hasattr(item, '_asdict'):
        data_dict = item._asdict()
    elif isinstance(item, dict):
        data_dict = item
    else:
        data_dict = {'text': str(item)}

    # Filter out non-serializable objects - keep primitives and lists
    # IMPORTANT: Skip None values - NSDictionary cannot contain nil
    clean_dict = {}
    for k, v in data_dict.items():
        if v is None:
            continue
        elif isinstance(v, (str, int, float, bool)):
            clean_dict[k] = v
        elif isinstance(v, list):
            if k == '_children' and v:
                # Recursively clean child dicts
                cleaned_children = []
                for child in v:
                    if isinstance(child, dict):
                        cleaned_children.append(clean_item_data(child))
                    else:
                        cleaned_children.append(child)
                clean_dict[k] = cleaned_children
            else:
                clean_dict[k] = v
        # Skip complex objects like toga.Image

    return clean_dict


def get_item_id(item_data: dict) -> str:
    """
    Get unique identifier for an item.

    Tries collection ID first (for library integration), then falls back to text.

    Args:
        item_data: Item dictionary

    Returns:
        Unique identifier string, or empty string if none found
    """
    if not isinstance(item_data, dict):
        return ""

    # Try collection ID first (for library integration)
    collection_data = item_data.get('_collection_data')
    if collection_data:
        collection_id = collection_data.get('id', '')
        if collection_id:
            return str(collection_id)

    # Fallback: use text field
    return item_data.get('text', '')


def find_item_by_id(data_list: list, item_id: str) -> Optional[dict]:
    """
    Find an item in the tree by its ID.

    Args:
        data_list: List of item dicts to search (can be nested)
        item_id: The identifier to search for (collection ID or text)

    Returns:
        The item dict if found, None otherwise
    """
    if not isinstance(data_list, list):
        return None

    for item in data_list:
        if not isinstance(item, dict):
            continue

        # Check if this item matches
        # Try collection ID first (for library integration), then fall back to text
        collection_data = item.get('_collection_data')
        if collection_data:
            collection_id = collection_data.get('id', '')
            if collection_id and collection_id == item_id:
                return item

        # Fallback: check text field (for demo/generic items)
        if item.get('text') == item_id:
            return item

        # Recursively search children
        children = item.get('_children', [])
        if children:
            found = find_item_by_id(children, item_id)
            if found:
                return found

    return None


def is_descendant_of(item_data: dict, ancestor_id: str) -> bool:
    """
    Check if item_data is the same as or contains ancestor_id in its children.

    This is used for circular reference detection during drag-drop:
    - If dropping ON item X, check if X contains the dragged item as a child
    - If true, the drop would create a circular reference

    Note: The name is slightly misleading - this checks if item_data CONTAINS
    ancestor_id, not if item_data IS a descendant of ancestor_id.

    Args:
        item_data: The potential container item data dict
        ancestor_id: The identifier to search for (collection ID or text)

    Returns:
        True if item_data's ID matches ancestor_id or if ancestor_id is found
        in item_data's children
    """
    if not isinstance(item_data, dict):
        return False

    # Get this item's ID
    item_id = get_item_id(item_data)

    # Check if this item IS the ancestor (same ID)
    if item_id and item_id == ancestor_id:
        return True

    # Recursively check children to see if ancestor_id is nested inside
    children = item_data.get('_children', [])
    if children:
        for child in children:
            if isinstance(child, dict):
                child_id = get_item_id(child)
                if child_id and child_id == ancestor_id:
                    return True
                # Recurse into child's children
                if is_descendant_of(child, ancestor_id):
                    return True

    return False


def find_item_in_tree(
    data_list: list,
    item_id: str,
    parent_data: dict = None
) -> Tuple[Optional[dict], Optional[dict], int]:
    """
    Find an item in the tree and return (item_dict, parent_dict, index_in_parent).

    Args:
        data_list: List of items to search
        item_id: Unique identifier of item to find (collection ID or text)
        parent_data: Parent item being searched (None for root level)

    Returns:
        Tuple of (item_dict, parent_dict, index_in_parent) or (None, None, -1) if not found
    """
    for i, item in enumerate(data_list):
        if not isinstance(item, dict):
            continue

        # Check if this is the item we're looking for using get_item_id()
        # This properly checks collection ID first, then falls back to text
        if get_item_id(item) == item_id:
            return (item, parent_data, i)

        # Recursively search children
        children = item.get('_children', [])
        if children:
            result = find_item_in_tree(children, item_id, item)
            if result[0] is not None:
                return result

    return (None, None, -1)


def remove_item_from_parent(item: dict, parent: dict, data_list: list) -> bool:
    """
    Remove an item from its parent's _children list.

    Args:
        item: Item dict to remove
        parent: Parent dict (None for root level)
        data_list: Root data list (used when parent is None)

    Returns:
        True if removed successfully
    """
    try:
        item_id = get_item_id(item)
        if parent is None:
            # Remove from root level by ID (not identity!)
            for i, existing in enumerate(data_list):
                if get_item_id(existing) == item_id:
                    data_list.pop(i)
                    logger.debug(f"Removed '{item.get('text')}' from root level")
                    return True
        else:
            # Remove from parent's children by ID
            children = parent.get('_children', [])
            for i, existing in enumerate(children):
                if get_item_id(existing) == item_id:
                    children.pop(i)
                    logger.debug(f"Removed '{item.get('text')}' from parent '{parent.get('text')}'")
                    return True

        return False
    except Exception as e:
        logger.error(f"Error removing item from parent: {e}", exc_info=True)
        return False


def insert_item_into_parent(item: dict, parent: dict, index: int, data_list: list) -> bool:
    """
    Insert an item into a parent's _children list at the specified index.

    Args:
        item: Item dict to insert
        parent: Parent dict (None for root level)
        index: Position to insert at (-1 for end)
        data_list: Root data list (used when parent is None)

    Returns:
        True if inserted successfully
    """
    try:
        if parent is None:
            # Insert at root level (data_list)
            if index == -1 or index >= len(data_list):
                data_list.append(item)
                logger.debug(f"Inserted '{item.get('text')}' at root level (end)")
            else:
                data_list.insert(index, item)
                logger.debug(f"Inserted '{item.get('text')}' at root level index {index}")
            return True
        else:
            # Insert into parent's children
            children = parent.get('_children', [])
            if index == -1 or index >= len(children):
                children.append(item)
                logger.debug(f"Inserted '{item.get('text')}' into '{parent.get('text')}' (end)")
            else:
                children.insert(index, item)
                logger.debug(f"Inserted '{item.get('text')}' into '{parent.get('text')}' at index {index}")

            # Ensure parent knows it has children
            parent['_has_children'] = True
            return True

    except Exception as e:
        logger.error(f"Error inserting item into parent: {e}", exc_info=True)
        return False


def flatten_tree(items: list, result: list = None) -> list:
    """
    Flatten hierarchical tree data into a flat list.

    Args:
        items: List of root items
        result: Accumulator list (used for recursion)

    Returns:
        Flat list of all items in tree order
    """
    if result is None:
        result = []

    for item in items:
        if isinstance(item, dict):
            result.append(item)
            # Recursively add children
            children = item.get('_children', [])
            if children:
                flatten_tree(children, result)

    return result


__all__ = [
    'clean_item_data',
    'get_item_id',
    'find_item_by_id',
    'is_descendant_of',
    'find_item_in_tree',
    'remove_item_from_parent',
    'insert_item_into_parent',
    'flatten_tree',
]
