# Phase 4 Implementation Plan: Multi-Selection Workflows

**Date**: 2025-11-15
**Phase**: 4 of 4 - Multi-Selection Workflows
**Status**: Planning Complete - Ready for Implementation
**Dependencies**: Phase 1, 2, 3 (all complete and tested)

---

## Executive Summary

Phase 4 extends the SelectionManager infrastructure (Phases 1-3) to enable batch operations on multiple selected items. The foundation is **fully functional** - multi-selection tracking works correctly and captures ALL selected items. Phase 4 focuses on **using** this selection data in workflows.

**Key Goals**:
- Enable batch delete operations (delete 5 items at once)
- Enable batch process operations (process 3 images together)
- Add user confirmations for batch operations
- Show progress for multi-item workflows
- Handle partial failures gracefully

**Scope Recommendation**: **MEDIUM** - Focus on critical workflows first (delete, process), defer advanced features (move, export) to future phases.

---

## 1. Workflow Analysis

### 1.1 Collection View Workflows

**File**: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/collection/collection_view.py`

#### Workflow 1: Delete Items
- **Location**: Line 1986 `async def _perform_delete_item(item_id, item_name)`
- **Trigger**: Swipe action on mobile (line 1939), toolbar button (desktop)
- **Current Behavior**: Deletes ONE item via `library_service.delete_collection_item(item_id)`
- **Selection Usage**: Uses swipe row data, NOT SelectionManager
- **Priority**: **HIGH** - Users expect multi-delete
- **Status**: Single-item only

#### Workflow 2: Process Items (Quick Process)
- **Location**: Line 2384 `async def _on_quick_process(plan_name, workflow_name)`
- **Current Behavior**:
  - Gets selection from `items_list.get_selection()` (line 2404)
  - Extracts FIRST item only: `selected_item_id` (singular, line 2408)
  - Falls back to all items if no selection (line 2426-2432)
  - Passes `item_ids` list to Director (line 2443)
- **Selection Usage**: Widget-level selection, NOT SelectionManager
- **Priority**: **HIGH** - Core workflow, partially supports multi-select
- **Status**: Widget returns multi-selection but code only uses first item

#### Workflow 3: Process Items (Dialog Process)
- **Location**: Line 2517 `async def _on_process_requested()`
- **Dialog**: Line 2557 `async def _show_process_dialog(collection_id, selected_item_id, selected_item_name)`
- **Current Behavior**:
  - Takes singular `selected_item_id` and `selected_item_name`
  - Processes via `_process_via_items()` (line 2591)
  - Director receives `item_ids` list but selection is always 1 item
- **Selection Usage**: Widget-level selection, NOT SelectionManager
- **Priority**: **HIGH** - Same as quick process
- **Status**: Single-item only (parameters are singular)

#### Workflow 4: Export Collection
- **Location**: Line 3003 `def _on_export_collection()`
- **Current Behavior**: Exports entire collection (no item selection)
- **Selection Usage**: None
- **Priority**: **LOW** - Not item-based
- **Status**: N/A for multi-selection

#### Workflow 5: Swipe Actions (Rename, Info)
- **Location**: Lines 1957 (rename), 1903 (info)
- **Current Behavior**: Single-item operations triggered by swipe
- **Selection Usage**: Swipe row data only
- **Priority**: **LOW** - Swipe is inherently single-item
- **Status**: Keep as single-item only

### 1.2 Library View Workflows

**File**: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/library/library_view.py`

#### Workflow 6: Delete Collection
- **Location**: Line 1384 `async def _perform_delete_collection(collection_id, collection_name)`
- **Trigger**: Swipe action (line 364), toolbar button
- **Current Behavior**: Deletes ONE collection via `library_manager.delete_collection()`
- **Selection Usage**: Swipe row data or `self.selected_collection`, NOT SelectionManager
- **Priority**: **MEDIUM** - Less common than item delete
- **Status**: Single-collection only

#### Workflow 7: Export Collection
- **Location**: Line 2175 `async def _perform_export_collection(collection_id, collection_name, output_path)`
- **Current Behavior**: Exports ONE collection to ZIP file
- **Selection Usage**: Uses `self.selected_collection`, NOT SelectionManager
- **Priority**: **LOW** - Export is slow, batch export less useful
- **Status**: Single-collection only

### 1.3 Universal Workflows

#### Workflow 8: Inspector (Show Info)
- **Location**: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/inspector/inspector_window.py` line 90
- **Current Behavior**: Shows metadata for ONE item
- **Selection Usage**: Receives first item from view (CollectionView line 1815)
- **Multi-Selection Behavior**: Should show summary "3 items selected: 2 images, 1 folder"
- **Priority**: **MEDIUM** - Nice UX improvement
- **Status**: Single-item only, but could summarize multi-selection

#### Workflow 9: Preview/Output Loading
- **Location**: CollectionView line 1824 `_load_item_outputs(item_data, file_path)`
- **Current Behavior**: Loads preview for ONE item
- **Selection Usage**: Receives first item from selection
- **Multi-Selection Behavior**: Could show grid of previews or "3 items selected"
- **Priority**: **LOW** - Complex, defer to future phase
- **Status**: Single-item only (keep as-is)

---

## 2. Current Implementation Analysis

### 2.1 Delete Item Workflow (Collection)

**File**: `collection_view.py`

**Code Location**: Lines 1986-2004
```python
async def _perform_delete_item(self, item_id: str, item_name: str):
    """Perform actual item deletion"""
    # Delete via library service
    success = await self.library_service.delete_collection_item(item_id)

    if success:
        logger.info(f"✅ Successfully deleted item: {item_name}")
        self._load_collection_items()  # Refresh
```

**Parameters Needed**:
- `item_id` (str) - Library item ID
- `item_name` (str) - For logging only

**Supports Batch**: NO - takes single ID only

**What Needs to Change**:
1. Create new method `_perform_delete_items(item_ids: List[str], item_names: List[str])`
2. Loop through items, call `delete_collection_item()` for each
3. Track successes/failures
4. Show confirmation dialog before deleting
5. Update UI after batch delete

### 2.2 Process Item Workflow (Quick Process)

**File**: `collection_view.py`

**Code Location**: Lines 2384-2443
```python
async def _on_quick_process(self, plan_name: str, workflow_name: str):
    # Get selection from widget (NOT SelectionManager)
    selection = self.items_list.get_selection()
    if selection:
        selected_row = selection  # Could be a list!
        selected_item_id = getattr(selected_row, 'item_id', None)

        if selected_item_id:
            item_ids = [selected_item_id]  # ❌ Only one item!
        else:
            item_ids = [item.id for item in all_items]  # All items fallback

    # Process using Director
    await self.app.director_integration.process_collection(...)
