# Phase 2: Drag-and-Drop Validation Rules

**Date:** November 26, 2025
**Status:** Planning

---

## Overview

Enhance drag-and-drop functionality to support:
1. Dropping files on **Inbox** → Import to inbox collection
2. Dropping files on **section headers** → Create new collection in that section
3. Dropping on **collections** → Import to that specific collection
4. **Section-aware** drag validation

---

## Current Implementation Analysis

### Existing Drag-and-Drop Support

**File:** `src/fichero/shared/widgets/list_widget/renderers/macos_sidebar.py`

**Current Behavior:**
- ✅ Internal collection reordering (drag collection to new position)
- ✅ External file/folder drops (creates new local collection)
- ✅ Prevents dropping into items (only root-level drops allowed)
- ❌ **Missing**: Drop target awareness (which collection/section?)
- ❌ **Missing**: Section header drop support
- ❌ **Missing**: Inbox-specific drop handling

**Current Callbacks:**
- `_on_collection_reorder(collection_id, new_position)` - Reorder collections
- `_on_external_drop(file_urls)` - Import external files/folders

**validateDrop Logic (lines 363-413):**
```python
if has_collection_uti:
    return 16  # NSDragOperationMove (internal reorder)
elif has_file_url:
    return 1   # NSDragOperationCopy (import file/folder)
```

**acceptDrop Logic (lines 415-509):**
```python
if has_collection_uti:
    # Reorder collection to new position
    renderer.set_reorder_callback(collection_id, index)
elif has_file_url:
    # Import files to library (creates new collection)
    renderer.set_import_callback(file_urls)
```

---

## Requirements

### 1. Drop Target Detection

Need to identify WHERE the drop is happening:

**Drop Targets:**
- **Section Header** (e.g., "Inbox", "Library", "External Folders")
- **Collection Item** (e.g., specific collection in a section)
- **Empty Space** (between items, not on any specific item)

**NSOutlineView Parameters:**
- `item` - The item being dropped ON (None = root level)
- `index` - The child index where drop will occur

### 2. Enhanced Drop Rules

| Drop Source | Drop Target | Action | Operation |
|-------------|-------------|--------|-----------|
| External file | **Inbox section** | Import to inbox collection | Copy |
| External file | **Library section** | Create new local collection | Copy |
| External file | **External section** | Create new external collection | Link |
| External file | **Any collection** | Add to that collection | Copy |
| Collection | **Same section** | Reorder within section | Move |
| Collection | **Different section** | Convert type + move | Move |
| Collection | **Inbox** | Not allowed (system collection) | None |

### 3. Inbox-Specific Handling

