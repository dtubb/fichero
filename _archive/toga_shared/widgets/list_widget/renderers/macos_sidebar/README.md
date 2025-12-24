# macOS Sidebar (NSOutlineView) Implementation

Native macOS sidebar using NSOutlineView with full drag-drop support, Finder file drops,
and contextual menus.

## Status (December 2024)

All features working:
- Drag-drop reordering within the sidebar
- Finder file drops (jpg, png, etc.) onto collections
- Contextual menus (right-click) with actions
- Option+click to expand/collapse entire subtrees (Finder-like)

## Files

| File | Purpose |
|------|---------|
| `renderer.py` | Main Python wrapper class (NSOutlineViewSidebar) |
| `objc_classes.py` | ObjC class definitions (TogaSidebar, SidebarItem, MinWidthView) |
| `tree_operations.py` | Tree manipulation helpers (find, remove, insert) |
| `constants.py` | Drag operation constants and ObjC class loading |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     NSOutlineViewSidebar                        │
│                      (renderer.py)                              │
│  - Python wrapper managing data and callbacks                   │
│  - Stores _data list and _wrapped_items (SidebarItem wrappers)  │
│  - Provides set_*_callback() methods for events                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       TogaSidebar                               │
│                    (objc_classes.py)                            │
│  - NSOutlineView subclass, acts as data source + delegate       │
│  - Sections: DataSource, Selection, RowDisplay, CellDisplay,    │
│              ContextualMenu, Expand/Collapse, DragDrop          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       SidebarItem                               │
│                    (objc_classes.py)                            │
│  - NSObject wrapper for Python dict data                        │
│  - Stored in item['_impl'] for stable identity                  │
│  - _python_data points to SAME dict as self._data               │
└─────────────────────────────────────────────────────────────────┘
```

## Key Pattern: Object Identity for Drag-Drop

The most critical insight for drag-drop to work correctly:

```
wrapper._python_data MUST point to the SAME dict as self._data
```

### Why This Matters

1. User drags an item
2. `acceptDrop` modifies `self._data` (removes/inserts item)
3. `reloadData()` causes NSOutlineView to re-query `numberOfChildren`
4. If wrappers point to COPIES of data, they return stale children -> duplication!

### The Fix

In `renderer.py:693-707`, we skip `clean_item_data()` for dicts:

```python
for item in self._data:
    if isinstance(item, dict):
        item_data = item  # Use original dict - CRITICAL!
    else:
        item_data = clean_item_data(item)  # Only clean non-dicts

    wrapper = self._get_or_create_wrapper(item_data)
```

## Drag-Drop Flow

```
DRAG START
    pasteboardWriterForItem
    └── Write item ID to pasteboard ("com.fichero.collection.id")

VALIDATION (as user hovers)
    validateDrop
    ├── Check: not self-drop, not circular reference
    ├── setDropItem:dropChildIndex: sets visual feedback
    └── Return: NSDragOperationMove or NSDragOperationNone

DROP
    acceptDrop
    ├── Get source_id from pasteboard
    ├── Determine parent_data and insert_index
    ├── Modify self._data (remove from old, insert at new)
    ├── Clear _child_cache
    ├── reloadData()
    ├── Expand root sections + target parent
    └── Fire _on_reorder_callback
```

## Visual Feedback

| index | Appearance | Meaning |
|-------|------------|---------|
| -1 | Blue highlight | Dropping ON container |
| >= 0 | Insertion line | Dropping BETWEEN children |

## Callbacks

```python
# Local reorder completed
sidebar.set_reorder_callback(lambda source_id, new_index: ...)

# File dropped from Finder (generic)
sidebar.set_import_callback(lambda paths: ...)

# File dropped on specific collection
sidebar.set_import_to_collection_callback(lambda paths, collection_id: ...)

# Contextual menu action
sidebar.set_context_menu_callback(lambda action, item_data: ...)
```

## Known Workarounds

### Return False from acceptDrop

`acceptDrop` returns `False` even on success to prevent animation segfaults.
The data is already updated and `reloadData()` shows the new position.

### Selective Expansion

After `reloadData()`, only expand:
- Root section headers
- Target parent (to show the moved item)

NOT `expandItem:expandChildren:(None, True)` - this expands entire tree!

## Implemented Features

### 1. Finder Drag-Drop (Working)

Drag files from Finder onto sidebar collections. Implementation in `objc_classes.py` lines 1364-1416.

```python
# Using readObjectsForClasses:options: API
NSURL = ObjCClass("NSURL")
NSArray = ObjCClass("NSArray")
classes = NSArray.arrayWithObject_(NSURL)
url_objects = pasteboard.readObjectsForClasses_options_(classes, None)
```

Callbacks:
```python
sidebar.set_import_callback(lambda paths: ...)              # Generic import
sidebar.set_import_to_collection_callback(lambda paths, id: ...)  # Drop on collection
```

### 2. Contextual Menus (Working)

Right-click on sidebar items shows context menu. Implementation requires `menuForEvent_` override
since NSOutlineView doesn't automatically call the delegate method.

See `objc_classes.py` lines 625-738.

Actions: rename, duplicate, reveal_in_finder, get_info, delete, new_collection

```python
sidebar.set_context_menu_callback(handle_context_menu)
```

### 3. Option+Click Expand/Collapse (Working)

Hold Option while clicking disclosure triangle to expand/collapse entire subtree.
Finder-like behavior. See `objc_classes.py` lines 864-972.

## Future Features

### Collection View Drag-Drop

Support dragging items from collection view to sidebar:

```python
# Register new type:
"com.fichero.document.ids"  # Multiple document IDs

# Add callback:
sidebar.set_items_dropped_callback(
    lambda doc_ids, target_collection_id: ...
)
```

## Testing

```bash
# Run sidebar demo (from project root)
PYTHONPATH=src python widget_list_demo.py

# Or run from demos folder
cd src/fichero/shared/widgets/list_widget/renderers/macos_sidebar/demos
PYTHONPATH=../../../../../../.. python sidebar_demo.py

# Test in actual app
briefcase dev
```

## Debugging

Enable debug logging:

```python
import logging
logging.getLogger('fichero.shared.widgets.list_widget.renderers.macos_sidebar').setLevel(logging.DEBUG)
```

Key log messages:
- `numberOfChildren('X'): N` - Data source query
- `validateDrop: ACCEPT/REJECT` - Drop validation
- `Move completed: 'X' to index N` - Successful reorder