```

**Parameters Needed**:
- `plan_name` (str) - Plan file name like "Crop"
- `workflow_name` (str) - Workflow name like "CropTest"
- `item_ids` (list) - Already supports multiple IDs!
- `collection_id` (str) - Target collection

**Supports Batch**: YES (Director already accepts list) - just need to get ALL selected IDs

**What Needs to Change**:
1. Replace widget selection with SelectionManager
2. Get all selected item IDs (not just first)
3. Show confirmation: "Process 3 items with Crop?"
4. Pass all IDs to Director (already supported)

### 2.3 Process Item Workflow (Dialog Process)

**File**: `collection_view.py`

**Code Location**: Lines 2557-2590
```python
async def _show_process_dialog(
    self,
    collection_id: str,
    selected_item_id: Optional[str] = None,      # ❌ Singular!
    selected_item_name: Optional[str] = None     # ❌ Singular!
):
    # Show processing options dialog
    # User selects plan/workflow
    # Calls _process_via_items(selected_item_id, ...)
```

**Parameters Needed**:
- `selected_item_ids` (list) - Change from singular to plural
- `selected_item_names` (list) - Change from singular to plural

**Supports Batch**: NO - parameters are singular

**What Needs to Change**:
1. Change parameters to lists: `selected_item_ids`, `selected_item_names`
2. Update dialog to show "Processing 3 items" instead of item name
3. Pass list to `_process_via_items()`
4. `_process_via_items()` already supports lists (uses Director)

### 2.4 Delete Collection Workflow (Library)

**File**: `library_view.py`

**Code Location**: Lines 1384-1404
```python
async def _perform_delete_collection(self, collection_id: str, collection_name: str):
    """Perform actual collection deletion"""
    success = await self.app.library_manager.delete_collection(collection_id)

    if success:
        logger.info(f"✅ Successfully deleted collection: {collection_name}")
        self._load_collections()  # Refresh
```

**Parameters Needed**:
- `collection_id` (str) - Library collection ID
- `collection_name` (str) - For confirmation dialog

**Supports Batch**: NO - takes single ID only

**What Needs to Change**:
1. Create new method `_perform_delete_collections(collection_ids, collection_names)`
2. Loop through collections, delete each
3. Show confirmation with collection names
4. Track successes/failures

---

## 3. Integration Strategy

### 3.1 Getting Selection from SelectionManager

**Pattern to Use Everywhere**:
```python
# Get selected item IDs from SelectionManager
selected_item_ids = []
selected_metadata = []

if hasattr(self.app, 'selection_manager') and self.app.selection_manager:
    selected_item_ids = self.app.selection_manager.get_selection('collection')
    selected_metadata = self.app.selection_manager.get_selection_metadata('collection')
else:
    # Fallback: use widget selection (backward compatibility)
    selection = self.items_list.get_selection() if hasattr(self, 'items_list') else None
    if selection:
        # Extract IDs from widget selection (use existing _extract_item_data)
        ...
```

**Why This Pattern**:
- Graceful degradation if SelectionManager unavailable
- Uses centralized selection (Phase 3)
- Gets both IDs and metadata (for dialogs, logging)
- Context-specific: 'collection', 'library', 'steps'

### 3.2 Validation Strategy

**Check Before Batch Operation**:
```python
# Validate selection before operation
if not selected_item_ids:
    logger.info("No items selected - process all? Or show error?")
    # Decision: Process all items (existing behavior)
    return

if len(selected_item_ids) == 1:
    # Single item - use existing singular logic (faster, simpler)
    await self._perform_delete_item(selected_item_ids[0], ...)
    return

# Multi-selection - use batch logic
await self._perform_delete_items(selected_item_ids, ...)
```

**Validation Rules**:
- 0 items selected → Process all items OR show error (depends on workflow)
- 1 item selected → Use existing single-item code path (optimization)
- 2+ items selected → Use new batch code path

### 3.3 User Confirmation Strategy

**Confirmation Dialog Design**:
```python
def _show_batch_confirmation(
    self,
    operation: str,  # "Delete", "Process", "Export"
    item_count: int,
    item_names: List[str]  # Up to 5 names shown
) -> bool:
    """
    Show confirmation dialog for batch operation.

    Returns True if user confirms, False if cancelled.
    """
    # Build message
    if item_count <= 3:
        # Show all names
        items_text = "\n".join([f"• {name}" for name in item_names])
        message = f"{operation} {item_count} items?\n\n{items_text}"
    else:
        # Show first 3 + "and X more"
        items_text = "\n".join([f"• {name}" for name in item_names[:3]])
        remaining = item_count - 3
        message = f"{operation} {item_count} items?\n\n{items_text}\n• ...and {remaining} more"

    # Show Toga dialog
    result = await self.app.main_window.confirm_dialog(
        title=f"{operation} Items",
        message=message
    )

    return result
```

**When to Show Confirmation**:
- **Delete**: ALWAYS (destructive)
- **Process**: Only if 5+ items (time-consuming)
- **Export**: Only if 10+ items (very slow)
- **Move/Copy**: Only if 10+ items (file operations)

### 3.4 Progress Indication Strategy

**Simple Status Bar Updates** (Phase 4):
```python
# Before batch operation
if hasattr(self.app, 'main_window_wrapper'):
    status_bar = self.app.main_window_wrapper.status_bar
    if status_bar:
        status_bar.set_status(f"Deleting {len(item_ids)} items...")

# After batch operation (success)
status_bar.set_status(f"Deleted {successful_count} of {len(item_ids)} items")

# After batch operation (failures)
if failed_count > 0:
    status_bar.set_status(f"Deleted {successful_count} items, {failed_count} failed")
```

**Advanced Progress Dialog** (Future Phase):
- Show modal dialog with progress bar
- "Deleting item 3 of 5..."
- Cancel button to stop mid-operation
- Defer to Phase 5 or later

### 3.5 Error Handling Strategy

**Partial Failure Handling**:
```python
# Track successes and failures
successful_items = []
failed_items = []

for item_id, item_name in zip(item_ids, item_names):
    try:
        success = await self._delete_single_item(item_id)
        if success:
            successful_items.append(item_name)
        else:
            failed_items.append((item_name, "Delete returned False"))
    except Exception as e:
        failed_items.append((item_name, str(e)))
        logger.error(f"Failed to delete {item_name}: {e}")

# Report results
if failed_items:
    # Show error summary
    error_text = "\n".join([f"• {name}: {reason}" for name, reason in failed_items])
    await self._show_error_dialog(
        title="Some Items Failed",
        message=f"Deleted {len(successful_items)} items successfully.\n\n"
                f"Failed to delete {len(failed_items)} items:\n{error_text}"
    )
