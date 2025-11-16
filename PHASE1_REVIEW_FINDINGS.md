# PHASE 1: REVIEW FINDINGS - Collection Rename & Delete Functionality

## Date: 2025-11-15

## Current State Analysis

### 1. Widget List Sidebar Implementation

**Location:** `src/fichero/windows/main/views/library/library_view.py`

**Key Findings:**
- Collections are displayed using `ListWidget` (Phase 6 platform-adaptive widget)
- Uses `sidebar` renderer for narrow Library column layout
- Selection handler: `_on_tree_select()` wraps ListWidget selection and calls `_on_collection_selected()`
- No double-click handler currently wired to ListWidget
- ListWidget supports `on_activate` parameter for double-click handling
- No context menu support currently implemented

**Code snippet:**
```python
self.collections_list = ListWidget(
    headings=['Collections'],
    data=tree_data,
    on_select=self._on_tree_select,  # Single-click selection
    style=Pack(flex=1, margin_left=2),
    renderer='sidebar'
)
```

### 2. LibraryManager Backend API

**Location:** `src/fichero/library/library_manager.py`

**Existing Methods Found:**

#### `rename_collection()` - Lines 431-474
```python
async def rename_collection(self, collection_id: str, new_name: str) -> bool
```
- ✅ Already implemented
- Validates collection exists
- Allows duplicate names (collections use UUID)
- Updates collection.name and collection.updated_at
- Calls storage.update_collection()
- Clears cache
- Emits "collection_updated" navigation event
- Returns True on success, False on failure

#### `delete_collection()` - Lines 387-429
```python
async def delete_collection(self, collection_id: str) -> bool
```
- ✅ Already implemented
- Validates collection exists
- Cleans up thumbnails via `_delete_collection_thumbnails()`
- Removes local files if type="local" (with error handling)
- Calls storage.delete_collection()
- Clears cache
- Emits "collection_deleted" navigation event
- Returns True on success, False on failure

**Conclusion:** Backend API is complete and ready to use!

### 3. Command System

**Location:** `src/fichero/shared/commands/command.py`

**FicheroCommand Pattern:**
- Commands are defined using `FicheroCommand` class
- Support for menus (desktop), toolbars (both platforms), and keyboard shortcuts
- Commands registered in `define_commands()` method of views
- Example structure:
```python
'command_name': FicheroCommand(
    id=f'{self.view_id}.command_id',
    label=_("Command Label"),
    action=self._on_command_action,
    shortcut=toga.Key.MOD_1 + 'x',
    icon='resources/icons/toolbar/icon.png',
    group=toga.Group.FILE,
    section=0,
    order=0,
    show_in_menu=True,
    show_in_top_toolbar=False,
    desktop_only=True
)
```

**Current Library View Commands:**
- `new_collection` - File menu, Cmd+N
- `new_collection_from_folder` - File menu only
- `settings`, `processing`, `about`, `activity` - Window/App menus
- `inspector`, `plans`, `prompts`, `output` - Tools/App menus
- Edit mode commands for mobile

**Missing Commands:**
- ❌ No `rename_collection` command
- ❌ No `delete_collection` command

### 4. Collection Selection Flow

**Selection Chain:**
1. User clicks collection in sidebar
2. `ListWidget` fires `on_select` callback
3. `_on_tree_select()` wrapper converts selection format
4. `_on_collection_selected()` processes selection
5. Updates `self.selected_collection`
6. Navigates to collection view

**Current Selection Storage:**
```python
self.selected_collection: Optional[Dict[str, Any]] = None
```

## What's Missing

### Rename Functionality
1. ❌ No UI trigger for rename (no double-click handler, no context menu, no button)
2. ❌ No rename dialog/input field
3. ❌ No FicheroCommand for rename action
4. ✅ Backend method exists and works

### Delete Functionality
1. ❌ No "Delete Collection" command in File menu
2. ❌ No FicheroCommand definition
3. ❌ No confirmation dialog
4. ❌ No UI refresh after delete
5. ✅ Backend method exists and works

## Recommended Approach

### For Rename:
**Option A: Double-Click to Rename** (Recommended)
- Wire `on_activate` to ListWidget
- Show Toga TextInput dialog on double-click
- Call `library_service.rename_collection()`
- Refresh collections list

**Option B: Context Menu**
- Requires platform-specific implementation
- More complex, less portable
- Not recommended for Phase 1

**Option C: Toolbar Button**
- "Rename" button in edit mode
- Simpler but less discoverable
- Could be Phase 2 addition

### For Delete:
**Recommended: File Menu Command**
- Add `delete_collection` FicheroCommand
- Add to File menu (section=1, after New Collection)
- Keyboard shortcut: Cmd+Backspace or Cmd+Delete
- Show confirmation dialog before delete
- Refresh collections list after delete
- Disable when no collection selected

## Implementation Complexity

**Rename:** Medium
- Need double-click detection
- Need input dialog
- Need validation (empty name check)
- Need list refresh

**Delete:** Medium
- Need FicheroCommand definition
- Need confirmation dialog
- Need command enable/disable logic
- Need list refresh
- Need to handle edge case: deleting currently viewed collection

## Files to Modify

1. `src/fichero/windows/main/views/library/library_view.py`
   - Add `on_activate` to ListWidget
   - Add rename handler method
   - Add delete command to `define_commands()`
   - Add delete handler method
   - Add dialogs for rename input and delete confirmation
   - Update command enabled state on selection change

2. `src/fichero/shared/commands/command.py` (no changes needed)

3. `src/fichero/library/library_manager.py` (no changes needed)

## Next Steps

Proceed to PHASE 2: Create detailed implementation plan with specific code locations and snippets.
