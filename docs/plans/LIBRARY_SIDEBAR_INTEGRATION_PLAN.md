# Comprehensive Library-Sidebar Integration Plan

## Executive Summary

This plan addresses integrating the Library with the NSOutlineView sidebar, enabling full CRUD operations (Create, Read, Update, Delete), drag-and-drop, search filtering, and proper collection view hookup.

## Root Cause Analysis (Completed)

### Issue Identified
The sidebar shows only 1 item (Library section) because **Inbox's `metadata.is_inbox` is `None` instead of `True`**.

### Evidence from Debug Logs
```
🔍 LOAD INPUT: 'Inbox' type='local' is_inbox=None    <-- BUG
🔍 LOAD: Added 'Inbox' to section 'local'            <-- Wrong section
🔍 Section 'Favorites' (id=favorites) has 0 collections
🔍 Skipping empty section 'Favorites'
🔍 DEBUG: formatted data has 1 root items            <-- Only Library section
```

### Additional Issue
- **Segmentation fault** when clicking on collection item in sidebar
- Need to investigate selection handling in NSOutlineView

---

## Phase 1: Fix Inbox Metadata (Immediate)

### Task 1.1: Fix Inbox `is_inbox` Flag

**File**: `src/fichero/library/library_manager.py` or where Inbox is created

**Problem**: When Inbox collection is created, `metadata.is_inbox` is not being set to `True`.

**Fix Options**:
1. **Fix at source**: Set `is_inbox=True` in Inbox creation code
2. **Fix at query**: Ensure `get_collections_for_ui()` returns proper metadata
3. **Fix at model**: Add fallback check for `name == 'Inbox'`

**Recommended**: Fix at source - find where Inbox is created and ensure metadata includes `is_inbox: True`.

### Task 1.2: Verify Fix

```python
# Expected after fix:
🔍 LOAD INPUT: 'Inbox' type='local' is_inbox=True
🔍 LOAD: Added 'Inbox' to section 'favorites'
🔍 Section 'Favorites' (id=favorites) has 1 collections
```

---

## Phase 2: Fix Selection/Segfault Issue

### Task 2.1: Investigate Segfault

**Error Location**: `error_handler.py:78` during item selection

**Likely Cause**: NSOutlineView selection callback accessing deallocated object

**Fix Approach**:
1. Add null checks in `_on_tree_select()`
2. Ensure Python objects are retained during ObjC callbacks
3. Use `@objc_keep` decorator if needed

### Task 2.2: Test Selection

Write unit test for selection handling:
```python
def test_sidebar_selection_handling():
    # Test section header click (should be ignored)
    # Test collection click (should select and show in collection view)
    # Test folder click (should filter collection view)
```

---

## Phase 3: CRUD Operations for Sidebar

### Task 3.1: Create Collection (New)

**Current**: `New Collection` command exists in toolbar

**Integration**:
1. Call `library_manager.create_collection(name, type='local')`
2. Refresh sidebar with `sidebar_model.load_from_library_data()`
3. Select new collection in sidebar
4. Open rename dialog immediately

**Test**:
```python
def test_create_collection_appears_in_sidebar():
    # Create collection via API
    # Verify it appears in correct section
    # Verify selection updates
```

### Task 3.2: Delete Collection

**Contextual Menu**: Right-click on collection → Delete

**Implementation**:
1. Show confirmation dialog
2. Call `library_manager.delete_collection(collection_id)`
3. Refresh sidebar
4. Select previous/next collection

**Safety**:
- Prevent deleting Inbox (system collection)
- Show warning for non-empty collections

**Test**:
```python
def test_delete_collection_removes_from_sidebar():
    # Create temporary collection
    # Delete via API
    # Verify removed from sidebar
```

### Task 3.3: Rename Collection

**Double-click or Contextual Menu**: Rename

**Implementation**:
1. Use `NSOutlineView.editColumn_row_withEvent_select_()` for inline editing
2. On commit: `library_manager.rename_collection(collection_id, new_name)`
3. Update sidebar model

**Test**:
```python
def test_rename_collection_updates_sidebar():
    # Rename via API
    # Verify sidebar shows new name
```

### Task 3.4: Contextual Menu Setup

**File**: `macos_sidebar.py` - Add `NSMenu` for right-click

**Menu Items**:
- New Collection
- New Smart Collection (future)
- ---
- Rename
- Delete
- ---
- Show in Finder (for external)
- Get Info

---

## Phase 4: Drag and Drop

### Task 4.1: Drag Collection to Reorder

**Enable**: `registerForDraggedTypes_` on NSOutlineView

**Implementation**:
1. `outlineView_writeItems_toPasteboard_`: Write collection ID
2. `outlineView_validateDrop_proposedItem_proposedChildIndex_`: Validate drop
3. `outlineView_acceptDrop_item_childIndex_`: Update sort order