else:
    # All succeeded
    logger.info(f"✅ Successfully deleted {len(successful_items)} items")
```

**Error Recovery**:
- Continue processing remaining items even if some fail
- Log each failure with traceback
- Show summary at end (not N dialogs)
- Refresh UI to show current state

---

## 4. Detailed Implementation Steps

### Step 1: Collection Delete Workflow (1 day)

**Goal**: Enable deleting multiple selected items at once.

**Files to Modify**:
- `src/fichero/windows/main/views/collection/collection_view.py`

**Implementation**:

**1.1 Create Batch Delete Method** (NEW, after line 2004):
```python
async def _perform_delete_items(self, item_ids: List[str], item_names: List[str]):
    """
    Delete multiple items with progress tracking and error handling.

    Args:
        item_ids: List of item IDs to delete
        item_names: List of item names (for logging/reporting)
    """
    try:
        logger.info(f"Batch delete: {len(item_ids)} items")

        # Show confirmation dialog
        confirmed = await self._show_batch_confirmation(
            operation="Delete",
            item_count=len(item_ids),
            item_names=item_names
        )

        if not confirmed:
            logger.info("Batch delete cancelled by user")
            return

        # Update status bar
        if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
            if hasattr(self.app.main_window_wrapper, 'status_bar'):
                self.app.main_window_wrapper.status_bar.set_status(
                    f"Deleting {len(item_ids)} items..."
                )

        # Delete each item, track results
        successful = []
        failed = []

        for item_id, item_name in zip(item_ids, item_names):
            try:
                success = await self.library_service.delete_collection_item(item_id)
                if success:
                    successful.append(item_name)
                    logger.info(f"✅ Deleted: {item_name}")
                else:
                    failed.append((item_name, "Delete returned False"))
                    logger.warning(f"❌ Failed to delete: {item_name}")
            except Exception as e:
                failed.append((item_name, str(e)))
                logger.error(f"❌ Exception deleting {item_name}: {e}")

        # Report results
        if failed:
            # Some failures
            error_text = "\n".join([f"• {name}: {reason}" for name, reason in failed[:5]])
            if len(failed) > 5:
                error_text += f"\n• ...and {len(failed) - 5} more"

            await self.app.main_window.info_dialog(
                title="Deletion Summary",
                message=f"Deleted {len(successful)} of {len(item_ids)} items.\n\n"
                        f"Failed items:\n{error_text}"
            )
        else:
            # All succeeded
            logger.info(f"✅ Successfully deleted all {len(successful)} items")

        # Update status bar
        if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
            if hasattr(self.app.main_window_wrapper, 'status_bar'):
                if failed:
                    self.app.main_window_wrapper.status_bar.set_status(
                        f"Deleted {len(successful)} items, {len(failed)} failed"
                    )
                else:
                    self.app.main_window_wrapper.status_bar.set_status(
                        f"Deleted {len(successful)} items"
                    )

        # Refresh collection view
        self._load_collection_items()

        # Clear selection
        if hasattr(self.app, 'selection_manager') and self.app.selection_manager:
            self.app.selection_manager.clear_selection('collection')

    except Exception as e:
        logger.error(f"Failed batch delete: {e}")
        import traceback
        traceback.print_exc()
```

**1.2 Add Confirmation Dialog Helper** (NEW, after batch delete method):
```python
async def _show_batch_confirmation(
    self,
    operation: str,
    item_count: int,
    item_names: List[str]
) -> bool:
    """
    Show confirmation dialog for batch operation.

    Args:
        operation: Operation name like "Delete", "Process"
        item_count: Total number of items
        item_names: Names of items (up to 5 shown)

    Returns:
        True if user confirms, False if cancelled
    """
    # Build item list (show up to 5 items)
    if item_count <= 5:
        items_text = "\n".join([f"  • {name}" for name in item_names])
    else:
        items_text = "\n".join([f"  • {name}" for name in item_names[:5]])
        items_text += f"\n  • ...and {item_count - 5} more"

    message = f"{operation} {item_count} items?\n\n{items_text}"

    # Show confirmation dialog
    result = await self.app.main_window.confirm_dialog(
        title=f"{operation} Items",
        message=message
    )

    return result
```

**1.3 Add Toolbar Delete Button Handler** (MODIFY, find existing delete handler or create new):
```python
async def _on_delete_selected_items(self):
    """Handle delete button click - delete all selected items"""
    try:
        # Get selection from SelectionManager
        selected_item_ids = []
        selected_item_names = []

        if hasattr(self.app, 'selection_manager') and self.app.selection_manager:
            selected_item_ids = self.app.selection_manager.get_selection('collection')
            metadata = self.app.selection_manager.get_selection_metadata('collection')
            selected_item_names = [m.get('item_name', 'Unknown') for m in metadata]

        if not selected_item_ids:
            # No selection - show error
            await self.app.main_window.info_dialog(
                title="No Selection",
                message="Please select one or more items to delete."
            )
            return

        # Single item - use existing fast path
        if len(selected_item_ids) == 1:
            await self._perform_delete_item(
                selected_item_ids[0],
                selected_item_names[0]
            )
        else:
            # Multiple items - use batch path
            await self._perform_delete_items(
                selected_item_ids,
                selected_item_names
            )

    except Exception as e:
        logger.error(f"Failed to delete selected items: {e}")
