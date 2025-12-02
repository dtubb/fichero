# Library View Complete Implementation Plan

## Overview

This plan addresses making LibraryView fully functional with:
- Proper sidebar display (badges, icons, item counts, type indicators)
- Collection view integration
- Context menu actions (rename, delete, duplicate)
- Drag-drop from Finder (folders → external, images → local/external)
- Collection-level processing status indicators

## Current State Analysis

### Working Features
- NSOutlineView sidebar with sections (Favorites, Library, External, URLs)
- Finder drag-drop to sidebar (creates external collections)
- Context menu appears on right-click
- Collection selection triggers callback
- Unit tests passing: 53 passed, 14 skipped

### Known Issues
1. **New collection has no name displayed** - Race condition in async creation
2. **Context menu actions unimplemented** - rename, delete, duplicate are stubs
3. **No item count badges** - `badge_text` field exists but not populated
4. **No type icons** - Missing visual indicators for local/external/url
5. **No processing status** - No indicator if collection is processed
6. **Selection doesn't update CollectionView** - Integration incomplete

---

## Phase 1: Fix Core Bugs (Priority: HIGH)

### 1.1 Fix "New Collection No Name" Bug
**Location**: `library_view.py:1622-1650`

**Root Cause**: Collection created async, widget refreshes before name loads

**Fix**:
```python
# In _create_local_collection():
async def _create_local_collection(self, name: str):
    collection = await self._library_service.add_collection(name, 'local')
    # Wait for collection to be fully created before refresh
    if collection:
        await self.refresh_collections()
        # Select the new collection AFTER refresh completes
        self.select_collection(collection.id)
```

### 1.2 Implement Context Menu Actions
**Location**: `library_view.py:2817-2888`

**Actions to implement**:
- `rename` → Show rename dialog, update collection
- `delete` → Show confirmation, delete collection
- `duplicate` → Copy collection with "(Copy)" suffix
- `reveal_in_finder` → Open external path in Finder
- `get_info` → Show/focus inspector with collection metadata

---

## Phase 2: Sidebar Visual Enhancements

### 2.1 Add Item Count Badges
**Location**: `sidebar_data_model.py:SidebarCollection`

**Changes**:
```python
@dataclass
class SidebarCollection:
    id: str
    name: str
    type: str  # 'local', 'external', 'url'
    item_count: int = 0  # Add this
    is_processed: bool = False  # Add this
    source_path: Optional[str] = None
```

**Format badge_text**:
```python
def _format_item_count(count: int) -> str:
    if count >= 1_000_000:
        return f"{count/1_000_000:.1f}M"
    elif count >= 1_000:
        return f"{count/1_000:.1f}K"
    return str(count) if count > 0 else ""
```

### 2.2 Add Type Icons
**Icon mapping**:
| Type | SF Symbol | Fallback Emoji |
|------|-----------|----------------|
| local | `folder.fill` | 📁 |
| external | `link` | 🔗 |
| url | `globe` | 🌐 |
| inbox | `tray` | 📥 |

**Trailing icon for status**:
| Status | SF Symbol | Meaning |
|--------|-----------|---------|
| processed | `checkmark.circle.fill` | Ready |
| unprocessed | `circle` | Not processed |
| processing | `arrow.clockwise` | In progress |
| error | `exclamationmark.circle` | Failed |

### 2.3 Update sidebar_data_model.py
```python
def to_widget_item(self, collection: SidebarCollection) -> dict:
    return {
        'text': collection.name,
        'icon': self._get_type_icon(collection.type),
        'badge_text': self._format_item_count(collection.item_count),
        'trailing_icon': self._get_status_icon(collection.is_processed),
        'font_weight': 'semibold' if collection.name == 'Inbox' else 'regular',
        'font_style': 'italic' if collection.type == 'external' else 'normal',
        '_collection_data': {
            'id': collection.id,
            'name': collection.name,
            'type': collection.type,
            'item_count': collection.item_count,
            'is_processed': collection.is_processed,
            'source_path': collection.source_path,
        },
        '_item_id': collection.id,
        '_node_type': 'collection',
    }
```

---

## Phase 3: Collection View Integration

### 3.1 Selection Flow
When collection selected in sidebar:
1. Update `SelectionManager` with collection_id
2. Call `CollectionView.set_collection_id(id)`
3. CollectionView loads items and displays

**Current callback location**: `library_view.py:948` `_on_collection_selected()`

**Fix needed**: Ensure CollectionView receives and displays selection