**Constraints**:
- Can only reorder within same section
- Cannot drag into another section
- Inbox is always first in Favorites

### Task 4.2: Drag Files into Collection

**Implementation**:
1. Accept `NSFilenamesPboardType` drop
2. Get dropped file paths
3. Call `library_manager.add_items_to_collection(collection_id, paths)`
4. Refresh collection view

### Task 4.3: Drag Collection to Folder (External)

**Implementation**:
- Drag collection to Finder = export
- Show progress dialog

**Test**:
```python
def test_reorder_collections_within_section():
    # Simulate drag within Library section
    # Verify sort order updated
```

---

## Phase 5: Collection View Integration

### Task 5.1: Selection → Collection View Update

**Current Flow**:
```
Sidebar click → _on_tree_select() → _on_collection_selected() → CollectionView.load()
```

**Fix Required**:
1. Handle section header clicks (expand/collapse only)
2. Handle collection clicks (load collection items)
3. Handle folder clicks (filter to folder items)

### Task 5.2: Collection View Data Loading

**File**: `collection_view.py`

**Methods**:
- `load_collection_data_async(collection_id)` - Load all items
- `load_folder_data_async(collection_id, folder_id)` - Load folder items
- `filter_by_search(query)` - Search filtering

### Task 5.3: Bidirectional Sync

When collection changes in CollectionView:
1. Item added → Update sidebar badge count
2. Item deleted → Update sidebar badge count
3. Folder structure changed → Refresh sidebar folders

---

## Phase 6: Search Field Integration

### Task 6.1: Toolbar Search Field

**Current**: `NSSearchToolbarItem` exists with ID `library.search`

**Handler**: Wire `search_field.action` to `_on_search_changed()`

### Task 6.2: Search Implementation

**Options**:
1. **Filter sidebar**: Show only matching collections
2. **Filter collection view**: Show only matching items (recommended)
3. **Both**: Filter both views

**Recommended Implementation**:
```python
def _on_search_changed(self, search_field):
    query = search_field.stringValue
    if query:
        # Filter collection view items
        self.collection_view.filter_by_search(query)
    else:
        # Clear filter
        self.collection_view.clear_filter()
```

### Task 6.3: Full-Text Search

**Backend**: Use SQLite FTS5 for transcription search

**Query**:
```sql
SELECT * FROM items
WHERE collection_id = ?
AND id IN (SELECT rowid FROM items_fts WHERE items_fts MATCH ?)
```

---

## Phase 7: Code Review & Testing

### Task 7.1: Code Review Checklist

For each phase:
- [ ] Memory management (no leaks, proper retain/release)
- [ ] Thread safety (UI updates on main thread)
- [ ] Error handling (graceful failures)
- [ ] Edge cases (empty collections, special characters in names)
- [ ] Performance (lazy loading, pagination)

### Task 7.2: Unit Tests

**Test Files**:
- `tests/unit/test_sidebar_data_model.py` - Data model
- `tests/unit/test_sidebar_crud.py` - CRUD operations
- `tests/unit/test_sidebar_drag_drop.py` - Drag and drop
- `tests/unit/test_collection_view_integration.py` - View integration
- `tests/unit/test_search_integration.py` - Search

### Task 7.3: Integration Tests

**Test Scenarios**:
1. Create collection → appears in sidebar → select → shows in collection view
2. Add item to collection → badge updates → item shows in view
3. Search query → filters collection view → clear → shows all
4. Rename collection → sidebar updates → selection preserved
5. Delete collection → removed from sidebar → adjacent selected

---

## Implementation Order

| Phase | Priority | Estimated Effort |
|-------|----------|------------------|
| 1. Fix Inbox metadata | Critical | 30 min |
| 2. Fix segfault | Critical | 1-2 hours |
| 3. CRUD operations | High | 4-6 hours |
| 4. Drag and drop | Medium | 4-6 hours |
| 5. Collection view | High | 2-3 hours |
| 6. Search integration | Medium | 2-3 hours |
| 7. Testing & review | High | Ongoing |

---

## Critical Files

| File | Purpose |
|------|---------|
| `library/library_manager.py` | Backend CRUD operations |
| `library/storage.py` | SQLite storage layer |
| `views/library/sidebar_data_model.py` | Sidebar data model |
| `views/library/library_view.py` | Library view integration |
| `widgets/list_widget/renderers/macos_sidebar.py` | NSOutlineView renderer |
| `views/collection/collection_view.py` | Collection item display |

---

## Success Criteria

1. Sidebar shows 3 sections: Favorites (with Inbox), Library, External
2. Collections appear in correct sections based on type
3. Can create, rename, delete collections via contextual menu
4. Can reorder collections via drag and drop
5. Collection selection updates collection view
6. Search filters collection view items
7. All operations have unit tests
8. No memory leaks or segfaults