```

**1.4 Register Delete Command** (MODIFY existing command definition):
Find where collection commands are defined (around line 80-150) and ensure delete command exists:
```python
# In define_commands() method
self.register_command(
    command_id='delete_items',
    title='Delete',
    action=self._on_delete_selected_items,
    icon='trash',
    tooltip='Delete selected items',
    enabled=True,  # Always enabled (will show error if no selection)
    toolbar_location='top'  # Desktop toolbar
)
```

**Test Scenarios**:
- [ ] Select 1 item → Delete → Shows confirmation for 1 item → Deletes
- [ ] Select 3 items → Delete → Shows confirmation with 3 names → Deletes all 3
- [ ] Select 10 items → Delete → Shows "...and 5 more" → Deletes all 10
- [ ] Delete with 1 failure → Shows error summary → Refreshes list
- [ ] Cancel confirmation → No items deleted

---

### Step 2: Collection Process Workflow (1.5 days)

**Goal**: Enable processing multiple selected items together.

**Files to Modify**:
- `src/fichero/windows/main/views/collection/collection_view.py`

**Implementation**:

**2.1 Modify Quick Process to Use SelectionManager** (MODIFY line 2384-2443):
```python
async def _on_quick_process(self, plan_name: str, workflow_name: str):
    """
    Quick process handler for specific tools (Crop, Rotate, Split).
    NOW SUPPORTS MULTI-SELECTION.

    Args:
        plan_name: Name of the plan file (e.g., 'Crop', 'Rotate', 'Split')
        workflow_name: Name of the workflow within the plan
    """
    try:
        if not self.collection_id:
            logger.error("No collection ID available")
            return

        logger.info(f"Quick process: {plan_name}/{workflow_name}")

        # === PHASE 4: Get ALL selected items from SelectionManager ===
        selected_item_ids = []
        selected_item_names = []

        if hasattr(self.app, 'selection_manager') and self.app.selection_manager:
            selected_item_ids = self.app.selection_manager.get_selection('collection')
            metadata = self.app.selection_manager.get_selection_metadata('collection')
            selected_item_names = [m.get('item_name', 'Unknown') for m in metadata]

            if selected_item_ids:
                logger.info(f"Processing {len(selected_item_ids)} selected items with {plan_name}")

        # Get collection
        collection = await self.app.library_manager.get_collection(self.collection_id)
        if not collection:
            logger.error(f"Collection not found: {self.collection_id}")
            return

        # Determine which items to process
        if selected_item_ids:
            # Use selected items
            item_ids = selected_item_ids
        else:
            # No selection - process all items
            logger.info(f"No items selected - will process all items with {plan_name}")
            all_items = await self.app.library_manager.get_collection_items(self.collection_id)
            item_ids = [item.id for item in all_items]

        if not item_ids:
            logger.warning(f"No items to process with {plan_name}")
            return

        # === PHASE 4: Show confirmation for large batches ===
        if len(item_ids) >= 5:
            confirmed = await self._show_batch_confirmation(
                operation=f"Process with {plan_name}",
                item_count=len(item_ids),
                item_names=selected_item_names if selected_item_names else [f"Item {i+1}" for i in range(len(item_ids))]
            )

            if not confirmed:
                logger.info(f"Batch process cancelled by user")
                return

        # === Update status bar ===
        if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
            if hasattr(self.app.main_window_wrapper, 'status_bar'):
                self.app.main_window_wrapper.status_bar.set_status(
                    f"Processing {len(item_ids)} items with {plan_name}..."
                )

        # === Process using Director (already supports multi-item) ===
        if not hasattr(self.app, 'director_integration'):
            logger.error("DirectorIntegrationService not available")
            return

        logger.info(f"Processing {len(item_ids)} items with {plan_name}/{workflow_name}")

        # Call Director to process items
        await self.app.director_integration.process_collection(
            collection_id=self.collection_id,
            plan_name=plan_name,
            workflow_name=workflow_name,
            item_ids=item_ids  # Director already supports lists!
        )

        logger.info(f"✅ Batch process started: {len(item_ids)} items")

    except Exception as e:
        logger.error(f"Failed to start batch process: {e}")
        import traceback
        traceback.print_exc()
```

**2.2 Modify Process Dialog to Support Multi-Selection** (MODIFY line 2517):
```python
async def _on_process_requested(self, widget):
    """Handle process button click - show dialog for plan/workflow selection"""
    try:
        if not self.collection_id:
            logger.error("No collection ID")
            return

        # === PHASE 4: Get ALL selected items from SelectionManager ===
        selected_item_ids = []
        selected_item_names = []

        if hasattr(self.app, 'selection_manager') and self.app.selection_manager:
            selected_item_ids = self.app.selection_manager.get_selection('collection')
            metadata = self.app.selection_manager.get_selection_metadata('collection')
            selected_item_names = [m.get('item_name', 'Unknown') for m in metadata]

            if selected_item_ids:
                logger.info(f"Process dialog: {len(selected_item_ids)} items selected")
        else:
            logger.info("Process dialog: No items selected - will process all")

        # Show processing dialog
        await self._show_process_dialog(
            self.collection_id,
            selected_item_ids=selected_item_ids,      # Changed to plural
            selected_item_names=selected_item_names   # Changed to plural
        )

    except Exception as e:
        logger.error(f"Failed to show process dialog: {e}")
```

**2.3 Update Process Dialog Signature** (MODIFY line 2557):
```python
async def _show_process_dialog(
    self,
    collection_id: str,
    selected_item_ids: Optional[List[str]] = None,      # Changed to list
    selected_item_names: Optional[List[str]] = None     # Changed to list
):
    """
    Show processing options dialog.
    NOW SUPPORTS MULTI-SELECTION.

    Args:
        collection_id: Collection to process
        selected_item_ids: List of selected item IDs (None = process all)
        selected_item_names: List of selected item names (for display)
    """
    try:
        selected_item_ids = selected_item_ids or []
        selected_item_names = selected_item_names or []

        # Build dialog message
        if selected_item_ids:
            if len(selected_item_ids) == 1:
                selection_text = f"Selected: {selected_item_names[0]}"
            else:
                selection_text = f"Selected: {len(selected_item_ids)} items"
        else:
            selection_text = "Processing all items in collection"

        # TODO: Show actual dialog with plan/workflow selection
        # For now, use a simple info dialog
        await self.app.main_window.info_dialog(
            title="Process Items",
            message=f"{selection_text}\n\nSelect processing plan..."
        )

        # Call processing logic (update to pass lists)
        await self._process_via_items(
            collection_id,
            collection=None,  # Will be fetched inside
            all_items=None,   # Will be fetched inside
            selected_item_ids=selected_item_ids,      # Plural
            selected_item_names=selected_item_names   # Plural
        )

    except Exception as e:
        logger.error(f"Failed to show process dialog: {e}")
```

**2.4 Update _process_via_items Signature** (MODIFY line 2591):
```python
async def _process_via_items(
    self,
    collection_id: str,
    collection,
    all_items,
    selected_item_ids: Optional[List[str]] = None,      # Changed to list
    selected_item_names: Optional[List[str]] = None     # Changed to list
):
    """
    Process items via Director integration.
    NOW SUPPORTS MULTI-SELECTION.
    """
    try:
        selected_item_ids = selected_item_ids or []

        # Determine which items to process
        if selected_item_ids:
            item_ids = selected_item_ids
            logger.info(f"Processing {len(item_ids)} selected items")
        else:
            # Process all items
            if not all_items:
                all_items = await self.app.library_manager.get_collection_items(collection_id)
            item_ids = [item.id for item in all_items]
            logger.info(f"Processing all {len(item_ids)} items")

        # Rest of processing logic...
        # (Director already supports item_ids list)

    except Exception as e:
        logger.error(f"Failed to process items: {e}")