**Requirements:**
- Dropping files on Inbox → Import files to inbox collection
- Inbox collection cannot be moved/reordered (it's always first)
- Other collections cannot be dropped into Inbox section

---

## Implementation Plan

### Step 1: Enhance Widget Data with Drop Context

**File:** `src/fichero/windows/main/views/library/sidebar_data_model.py`

Add metadata to widget items to identify drop targets:

```python
def to_widget_item(self) -> Dict[str, Any]:
    return {
        'text': self.title,
        'icon': self.icon,
        '_is_section_header': True,
        '_section_id': self.id,
        '_can_accept_files': True,  # NEW: Sections can accept file drops
        '_can_accept_collections': False,  # NEW: Can't drop collections on headers
        # ...
    }
```

```python
def to_widget_item(self, folder_icon_cache=None) -> Dict[str, Any]:
    return {
        'text': self.name,
        'icon': icon,
        '_collection_data': {...},
        '_can_accept_files': not self.metadata.get('is_inbox'),  # NEW: Inbox protected
        '_can_accept_collections': not self.metadata.get('is_inbox'),  # NEW
        # ...
    }
```

### Step 2: Add Drop Target Lookup in Renderer

**File:** `src/fichero/shared/widgets/list_widget/renderers/macos_sidebar.py`

Add helper method to get drop target information:

```python
def _get_drop_target_info(self, index: int) -> Dict[str, Any]:
    """
    Get information about the drop target at the given index.

    Args:
        index: The index where drop is proposed

    Returns:
        Dict with drop target info:
        {
            'type': 'section_header' | 'collection' | 'empty',
            'section_id': str,
            'collection_id': str | None,
            'can_accept_files': bool,
            'can_accept_collections': bool
        }
    """
    # Get item data at index from widget_data
    if 0 <= index < len(self.interface._widget_data):
        item = self.interface._widget_data[index]

        if item.get('_is_section_header'):
            return {
                'type': 'section_header',
                'section_id': item.get('_section_id'),
                'collection_id': None,
                'can_accept_files': item.get('_can_accept_files', True),
                'can_accept_collections': item.get('_can_accept_collections', False)
            }
        elif item.get('_collection_data'):
            col_data = item['_collection_data']
            return {
                'type': 'collection',
                'section_id': col_data.get('section_id'),
                'collection_id': col_data.get('id'),
                'can_accept_files': item.get('_can_accept_files', True),
                'can_accept_collections': item.get('_can_accept_collections', True)
            }

    return {
        'type': 'empty',
        'section_id': None,
        'collection_id': None,
        'can_accept_files': False,
        'can_accept_collections': False
    }
```

### Step 3: Update validateDrop Logic

```python
def outlineView_validateDrop_proposedItem_proposedChildIndex_(
    self, outline_view, drag_info, item, index: int
) -> int:
    """Enhanced validation with drop target awareness"""
    try:
        # Get drop target info
        target = self._get_drop_target_info(index)

        pasteboard = drag_info.draggingPasteboard
        types = pasteboard.types

        has_collection_uti = False
        has_file_url = False

        for i in range(len(types)):
            type_str = str(types[i])
            if type_str == "com.fichero.collection.id":
                has_collection_uti = True
            elif type_str == "public.file-url":
                has_file_url = True

        if has_collection_uti:
            # Collection drag - check if target accepts collections
            if target['can_accept_collections']:
                return 16  # NSDragOperationMove
            else:
                return 0  # Reject (can't drop on section headers or inbox)

        elif has_file_url:
            # File drag - check if target accepts files
            if target['can_accept_files']:
                if target['type'] == 'collection':
                    return 1  # NSDragOperationCopy (add to collection)
                elif target['type'] == 'section_header':
                    return 1  # NSDragOperationCopy (create collection in section)
            return 0  # Reject

        return 0  # NSDragOperationNone

    except Exception as e:
        logger.error(f"Error in validateDrop: {e}", exc_info=True)
        return 0
```

### Step 4: Update acceptDrop Logic

```python
def outlineView_acceptDrop_item_childIndex_(
    self, outline_view, drag_info, item, index: int
) -> bool:
    """Enhanced drop handling with target context"""
    try:
        # Get drop target info
        target = self._get_drop_target_info(index)

        pasteboard = drag_info.draggingPasteboard
        types = pasteboard.types

        has_collection_uti = False
        has_file_url = False

        for i in range(len(types)):
            type_str = str(types[i])
            if type_str == "com.fichero.collection.id":
                has_collection_uti = True
            elif type_str == "public.file-url":
                has_file_url = True

        if has_collection_uti:
            # Collection reordering
            collection_id = pasteboard.stringForType_("com.fichero.collection.id")

            if target['type'] == 'collection':
                # Dropping on another collection - might trigger section change
                return self._handle_collection_move(collection_id, target, index)
            else:
                # Standard reordering
                return self._handle_collection_reorder(collection_id, index)

        elif has_file_url:
            # File/folder import
            file_list = pasteboard.propertyListForType_("public.file-url")

            if target['type'] == 'collection':
                # Import to specific collection
                return self._handle_import_to_collection(
                    file_list,
                    target['collection_id']
                )
            elif target['type'] == 'section_header':
                # Create new collection in section
                return self._handle_import_to_section(
                    file_list,
                    target['section_id']
                )

        return False

    except Exception as e:
        logger.error(f"Error in acceptDrop: {e}", exc_info=True)
        return False
```

### Step 5: Add New Callbacks in Library View

**File:** `src/fichero/windows/main/views/library/library_view.py`

Add new callback methods:

```python
def _on_import_to_collection(self, file_urls: list, collection_id: str) -> bool:
    """Import files to a specific collection"""
    # Implementation in Phase 4

def _on_import_to_section(self, file_urls: list, section_id: str) -> bool:
    """Create new collection in section and import files"""
    # Implementation in Phase 4

def _on_collection_move_to_section(self, collection_id: str, target_section_id: str) -> bool:
    """Move collection to different section (triggers type conversion)"""
    # Implementation in Phase 3
```

---

## Testing Strategy

### Unit Tests

1. **Drop target detection tests**
   - Test `_get_drop_target_info()` with various indices
   - Verify section header detection
   - Verify collection detection
   - Verify empty space handling

2. **Drop validation tests**
   - Test file drop on Inbox → Accept
   - Test file drop on section header → Accept
   - Test collection drop on section header → Reject
   - Test collection drop on Inbox → Reject
   - Test file drop on collection → Accept

### Manual Testing Scenarios

1. Drag file from Finder onto Inbox section → Should import to inbox collection
2. Drag file onto "Library" section header → Should create new local collection
3. Drag file onto "External Folders" header → Should create new external collection
4. Drag file onto existing collection → Should add to that collection
5. Drag collection onto another collection → Should reorder (same section) or reject (different section for now)
6. Try to drag collection onto Inbox → Should be rejected

---

## Implementation Checklist

- [ ] Add `_can_accept_files` and `_can_accept_collections` to SidebarSection.to_widget_item()
- [ ] Add `_can_accept_files` and `_can_accept_collections` to SidebarCollection.to_widget_item()
- [ ] Implement `_get_drop_target_info()` in MacOSSidebarRenderer
- [ ] Update `validateDrop` with target-aware logic
- [ ] Update `acceptDrop` with target-aware logic
- [ ] Add helper methods: `_handle_collection_move()`, `_handle_import_to_collection()`, `_handle_import_to_section()`
- [ ] Wire up new callbacks in library_view.py (stubs for Phase 3/4)
- [ ] Create unit tests for drop target detection
- [ ] Create unit tests for drop validation rules
- [ ] Manual testing with real drag operations

---

## Files to Modify

1. `src/fichero/windows/main/views/library/sidebar_data_model.py` - Add drop metadata
2. `src/fichero/shared/widgets/list_widget/renderers/macos_sidebar.py` - Enhanced validation
3. `src/fichero/windows/main/views/library/library_view.py` - New callback stubs

---

## Dependencies

- **Phase 1**: ✅ Complete (inbox system in place)
- **Phase 3**: Collection type conversion (will use stubs for now)
- **Phase 4**: Collection management operations (will use stubs for now)

---

## Next Steps

After Phase 2 completion:
- Phase 3: Implement collection type conversion
- Phase 4: Wire up full collection management operations