### 3.2 CollectionView as Card Grid
CollectionView should display items as cards with:
- Thumbnail preview
- Filename
- Type indicator (image, folder, etc.)
- Processing status

### 3.3 Preview Pane Updates
When item selected in CollectionView:
1. PreviewImagePane shows full image
2. PreviewMetadataPane shows extracted text/metadata
3. Info pane shows detailed metadata

---

## Phase 4: Drag-Drop Improvements

### 4.1 Finder Drop Handling (Already Working)
- Folders → Create external collection
- Images → Add to target collection or create local collection

### 4.2 Internal Reordering
Enable drag-drop within sidebar to reorder collections:
- Persist order in database (sort_order field)
- Visual feedback during drag
- Respect section boundaries (can't drag Inbox out of Favorites)

### 4.3 Move to Parent/Child
Allow nesting collections under parent collections:
- Drop collection onto another → Make it child
- Currently not supported, defer to future phase

---

## Phase 5: Processing Integration

### 5.1 Collection-Level Processing
Processing happens at collection level, not individual files:
- "Process" button in toolbar
- Processes all unprocessed items in collection
- Updates `is_processed` flag when complete

### 5.2 Status Tracking
Track in `collections` table:
```sql
ALTER TABLE collections ADD COLUMN processing_status TEXT DEFAULT 'unprocessed';
-- Values: 'unprocessed', 'processing', 'processed', 'error'
```

### 5.3 Visual Feedback
Update sidebar trailing icon based on processing_status:
- Show spinner during processing
- Show checkmark when complete
- Show error icon on failure

---

## Phase 6: Demo Integration & Tests

### 6.1 Move widget_list_demo.py
Move to: `src/fichero/shared/widgets/list_widget/demos/sidebar_demo.py`

### 6.2 Update Unit Tests
Fix broken tests and add new ones:
- Test badge formatting
- Test type icon mapping
- Test context menu actions
- Test selection → CollectionView flow

---

## Implementation Order

### Sprint 1: Core Fixes (COMPLETED)
1. [x] Fix new collection name bug
2. [x] Add item count badges to sidebar (infrastructure already existed)
3. [x] Add type icons (local/external/url) (infrastructure already existed)
4. [x] Implement context menu: rename, delete

### Sprint 2: Visual Polish (COMPLETED)
5. [x] Add processing status indicators (infrastructure already existed)
6. [x] Implement context menu: duplicate, get_info, reveal
7. [x] Polish sidebar styling (basic styling in place)

### Sprint 3: Integration (COMPLETED - December 2024)
8. [x] Fix CollectionView selection integration
   - Fixed cached view pattern - collection_id was not being updated
   - Added collection_view.collection_id = collection_id in _on_show_collection
9. [x] Ensure preview pane updates on selection
   - Already wired via SELECTION_CHANGED event → _handle_preview_selection_changed
   - Loads ImagePane, MetadataPane, and AdjustView correctly
10. [ ] Add processing button to toolbar (deferred - needs Director integration)

### Sprint 4: Testing & Cleanup (COMPLETED - December 2024)
11. [x] Fix failing unit tests - 53 passed, 14 skipped
12. [x] Add new integration tests
   - Created `tests/integration/test_library_view_integration.py` with 20 tests
   - Tests cover: Collection CRUD, sidebar data formatting, context menu actions,
     selection flow, preview pane metadata requirements
13. [x] Move demo to demos folder
   - Demo already at `src/fichero/shared/widgets/list_widget/demos/`
   - Removed duplicate from project root
14. [x] Update documentation
   - Updated this plan document
   - Existing demos/README.md already comprehensive

---

## Files to Modify

| File | Changes |
|------|---------|
| `library_view.py` | Fix new collection, implement context menu |
| `sidebar_data_model.py` | Add item_count, type icons, badges |
| `library_manager.py` | Add get_item_count(), get_processing_status() |
| `collection_view.py` | Ensure selection updates display |
| `test_nsoutlineview_sidebar.py` | Fix skipped tests, add new tests |

---

## Success Criteria

1. **New collection shows name** - No blank names
2. **Item counts visible** - Badge shows count (42, 1.2K, 3.4M)
3. **Type icons visible** - local=📁, external=🔗, url=🌐
4. **Context menu works** - rename/delete/duplicate functional
5. **Selection updates CollectionView** - Click collection → see items
6. **Processing status shows** - checkmark/circle/spinner
7. **All unit tests pass** - 0 failures, minimal skips