```

**Test Scenarios**:
- [ ] Select 1 item → Quick Process (Crop) → Processes 1 item
- [ ] Select 3 items → Quick Process (Crop) → Shows "Process 3 items?" → Processes all 3
- [ ] Select 5+ items → Shows confirmation dialog → User confirms → Processes all
- [ ] Select nothing → Process → Processes all items in collection
- [ ] Select 2 items → Process Dialog → Shows "Selected: 2 items" → Processes 2

---

### Step 3: Library Delete Workflow (1 day)

**Goal**: Enable deleting multiple collections at once.

**Files to Modify**:
- `src/fichero/windows/main/views/library/library_view.py`

**Implementation**:

**3.1 Create Batch Delete Collections Method** (NEW, after line 1404):
```python
async def _perform_delete_collections(
    self,
    collection_ids: List[str],
    collection_names: List[str]
):
    """
    Delete multiple collections with confirmation and error handling.

    Args:
        collection_ids: List of collection IDs to delete
        collection_names: List of collection names (for display)
    """
    try:
        logger.info(f"Batch delete collections: {len(collection_ids)}")

        # Show confirmation dialog
        confirmed = await self._show_batch_confirmation(
            operation="Delete",
            item_count=len(collection_ids),
            item_names=collection_names
        )

        if not confirmed:
            logger.info("Batch delete collections cancelled")
            return

        # Update status bar
        if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
            if hasattr(self.app.main_window_wrapper, 'status_bar'):
                self.app.main_window_wrapper.status_bar.set_status(
                    f"Deleting {len(collection_ids)} collections..."
                )

        # Delete each collection
        successful = []
        failed = []

        for col_id, col_name in zip(collection_ids, collection_names):
            try:
                success = await self.app.library_manager.delete_collection(col_id)
                if success:
                    successful.append(col_name)
                    logger.info(f"✅ Deleted collection: {col_name}")
                else:
                    failed.append((col_name, "Delete returned False"))
                    logger.warning(f"❌ Failed to delete collection: {col_name}")
            except Exception as e:
                failed.append((col_name, str(e)))
                logger.error(f"❌ Exception deleting collection {col_name}: {e}")

        # Report results
        if failed:
            error_text = "\n".join([f"• {name}: {reason}" for name, reason in failed])
            await self.app.main_window.info_dialog(
                title="Deletion Summary",
                message=f"Deleted {len(successful)} of {len(collection_ids)} collections.\n\n"
                        f"Failed:\n{error_text}"
            )
        else:
            logger.info(f"✅ Successfully deleted all {len(successful)} collections")

        # Update status bar
        if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
            if hasattr(self.app.main_window_wrapper, 'status_bar'):
                status_text = f"Deleted {len(successful)} collections"
                if failed:
                    status_text += f", {len(failed)} failed"
                self.app.main_window_wrapper.status_bar.set_status(status_text)

        # Refresh library view
        self._load_collections()

        # Clear selection
        if hasattr(self.app, 'selection_manager') and self.app.selection_manager:
            self.app.selection_manager.clear_selection('library')

    except Exception as e:
        logger.error(f"Failed batch delete collections: {e}")
        import traceback
        traceback.print_exc()
```

**3.2 Add Toolbar Delete Handler** (NEW or MODIFY existing):
```python
async def _on_delete_selected_collections(self):
    """Handle delete button - delete all selected collections"""
    try:
        # Get selection from SelectionManager
        selected_collection_ids = []
        selected_collection_names = []

        if hasattr(self.app, 'selection_manager') and self.app.selection_manager:
            selected_collection_ids = self.app.selection_manager.get_selection('library')
            metadata = self.app.selection_manager.get_selection_metadata('library')
            selected_collection_names = [m.get('collection_name', 'Unknown') for m in metadata]

        if not selected_collection_ids:
            await self.app.main_window.info_dialog(
                title="No Selection",
                message="Please select one or more collections to delete."
            )
            return

        # Single collection - use existing fast path
        if len(selected_collection_ids) == 1:
            await self._perform_delete_collection(
                selected_collection_ids[0],
                selected_collection_names[0]
            )
        else:
            # Multiple collections - use batch path
            await self._perform_delete_collections(
                selected_collection_ids,
                selected_collection_names
            )

    except Exception as e:
        logger.error(f"Failed to delete selected collections: {e}")
```

**Test Scenarios**:
- [ ] Select 1 collection → Delete → Confirmation → Deletes
- [ ] Select 3 collections → Delete → Shows 3 names → Deletes all
- [ ] Delete with failure → Shows error summary

---

### Step 4: Library Export Workflow (0.5 days)

**Goal**: Enable exporting multiple collections to ZIP files.

**Files to Modify**:
- `src/fichero/windows/main/views/library/library_view.py`

**Implementation**:

**4.1 Create Batch Export Method** (NEW, after line 2200):
```python
async def _perform_export_collections(
    self,
    collection_ids: List[str],
    collection_names: List[str]
):
    """
    Export multiple collections to ZIP files.
    Each collection gets its own ZIP file.

    Args:
        collection_ids: List of collection IDs to export
        collection_names: List of collection names
    """
    try:
        logger.info(f"Batch export collections: {len(collection_ids)}")

        # Show folder picker for output directory
        folder_path = await self.app.main_window.select_folder_dialog(
            title=f"Select Export Location for {len(collection_ids)} Collections"
        )

        if not folder_path:
            logger.info("Export cancelled - no folder selected")
            return

        # Update status bar
        if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
            if hasattr(self.app.main_window_wrapper, 'status_bar'):
                self.app.main_window_wrapper.status_bar.set_status(
                    f"Exporting {len(collection_ids)} collections..."
                )

        # Export each collection
        successful = []
        failed = []

        for col_id, col_name in zip(collection_ids, collection_names):
            try:
                # Generate output path
                safe_name = col_name.replace(' ', '_').replace('/', '_')
                output_path = os.path.join(folder_path, f"{safe_name}_export.zip")

                # Export collection
                success = await self._export_single_collection(col_id, col_name, output_path)
                if success:
                    successful.append(col_name)
                    logger.info(f"✅ Exported: {col_name}")
                else:
                    failed.append((col_name, "Export failed"))
                    logger.warning(f"❌ Failed to export: {col_name}")
            except Exception as e:
                failed.append((col_name, str(e)))
                logger.error(f"❌ Exception exporting {col_name}: {e}")

        # Report results
        if failed:
            error_text = "\n".join([f"• {name}: {reason}" for name, reason in failed])
            await self.app.main_window.info_dialog(
                title="Export Summary",
                message=f"Exported {len(successful)} of {len(collection_ids)} collections.\n\n"
                        f"Failed:\n{error_text}"
            )
        else:
            await self.app.main_window.info_dialog(
                title="Export Complete",
                message=f"Successfully exported {len(successful)} collections to:\n{folder_path}"
            )

        # Update status bar
        if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
            if hasattr(self.app.main_window_wrapper, 'status_bar'):
                self.app.main_window_wrapper.status_bar.set_status(
                    f"Exported {len(successful)} collections"
                )

    except Exception as e:
        logger.error(f"Failed batch export: {e}")
```

**Test Scenarios**:
- [ ] Select 2 collections → Export → Pick folder → Creates 2 ZIP files
- [ ] Export with failure → Shows summary

---

### Step 5: Inspector Multi-Selection Support (0.5 days)

**Goal**: Show summary for multiple selected items in inspector.

**Files to Modify**:
- `src/fichero/windows/inspector/inspector_window.py`
- `src/fichero/windows/main/views/collection/collection_view.py` (modify inspector update call)

**Implementation**:

**5.1 Modify CollectionView Inspector Update** (MODIFY line 1815):
```python
# In _on_item_selected(), update inspector section:

# Update inspector with selection
if selected_item_ids:
    if len(selected_item_ids) == 1:
        # Single item - show full metadata (existing behavior)
        first_item_data = self._extract_item_data(selected_items[0])
        if hasattr(self.app, 'inspector_window') and self.app.inspector_window:
            asyncio.create_task(self._update_inspector_async(first_item_data))
    else:
        # Multiple items - show summary
        if hasattr(self.app, 'inspector_window') and self.app.inspector_window:
            # Build summary metadata
            summary = self._build_multi_selection_summary(selected_metadata)
            self.app.inspector_window.update_metadata(summary, selection_type="MULTI_SELECTION")
```

**5.2 Add Summary Builder Method** (NEW in collection_view.py):
```python
def _build_multi_selection_summary(self, metadata_list: List[Dict]) -> Dict:
    """
    Build summary metadata for multiple selected items.

    Args:
        metadata_list: List of item metadata dicts

    Returns:
        Summary dict with aggregated info
    """
    total_items = len(metadata_list)

    # Count by type
    folders = sum(1 for m in metadata_list if m.get('is_folder', False))
    files = total_items - folders

    # Count by file type (for files)
    type_counts = {}
    for m in metadata_list:
        if not m.get('is_folder', False):
            item_type = m.get('type', 'unknown')
            type_counts[item_type] = type_counts.get(item_type, 0) + 1

    # Build summary text
    summary_lines = [
        f"{total_items} items selected",
        f"{folders} folders, {files} files" if folders > 0 else f"{files} files",
    ]

    if type_counts:
        type_summary = ", ".join([f"{count} {type_name}" for type_name, count in type_counts.items()])
        summary_lines.append(f"Types: {type_summary}")

    return {
        'summary': '\n'.join(summary_lines),
        'total_items': total_items,
        'folders': folders,
        'files': files,
        'type_counts': type_counts
    }
```

**5.3 Update Inspector to Show Summary** (MODIFY inspector_window.py):
```python
def update_metadata(self, metadata, selection_type: str = None):
    """Update metadata - now supports MULTI_SELECTION type"""

    if selection_type == "MULTI_SELECTION":
        # Show summary view instead of detailed metadata
        self.current_selection_type = "MULTI_SELECTION"
        self.current_metadata = metadata

        if self.option_container:
            # Show simplified summary tabs
            self._rebuild_summary_tabs(metadata)
    else:
        # Existing single-item logic
        # ...existing code...
```

**Test Scenarios**:
- [ ] Select 1 item → Inspector shows full metadata
- [ ] Select 3 items (2 images, 1 folder) → Inspector shows "3 items selected, 1 folder, 2 files"
- [ ] Select 5 PDFs → Inspector shows "5 items selected, 5 files, Types: 5 pdf"

---

## 5. User Confirmation Dialog Design

### 5.1 Delete Confirmation

**Single Item** (existing behavior):
```
Delete "Document 1.jpg"?

This action cannot be undone.

[Cancel] [Delete]
```

**Multiple Items** (new):
```
Delete 5 items?

  • Document 1.jpg
  • Document 2.jpg
  • Document 3.jpg
  • Folder A
  • Folder B

This action cannot be undone.

[Cancel] [Delete]
```

**Many Items** (show first 5):
```
Delete 25 items?

  • Document 1.jpg
  • Document 2.jpg
  • Document 3.jpg
  • Folder A
  • Folder B
  • ...and 20 more

This action cannot be undone.

[Cancel] [Delete]
```

### 5.2 Process Confirmation

**Small Batch** (< 5 items, no confirmation):
- Process immediately

**Large Batch** (5+ items):
```
Process 12 items with Crop Images?

  • Document 1.jpg
  • Document 2.jpg
  • Document 3.jpg
  • ...and 9 more

This may take several minutes.

[Cancel] [Process]
```

### 5.3 Export Confirmation

**Small Batch** (< 10 collections):
- Export immediately after folder selection

**Large Batch** (10+ collections):
```
Export 15 collections?

Each collection will be exported to a separate ZIP file.
This may take a long time.

[Cancel] [Export]
```

---

## 6. Progress Indication Strategy

### 6.1 Status Bar Updates (Phase 4 - Simple)

**Pattern**:
```python
# Before operation
status_bar.set_status(f"Deleting {count} items...")

# After success
status_bar.set_status(f"Deleted {success_count} items")

# After partial failure
status_bar.set_status(f"Deleted {success_count} items, {failed_count} failed")

# Clear after 5 seconds (optional)
await asyncio.sleep(5)
status_bar.set_status("")
```

**When to Update**:
- Before operation starts
- After operation completes (success or failure)
- No intermediate updates (too complex for Phase 4)

### 6.2 Progress Dialog (Future Phase 5)

**Not Implemented in Phase 4** - Defer to later:
- Modal dialog with progress bar
- "Deleting item 3 of 10..."
- Cancel button
- Real-time updates

**Why Defer**:
- Complex implementation (requires threading or async updates)
- Status bar is sufficient for most operations
- Can add in Phase 5 if users request it

---

## 7. Error Handling Strategy

### 7.1 Partial Failure Handling

**Pattern Used in All Batch Operations**:
```python
successful = []
failed = []

for item_id, item_name in zip(item_ids, item_names):
    try:
        success = await self._delete_item(item_id)
        if success:
            successful.append(item_name)
        else:
            failed.append((item_name, "Operation failed"))
    except Exception as e:
        failed.append((item_name, str(e)))
        logger.error(f"Error: {e}")

# Always continue to next item - don't stop on first failure
```

### 7.2 Error Reporting

**Single Error Dialog** (not N dialogs):
```python
if failed:
    error_text = "\n".join([f"• {name}: {reason}" for name, reason in failed[:10]])
    if len(failed) > 10:
        error_text += f"\n• ...and {len(failed) - 10} more errors"

    await self.app.main_window.info_dialog(
        title=f"{operation} Summary",
        message=f"Completed {len(successful)} of {total} items.\n\n"
                f"Failed items:\n{error_text}\n\n"
                f"Check logs for details."
    )
```

**Logging**:
```python
# Log each failure with full traceback
logger.error(f"Failed to delete {item_name}: {e}")
traceback.print_exc()

# Log summary at end
logger.info(f"Batch operation complete: {len(successful)} succeeded, {len(failed)} failed")
```

### 7.3 Graceful Degradation

**If SelectionManager Not Available**:
```python
if hasattr(self.app, 'selection_manager') and self.app.selection_manager:
    # Use SelectionManager (Phase 4 behavior)
    selected_ids = self.app.selection_manager.get_selection('collection')
else:
    # Fallback to widget selection (Phase 3 behavior)
    logger.warning("SelectionManager not available, using widget selection")
    selection = self.items_list.get_selection()
    # Extract IDs from widget...
```

**If Batch Operation Fails Completely**:
```python
try:
    await self._perform_delete_items(item_ids, item_names)
except Exception as e:
    logger.error(f"Batch delete failed completely: {e}")
    await self.app.main_window.error_dialog(
        title="Operation Failed",
        message=f"Could not complete batch operation.\n\nError: {str(e)}\n\nSee logs for details."
    )
```

---

## 8. Testing Strategy

### 8.1 Manual Test Scenarios

**Collection Delete Tests**:
- [ ] Select 1 item → Delete → Confirms with item name → Item deleted
- [ ] Select 3 items → Delete → Shows 3 names → All deleted
- [ ] Select 10 items → Delete → Shows "...and 5 more" → All deleted
- [ ] Select item, delete fails (permissions) → Shows error → Other items still selectable
- [ ] Cancel delete confirmation → No items deleted
- [ ] Delete with no selection → Shows "No selection" error

**Collection Process Tests**:
- [ ] Select 1 item → Quick Process (Crop) → Processes 1 item
- [ ] Select 3 items → Quick Process (Crop) → Processes all 3
- [ ] Select 5+ items → Shows confirmation → Confirms → Processes all
- [ ] Select nothing → Quick Process → Processes all items
- [ ] Select 2 items → Process Dialog → Shows "Selected: 2 items" → Processes 2
- [ ] Cancel process confirmation → No processing starts

**Library Delete Tests**:
- [ ] Select 1 collection → Delete → Confirms → Collection deleted
- [ ] Select 2 collections → Delete → Shows both names → Both deleted
- [ ] Cancel delete → No collections deleted

**Library Export Tests**:
- [ ] Select 2 collections → Export → Pick folder → Creates 2 ZIP files
- [ ] Export with disk full → Shows error for failed exports

**Inspector Tests**:
- [ ] Select 1 item → Inspector shows full metadata
- [ ] Select 3 items → Inspector shows summary "3 items selected"
- [ ] Select 5 PDFs → Inspector shows "5 items selected, Types: 5 pdf"

### 8.2 Edge Cases

**Empty Selection**:
- [ ] Delete with no selection → Shows error
- [ ] Process with no selection → Processes all items (existing behavior)

**Large Selections**:
- [ ] Select 100 items → Delete → Shows "...and 95 more" → Deletes all
- [ ] Select 1000 items → Process → Shows confirmation → Processes (may take a while)

**Partial Failures**:
- [ ] Delete 5 items, 2 fail (permission denied) → Shows "Deleted 3, 2 failed"
- [ ] Process 5 items, 1 fails → Continues processing remaining items

**Concurrent Operations**:
- [ ] Start delete → While deleting, select new items → New selection tracked correctly
- [ ] Process running → Delete items from same collection → Operations don't conflict

### 8.3 Regression Tests

**Ensure Single-Selection Still Works**:
- [ ] Select 1 item → Inspector shows metadata (not summary)
- [ ] Select 1 item → Delete → Uses fast path (not batch path)
- [ ] Process 1 item → No confirmation shown

**Ensure Existing Features Work**:
- [ ] Status bar updates on selection change (Phase 2)
- [ ] SelectionManager tracks selection (Phase 1)
- [ ] Preview still loads for single item
- [ ] Navigation still works

### 8.4 Unit Test Coverage

**Tests to Create**:

**File**: `tests/unit/test_phase4_batch_operations.py`
```python
# Test batch delete
def test_perform_delete_items_all_succeed()
def test_perform_delete_items_partial_failure()
def test_perform_delete_items_all_fail()

# Test batch process
def test_quick_process_uses_selection_manager()
def test_quick_process_with_multiple_items()
def test_quick_process_with_no_selection()

# Test confirmation dialogs
def test_batch_confirmation_shows_all_items_when_few()
def test_batch_confirmation_truncates_when_many()

# Test multi-selection summary
def test_build_multi_selection_summary_files_only()
def test_build_multi_selection_summary_mixed()
```

**File**: `tests/integration/test_phase4_workflows.py`
```python
# Test full workflows
def test_delete_workflow_end_to_end()
def test_process_workflow_end_to_end()
def test_export_workflow_end_to_end()

# Test error handling
def test_delete_with_permission_error()
def test_process_with_invalid_item()
```

---

## 9. Success Criteria

Phase 4 is complete when:

### 9.1 Functional Requirements
- [ ] User can delete multiple selected items (collection view)
- [ ] User can process multiple selected items (quick process)
- [ ] User can process multiple selected items (process dialog)
- [ ] User can delete multiple collections (library view)
- [ ] User can export multiple collections (library view)
- [ ] Inspector shows summary for multi-selection
- [ ] All workflows show confirmations for batch operations
- [ ] Status bar shows progress messages

### 9.2 User Experience
- [ ] Confirmations show item names (up to 5, then "...and N more")
- [ ] Error summaries show which items failed and why
- [ ] Status bar updates before/after batch operations
- [ ] No blocking UI during long operations
- [ ] Single-item operations still feel fast (don't use batch path)

### 9.3 Error Handling
- [ ] Partial failures handled gracefully (don't stop processing)
- [ ] Error summary shown at end (not N dialogs)
- [ ] Failed items logged with full traceback
- [ ] UI refreshes correctly after partial failure

### 9.4 Backward Compatibility
- [ ] Single-selection workflows still work exactly as before
- [ ] Inspector still shows full metadata for single item
- [ ] Process with no selection still processes all items
- [ ] Swipe actions still work for single items

### 9.5 Code Quality
- [ ] All new methods have docstrings
- [ ] Error handling in all batch operations
- [ ] Logging at appropriate levels
- [ ] No code duplication (use helper methods)

---

## 10. Notes for Next Agent (Implementation Agent)

### 10.1 Key Assumptions

**Assumption 1: Director Supports Multi-Item Processing**
- `director_integration.process_collection()` accepts `item_ids` list
- **Verification**: Check line 2443 in collection_view.py - it's already used
- **Risk**: LOW - Director already built for this

**Assumption 2: Library Service Supports Item Deletion**
- `library_service.delete_collection_item(item_id)` exists and works
- **Verification**: Used at line 1992 in collection_view.py
- **Risk**: LOW - Already in use

**Assumption 3: Toga Dialogs Support Async/Await**
- `await self.app.main_window.confirm_dialog()` works
- `await self.app.main_window.info_dialog()` works
- **Verification**: Check existing dialog usage in codebase
- **Risk**: MEDIUM - May need to use different dialog API

**Assumption 4: SelectionManager Is Always Available**
- `self.app.selection_manager` exists in all views
- **Verification**: Check app.py initialization
- **Risk**: LOW - Graceful fallback implemented

### 10.2 Design Decisions & Rationale

**Decision 1: Use Status Bar (Not Progress Dialog)**
- **Rationale**: Simpler implementation, sufficient for most users
- **Trade-off**: Can't cancel mid-operation, no real-time progress
- **Future**: Add progress dialog in Phase 5 if needed

**Decision 2: Single-Item Fast Path**
- **Rationale**: Keep single-item operations fast and simple
- **Implementation**: `if len(ids) == 1: use existing method else: use batch method`
- **Benefit**: No regression risk for 90% of operations

**Decision 3: Continue on Failure**
- **Rationale**: If deleting 10 items and item 3 fails, still delete items 4-10
- **Alternative**: Stop on first failure (more conservative but less useful)
- **User Preference**: Continuing is more useful

**Decision 4: One Error Dialog (Not N Dialogs)**
- **Rationale**: Showing 10 error dialogs is terrible UX
- **Implementation**: Collect all errors, show summary at end
- **Benefit**: User sees all failures at once

### 10.3 Potential Risks

**Risk 1: Long-Running Operations Block UI**
- **Mitigation**: Use `asyncio.create_task()` for batch operations
- **Fallback**: Show "Processing..." status, accept that UI may be slow
- **Future**: Move to background thread

**Risk 2: Partial State Corruption**
- **Scenario**: Delete 5 items, process fails after item 3 deleted
- **Mitigation**: Each operation is atomic (delete one item at a time)
- **Recovery**: Refresh UI to show current state

**Risk 3: Memory Usage for Large Selections**
- **Scenario**: User selects 10,000 items
- **Mitigation**: SelectionManager stores IDs (strings), not full data
- **Limit**: Don't implement for Phase 4, defer to future optimization

**Risk 4: Toga Dialog API Differs from Assumptions**
- **Scenario**: `confirm_dialog()` doesn't exist or works differently
- **Mitigation**: Check Toga docs, use alternative like `question_dialog()`
- **Fallback**: Skip confirmations, just log warning

### 10.4 Questions for Review Agent

**Question 1: Scope**
- Is MEDIUM scope correct? (delete + process, defer export/move)
- Should we implement export in Phase 4 or defer to Phase 5?

**Question 2: Confirmations**
- Confirm for all deletes, or only 5+ items?
- Should process operations always confirm, or only large batches?

**Question 3: Progress**
- Is status bar sufficient, or should we implement progress dialog now?
- Can progress dialog wait until Phase 5?

**Question 4: Inspector**
- Should multi-selection summary be in Phase 4 or defer to Phase 5?
- Is showing "3 items selected" sufficient, or need more detail?

**Question 5: Testing**
- Should we create unit tests in Phase 4, or defer to separate testing phase?
- How much manual testing is expected?

### 10.5 Implementation Order

**Recommended Order** (most value first):
1. Step 2: Collection Process (HIGH value, partially works already)
2. Step 1: Collection Delete (HIGH value, common operation)
3. Step 5: Inspector Summary (MEDIUM value, nice UX)
4. Step 3: Library Delete (MEDIUM value, less common)
5. Step 4: Library Export (LOW value, can defer)

**Rationale**:
- Process workflow is most-used and partially implemented
- Delete is second most-used and relatively simple
- Inspector improves UX without much work
- Library operations are less common

---

## 11. Scope Recommendation

### 11.1 Recommended Scope: MEDIUM

**Include in Phase 4**:
- ✅ Collection Delete (Step 1)
- ✅ Collection Process - Quick Process (Step 2.1)
- ✅ Collection Process - Dialog Process (Step 2.2-2.4)
- ✅ Inspector Summary (Step 5)
- ⚠️ Library Delete (Step 3) - Optional

**Defer to Phase 5**:
- ❌ Library Export (Step 4) - Low value
- ❌ Progress Dialog - Complex
- ❌ Move/Copy Operations - Not yet implemented
- ❌ Batch Rename - Not critical

**Justification**:
- Phase 4 focuses on **critical workflows** (delete, process)
- These are the most-used batch operations
- Export is slow and less common
- Move/copy aren't implemented yet
- Keeps phase manageable (3-4 days work)

### 11.2 Minimal Scope Alternative

**If time is limited, implement only**:
- ✅ Collection Delete (Step 1)
- ✅ Collection Process Quick (Step 2.1)

**Defer everything else to Phase 5**:
- Process Dialog (can use quick process instead)
- Library operations (less common)
- Inspector summary (nice-to-have)

**Justification**:
- Covers 80% of batch operation use cases
- Quick win, low risk
- Can release sooner

### 11.3 Full Scope Alternative

**If comprehensive implementation desired**:
- ✅ All Steps 1-5 above
- ✅ Library Export (Step 4)
- ✅ Progress Dialog with Cancel
- ✅ Batch Rename
- ✅ Move/Copy Operations

**Estimated Time**: 7-10 days
**Risk**: HIGH - too large for one phase
**Recommendation**: Split into Phase 4a and 4b

---

## Summary

Phase 4 Implementation Plan provides:
- ✅ Complete workflow analysis (9 workflows identified)
- ✅ Current implementation analysis (code locations, parameters)
- ✅ Integration strategy (SelectionManager usage pattern)
- ✅ Detailed implementation steps (5 major steps)
- ✅ User confirmation dialogs (designs provided)
- ✅ Progress indication strategy (status bar)
- ✅ Error handling strategy (partial failures)
- ✅ Testing strategy (manual + unit tests)
- ✅ Success criteria (25 checkboxes)
- ✅ Notes for next agent (assumptions, risks, questions)
- ✅ Scope recommendation (MEDIUM)

**Ready for Implementation**: YES

**Estimated Time**: 3-4 days for MEDIUM scope

**Confidence**: HIGH - Foundation (Phases 1-3) is solid and tested
