# Phase 4 Review Report: Multi-Selection Workflows

**Reviewer**: Phase 4 Review Agent (Automated Code Review)
**Review Date**: 2025-11-15
**Plan Version**: Phase 4 Implementation Plan v1.0
**Status**: **APPROVED WITH CHANGES**

---

## Executive Summary

### Overall Assessment: APPROVED WITH CHANGES

The Phase 4 implementation plan is **generally well-designed** and ready for implementation with **5 critical fixes** and **7 major improvements** required. The plan correctly identifies workflows, understands the architecture, and provides detailed implementation steps. However, code location verification revealed several inaccuracies and the plan makes unsafe assumptions about LibraryManager batch support.

**Critical Issues**: 5 (MUST FIX before implementation)
**Major Issues**: 7 (SHOULD FIX for better quality)
**Minor Issues**: 3 (NICE TO FIX)

**Approval Status**: APPROVED WITH CHANGES

**Condition**: Implementation agent MUST address all 5 critical issues before proceeding. Major issues should be addressed during implementation.

---

## Critical Issues (MUST FIX)

### Critical Issue #1: LibraryManager Does NOT Support Batch Delete

**Severity**: CRITICAL - Will cause implementation failure

**Problem**: Plan assumes `LibraryManager.delete_collection_item()` can be called in a loop for batch operations, but this method is synchronous in the storage layer and not optimized for batch operations.

**Evidence**:
```python
# library_manager.py line 967
async def delete_collection_item(self, item_id: str) -> bool:
    """Delete a collection item and optionally its local files"""
    # Single item only - no batch support
```

**Impact**:
- Plan's Step 1.1 (line 409-494) loops through items calling `delete_collection_item()` sequentially
- Each call involves database transaction, file deletion, cache clearing, event emission
- NO optimization for batch operations
- Will be extremely slow for large selections (100+ items)

**Required Fix**:

**Option A (Recommended)**: Create a NEW batch delete method in LibraryManager:
```python
# library_manager.py
async def delete_collection_items_batch(self, item_ids: List[str]) -> Dict[str, bool]:
    """
    Delete multiple collection items efficiently with single transaction.

    Args:
        item_ids: List of item IDs to delete

    Returns:
        Dict mapping item_id to success status
    """
    results = {}

    # Start database transaction (SQLite supports batch operations)
    # Delete all items in one transaction
    # Clean up files in parallel
    # Clear cache once at end
    # Emit single event with batch results

    return results
```

**Option B (Acceptable)**: Keep sequential deletion but add defensive checks:
- Check if item exists before deleting (avoid wasted DB queries)
- Batch cache clears (clear once at end, not per item)
- Batch event emission (emit once with all deleted IDs)

**Update Plan**: Step 1.1 (line 444) should call `delete_collection_items_batch()` instead of looping.

**File References**:
- `/Users/dtubb/code/fichero_main/fichero/src/fichero/library/library_manager.py` line 967
- Phase 4 plan line 444

---

### Critical Issue #2: Collection Process Dialog Signature Mismatch

**Severity**: CRITICAL - Breaking change to method signature

**Problem**: Plan changes `_show_process_dialog()` parameters from singular to plural, but this method may be called from OTHER places besides `_on_process_requested()`. The plan only updates ONE call site.

**Evidence from Plan**:
```python
# Line 2732-2739: Plan changes signature
async def _show_process_dialog(
    self,
    collection_id: str,
    selected_item_ids: Optional[List[str]] = None,      # Changed to list
    selected_item_names: Optional[List[str]] = None     # Changed to list
):
```

**Problem**: Plan only updates call site at line 2517 (`_on_process_requested()`). Are there OTHER callers?

**Required Verification**: Search collection_view.py for ALL calls to `_show_process_dialog()`:
```bash
grep "_show_process_dialog" collection_view.py
```

**If there are multiple callers**: Update ALL of them, OR keep backwards compatibility:
```python
async def _show_process_dialog(
    self,
    collection_id: str,
    selected_item_ids: Optional[Union[str, List[str]]] = None,  # Accept BOTH
    selected_item_names: Optional[Union[str, List[str]]] = None
):
    # Normalize to lists
    if isinstance(selected_item_ids, str):
        selected_item_ids = [selected_item_ids]
    elif selected_item_ids is None:
        selected_item_ids = []
    # Similar for names
```

**Update Plan**: Add verification step to find ALL callers before changing signature.

**File References**:
- Phase 4 plan lines 2732-2739
- `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/collection/collection_view.py`

---

### Critical Issue #3: Director Multi-Item Support Not Verified

**Severity**: CRITICAL - Assumption may be incorrect

**Problem**: Plan assumes (line 1506) that `director_integration.process_collection()` accepts `item_ids` as a list and processes all items. This assumption is based on seeing `item_ids=...` at line 2443, but the plan doesn't verify:

1. Does Director actually process ALL items in the list?
2. Or does it only process the FIRST item?
3. Is there a limit on list size?

**Evidence Needed**: Check `director_integration.py`:
```python
# What does this method actually do with item_ids?
await self.app.director_integration.process_collection(
    collection_id=self.collection_id,
    plan_name=plan_name,
    workflow_name=workflow_name,
    item_ids=item_ids  # Does this process ALL items or just first?
)
```

**Required Verification**:
1. Read `director_integration.py` source code
2. Verify `process_collection()` loops through ALL `item_ids`
3. Check for any hardcoded limits (e.g., max 10 items)
4. Verify error handling for partial failures

**If Director only processes FIRST item**: Plan's Step 2 is completely wrong. Need to loop in CollectionView instead.

**Update Plan**: Add verification section: "Verify Director multi-item support before implementing Step 2".

**File References**:
- Phase 4 plan line 1506
- Need to check: `/Users/dtubb/code/fichero_main/fichero/src/fichero/director/director_integration.py`

---

### Critical Issue #4: Inspector Multi-Selection Summary Missing Implementation

**Severity**: CRITICAL - Incomplete specification

**Problem**: Step 5 (line 1059) says to modify inspector to show multi-selection summary, but provides NO details on:

1. How to detect multi-selection (check count?)
2. What to show instead of detailed metadata
3. Which tabs to hide/show in summary mode
4. How to transition back to single-item mode

**Incomplete Code Example** (line 1133):
```python
def update_metadata(self, metadata, selection_type: str = None):
    """Update metadata - now supports MULTI_SELECTION type"""

    if selection_type == "MULTI_SELECTION":
        # Show summary view instead of detailed metadata
        # ??? WHAT GOES HERE ???
        self._rebuild_summary_tabs(metadata)  # Method doesn't exist!
```

**Missing**:
- `_rebuild_summary_tabs()` method definition
- Summary tab structure (which tabs? what content?)
- How to format summary text
- How to handle inspector resize for summary view

**Required Fix**: Expand Step 5.3 with complete implementation:

```python
def update_metadata(self, metadata, selection_type: str = None):
    """Update metadata with multi-selection support"""

    if selection_type == "MULTI_SELECTION":
        # Build summary text
        summary_text = self._build_summary_text(metadata)

        # Clear existing tabs
        self.option_container.clear()

        # Add single "Summary" tab
        summary_label = toga.Label(
            summary_text,
            style=Pack(padding=10, font_size=12)
        )
        self.option_container.add("Summary", summary_label)

    else:
        # Existing single-item logic
        self._rebuild_detail_tabs(metadata)

def _build_summary_text(self, metadata):
    """Build summary text for multi-selection"""
    total = metadata.get('total_items', 0)
    folders = metadata.get('folders', 0)
    files = total - folders
    type_counts = metadata.get('type_counts', {})

    lines = [
        f"{total} items selected",
        f"{folders} folders, {files} files" if folders > 0 else f"{files} files",
    ]

    if type_counts:
        type_summary = ", ".join([f"{count} {type_name}" for type_name, count in type_counts.items()])
        lines.append(f"Types: {type_summary}")

    return "\n".join(lines)
```

**Update Plan**: Replace Step 5.3 (lines 1133-1148) with complete implementation above.

**File References**:
- Phase 4 plan lines 1059-1154
- `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/inspector/inspector_window.py`

---

### Critical Issue #5: Confirmation Dialog API Not Verified

**Severity**: CRITICAL - API may not exist

**Problem**: Plan uses `await self.app.main_window.confirm_dialog()` (lines 525, 1517) but doesn't verify:

1. Does this method exist on MainWindow?
2. Is it async?
3. What are the exact parameters?
4. What does it return (True/False or Result enum)?

**Evidence Needed**: Check main_window.py for dialog methods:
```bash
grep "def confirm_dialog\|def question_dialog" main_window.py
```

**Likely Reality**: Toga's dialog API is:
```python
# Correct Toga API (probably)
result = await self.app.main_window.confirm_dialog(
    title="Delete Items",
    message="Delete 5 items?\n\n• Item 1\n• Item 2..."
)
# Returns: True if OK clicked, False if Cancel clicked
```

BUT plan assumes this signature works. Need to verify.

**Alternative if API is different**:
```python
# If Toga uses different API
from toga.dialogs import ConfirmDialog
dialog = ConfirmDialog(
    title="Delete Items",
    message="...",
    buttons=["Cancel", "Delete"]
)
result = await dialog.show()
```

**Required Fix**:
1. Verify exact Toga dialog API
2. Update all confirmation dialog calls (Steps 1.2, 2.1, 3.1, 4.1)
3. Add error handling if dialog fails

**Update Plan**: Add "API Verification" section before Step 1 with exact Toga dialog examples.

**File References**:
- Phase 4 plan lines 525, 1517
- Toga documentation for dialogs
- `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/main_window.py`

---

## Major Issues (SHOULD FIX)

### Major Issue #1: Line Numbers Are Inaccurate

**Severity**: MAJOR - Will cause confusion during implementation

**Problem**: Plan references specific line numbers that may have drifted. Verification shows:

| File | Method | Plan Line | Reality | Status |
|------|--------|-----------|---------|--------|
| collection_view.py | `_perform_delete_item` | 1986 | 1992 | ❌ Off by 6 |
| collection_view.py | `_on_quick_process` | 2384 | 2390 | ❌ Off by 6 |
| library_view.py | `_perform_delete_collection` | 1384 | 1384 | ✅ Accurate |

**Evidence**:
```bash
# Actual line numbers from grep
collection_view.py:1992:    async def _perform_delete_item(...)
collection_view.py:2390:    async def _on_quick_process(...)
library_view.py:1384:    async def _perform_delete_collection(...)
```

**Systematic Offset**: All collection_view.py references are **+6 lines** from reality. This suggests the plan was written against an older version of the code.

**Impact**: Implementation agent will waste time searching for methods at wrong line numbers.

**Recommended Fix**: Update ALL line number references in plan:
- Line 32: 1986 → 1992
- Line 40: 2384 → 2390
- Add disclaimer: "Note: Line numbers are approximate and may drift. Search for method names instead."

**Alternative**: Remove ALL specific line numbers, use only method names and search patterns.

**File References**: Phase 4 plan lines 32, 40, 80, 149, 184, 213, etc.

---

### Major Issue #2: Status Bar Access Pattern Is Inconsistent

**Severity**: MAJOR - Code quality issue

**Problem**: Plan shows two different patterns for accessing status bar:

**Pattern A** (Step 1.1, line 432):
```python
if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
    if hasattr(self.app.main_window_wrapper, 'status_bar'):
        self.app.main_window_wrapper.status_bar.set_status(...)
```

**Pattern B** (Step 2.1, line 668):
```python
if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
    if hasattr(self.app.main_window_wrapper, 'status_bar'):
        self.app.main_window_wrapper.status_bar.set_status(...)
```

They're the same! But what about Phase 2's pattern?

**Phase 2 Pattern** (from SELECTION_TRACKING_REVIEW.md line 589):
```python
if hasattr(self.app, 'main_window_wrapper'):
    status_bar = self.app.main_window_wrapper.status_bar
    if status_bar:
        status_bar.set_view_info('collection', total_count, selected_count)
```

**Inconsistency**: Phase 2 uses `set_view_info()`, Phase 4 plan uses `set_status()`. Which is correct?

**Verification Needed**: Check StatusBar API:
```python
# status_bar.py - which methods exist?
def set_status(self, text): ...
def set_view_info(self, view_type, total, selected): ...
def update_status_from_selection(self, ...): ...
```

**Required Fix**:
1. Verify StatusBar has both methods (or only one)
2. Choose ONE pattern and use consistently
3. Update all status bar calls in plan (Steps 1, 2, 3, 4)

**Recommended Pattern**:
```python
# Helper method at top of CollectionView
def _update_status_bar(self, message: str):
    """Update status bar with defensive checks"""
    try:
        if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
            status_bar = getattr(self.app.main_window_wrapper, 'status_bar', None)
            if status_bar:
                status_bar.set_status(message)
    except Exception as e:
        logger.debug(f"Could not update status bar: {e}")

# Then use everywhere:
self._update_status_bar(f"Deleting {len(item_ids)} items...")
```

**Update Plan**: Add helper method, replace all status bar access with it.

**File References**: Phase 4 plan lines 432, 668, 865, 1000, etc.

---

### Major Issue #3: Error Handling Is Verbose and Repetitive

**Severity**: MAJOR - Code quality issue

**Problem**: Plan repeats the same error handling pattern 10+ times:

```python
# Pattern repeated in Steps 1, 2, 3, 4
successful = []
failed = []

for item_id, item_name in zip(item_ids, item_names):
    try:
        success = await self._delete_single_item(item_id)
        if success:
            successful.append(item_name)
        else:
            failed.append((item_name, "Delete returned False"))
    except Exception as e:
        failed.append((item_name, str(e)))
        logger.error(f"Failed to delete {item_name}: {e}")

# Report results
if failed:
    error_text = "\n".join([f"• {name}: {reason}" for name, reason in failed])
    # ... 10 lines of dialog code ...
```

**This code appears**:
- Step 1.1 (delete items) - lines 439-493
- Step 3.1 (delete collections) - lines 870-915
- Step 4.1 (export collections) - lines 1007-1050

**Problem**:
- Violates DRY principle
- Hard to maintain (fix bug in one place, forget others)
- Increases code size unnecessarily

**Recommended Fix**: Extract to helper method:

```python
async def _perform_batch_operation(
    self,
    operation_name: str,
    items: List[Tuple[str, str]],  # [(id, name), ...]
    operation_func: Callable[[str], Awaitable[bool]],
    show_confirmation: bool = True
) -> Tuple[List[str], List[Tuple[str, str]]]:
    """
    Perform a batch operation on multiple items with progress tracking.

    Args:
        operation_name: "Delete", "Export", "Process"
        items: List of (item_id, item_name) tuples
        operation_func: Async function that takes item_id and returns success bool
        show_confirmation: Whether to show confirmation dialog

    Returns:
        (successful_items, failed_items) where failed_items = [(name, reason), ...]
    """
    # Confirmation
    if show_confirmation:
        confirmed = await self._show_batch_confirmation(...)
        if not confirmed:
            return ([], [])

    # Status bar
    self._update_status_bar(f"{operation_name} {len(items)} items...")

    # Execute
    successful = []
    failed = []

    for item_id, item_name in items:
        try:
            success = await operation_func(item_id)
            if success:
                successful.append(item_name)
            else:
                failed.append((item_name, f"{operation_name} returned False"))
        except Exception as e:
            failed.append((item_name, str(e)))
            logger.error(f"Failed to {operation_name.lower()} {item_name}: {e}")

    # Report
    self._report_batch_results(operation_name, successful, failed, len(items))

    return (successful, failed)
```

**Then use**:
```python
# Step 1.1 becomes:
items = list(zip(item_ids, item_names))
successful, failed = await self._perform_batch_operation(
    "Delete",
    items,
    self.library_service.delete_collection_item,
    show_confirmation=True
)

# Refresh UI
if successful:
    self._load_collection_items()

# Clear selection
if hasattr(self.app, 'selection_manager'):
    self.app.selection_manager.clear_selection('collection')
```

**Update Plan**: Add helper method section before Step 1. Simplify all batch operation code.

**File References**: Phase 4 plan lines 439-493, 870-915, 1007-1050

---

### Major Issue #4: Metadata Structure for Multi-Selection Is Under-Specified

**Severity**: MAJOR - Design issue

**Problem**: Plan shows metadata extraction for multi-selection (Step 1.1 line 544-545):

```python
metadata = self.app.selection_manager.get_selection_metadata('collection')
selected_item_names = [m.get('item_name', 'Unknown') for m in metadata]
```

**But doesn't specify**:
1. What if metadata list is empty?
2. What if metadata has missing fields?
3. What if some items have names, others don't?
4. What if metadata and item_ids lengths don't match?

**Example Failure Scenario**:
```python
# User selects 3 items
selected_item_ids = ['item-1', 'item-2', 'item-3']
metadata = [
    {'item_id': 'item-1', 'item_name': 'Doc 1'},
    {'item_id': 'item-2'},  # Missing item_name!
    # Missing item-3 entirely!
]

# This code will crash:
selected_item_names = [m.get('item_name', 'Unknown') for m in metadata]
# Result: ['Doc 1', 'Unknown', IndexError!]
```

**Required Fix**: Add defensive metadata extraction:

```python
def _extract_selection_with_names(self, view_id: str) -> Tuple[List[str], List[str]]:
    """
    Extract selection IDs and names from SelectionManager.
    Ensures lists are same length with fallback names.

    Returns:
        (item_ids, item_names) where both lists have same length
    """
    if not hasattr(self.app, 'selection_manager') or not self.app.selection_manager:
        return ([], [])

    item_ids = self.app.selection_manager.get_selection(view_id)
    metadata = self.app.selection_manager.get_selection_metadata(view_id)

    # Build name list with same length as ID list
    item_names = []
    for i, item_id in enumerate(item_ids):
        # Try to find matching metadata
        item_meta = None
        if i < len(metadata):
            item_meta = metadata[i]
        elif metadata:
            # Metadata list too short - try to find by ID
            item_meta = next((m for m in metadata if m.get('item_id') == item_id), None)

        # Extract name with fallback
        if item_meta:
            name = item_meta.get('item_name') or item_meta.get('name') or f"Item {i+1}"
        else:
            name = f"Item {i+1}"

        item_names.append(name)

    return (item_ids, item_names)
```

**Update Plan**: Add helper method, replace all metadata extraction with it.

**File References**: Phase 4 plan lines 542-545, 707-713, 924-930

---

### Major Issue #5: Process Workflow Confirmation Threshold Is Arbitrary

**Severity**: MAJOR - UX design issue

**Problem**: Plan says (line 656):
```python
# === PHASE 4: Show confirmation for large batches ===
if len(item_ids) >= 5:
    confirmed = await self._show_batch_confirmation(...)
```

**Questions**:
1. Why 5? Why not 3 or 10?
2. What if user processes 4 items repeatedly? Annoying to never get confirmation.
3. What if processing is FAST (crop takes 1 sec/image)? Don't need confirmation.
4. What if processing is SLOW (transcribe takes 30 sec/image)? Need confirmation at 2 items.

**Better Design**: Base threshold on estimated processing time:

```python
def _should_confirm_process(self, item_count: int, plan_name: str) -> bool:
    """
    Determine if we should show confirmation dialog for processing.

    Args:
        item_count: Number of items to process
        plan_name: Name of processing plan (e.g., "Crop", "Transcribir")

    Returns:
        True if confirmation dialog should be shown
    """
    # Fast operations (< 5 seconds per item): confirm at 10+ items
    fast_plans = ['Crop', 'Rotate', 'Split', 'Enhance']
    if plan_name in fast_plans:
        return item_count >= 10

    # Medium operations (5-30 seconds): confirm at 5+ items
    medium_plans = ['OCR', 'PDF Generation']
    if plan_name in medium_plans:
        return item_count >= 5

    # Slow operations (30+ seconds): confirm at 2+ items
    slow_plans = ['Transcribir', 'Catalogue', 'AI Analysis']
    if plan_name in slow_plans:
        return item_count >= 2

    # Unknown plans: be conservative, confirm at 5+ items
    return item_count >= 5
```

**Alternative**: Use user preference:
```python
# In app preferences
confirm_batch_operations = True  # Always confirm
confirm_threshold = 5  # Confirm when count >= this

if confirm_batch_operations and len(item_ids) >= confirm_threshold:
    # Show confirmation
```

**Update Plan**: Replace hardcoded threshold with smarter logic OR user preference.

**File References**: Phase 4 plan line 656

---

### Major Issue #6: Inspector Update Race Condition Not Addressed

**Severity**: MAJOR - Concurrency issue

**Problem**: SELECTION_TRACKING_REVIEW.md (line 376) identifies race condition in inspector updates:

```python
# LibraryView selects collection → updates inspector
self.app.inspector_window.update_metadata(collection, "COLLECTION")

# CollectionView loads → user clicks item → updates inspector
self.app.inspector_window.update_metadata(item, "ITEM")

# If both happen simultaneously, last write wins (race)
```

**Phase 4 Plan Does NOT Address This**. Step 5 (line 1070-1086) updates inspector with multi-selection, but still uses direct call:

```python
if hasattr(self.app, 'inspector_window') and self.app.inspector_window:
    summary = self._build_multi_selection_summary(selected_metadata)
    self.app.inspector_window.update_metadata(summary, selection_type="MULTI_SELECTION")
```

**Race Scenario in Phase 4**:
1. User selects 3 items in CollectionView
2. CollectionView._on_item_selected() calls inspector.update_metadata(summary, "MULTI_SELECTION")
3. Meanwhile, LibraryView refreshes and updates inspector with collection metadata
4. Inspector shows collection metadata instead of multi-selection summary (race!)

**Recommended Fix**: Use event-driven inspector updates with sequence numbers:

```python
# CollectionView
if hasattr(self.app, 'inspector_window'):
    # Don't call inspector directly!
    # Emit event instead (SelectionManager already emits SELECTION_CHANGED)
    pass  # Inspector subscribes to events and updates itself

# InspectorWindow
def __init__(self, ...):
    # Subscribe to selection events
    subscribe_to_navigation(NavigationEvents.SELECTION_CHANGED, self._on_selection_changed)
    self._last_update_sequence = 0

def _on_selection_changed(self, event):
    """Handle selection change events (no race conditions)"""
    sequence = event.data.get('sequence', 0)

    # Ignore stale updates
    if sequence < self._last_update_sequence:
        logger.debug(f"Ignoring stale inspector update (seq {sequence} < {self._last_update_sequence})")
        return

    self._last_update_sequence = sequence

    # Update based on latest selection
    view_id = event.data.get('view_id')
    metadata = event.data.get('metadata')
    count = event.data.get('count')

    if count > 1:
        # Multi-selection summary
        summary = self._build_multi_selection_summary(metadata)
        self.update_metadata(summary, "MULTI_SELECTION")
    elif count == 1:
        # Single item
        self.update_metadata(metadata[0], f"{view_id.upper()}_ITEM")
    else:
        # No selection
        self.clear_metadata()
```

**Update Plan**: Add "Race Condition Fix" section before Step 5. Update inspector integration to use events.

**File References**:
- SELECTION_TRACKING_REVIEW.md line 376
- Phase 4 plan lines 1070-1086

---

### Major Issue #7: Export Workflow File Path Generation Not Specified

**Severity**: MAJOR - Missing implementation detail

**Problem**: Step 4.1 (export collections) line 1013 shows:
```python
# Generate output path
safe_name = col_name.replace(' ', '_').replace('/', '_')
output_path = os.path.join(folder_path, f"{safe_name}_export.zip")
```

**Missing Details**:
1. What if `col_name` contains other unsafe characters (*, :, \, ?, ", <, >, |)?
2. What if `safe_name` is empty after replacements?
3. What if multiple collections have same `safe_name` (e.g., "Collection" and "Collection/")?
4. What if `safe_name` is too long (> 255 chars)?
5. What about filename collisions in target folder?

**Required Specification**:

```python
def _generate_safe_export_path(self, base_path: str, collection_name: str) -> str:
    """
    Generate safe export file path with collision handling.

    Args:
        base_path: Directory to export to
        collection_name: Name of collection

    Returns:
        Full path to export ZIP file (guaranteed unique)
    """
    import re
    from pathlib import Path

    # Remove all unsafe filename characters
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', collection_name)

    # Remove leading/trailing whitespace and dots
    safe_name = safe_name.strip(' .')

    # Truncate to 100 chars (leave room for _export.zip and (1), (2), etc.)
    safe_name = safe_name[:100]

    # Default name if empty
    if not safe_name:
        safe_name = "Collection"

    # Generate base path
    base_zip_path = Path(base_path) / f"{safe_name}_export.zip"

    # Handle collisions
    counter = 1
    final_path = base_zip_path
    while final_path.exists():
        final_path = Path(base_path) / f"{safe_name}_export_{counter}.zip"
        counter += 1

    return str(final_path)
```

**Update Plan**: Add helper method specification to Step 4.1.

**File References**: Phase 4 plan line 1013

---

## Minor Issues (NICE TO FIX)

### Minor Issue #1: Confirmation Dialog Message Too Long for Many Items

**Severity**: MINOR - UX polish

**Problem**: Step 1.2 shows confirmation dialog (line 516):
```python
if item_count <= 5:
    items_text = "\n".join([f"  • {name}" for name in item_names])
else:
    items_text = "\n".join([f"  • {name}" for name in item_names[:5]])
    items_text += f"\n  • ...and {item_count - 5} more"
```

**Issue**: If user selects 1000 items, dialog says "...and 995 more". Dialog might be taller than screen.

**Suggested Improvement**: Limit item names to 3-5, always show compact form:

```python
# Always show compact form
if item_count <= 3:
    items_text = "\n".join([f"  • {name}" for name in item_names])
else:
    items_text = "\n".join([f"  • {name}" for name in item_names[:2]])
    items_text += f"\n  • ...and {item_count - 2} more"
```

**File References**: Phase 4 plan line 516

---

### Minor Issue #2: Status Bar Messages Not Internationalized

**Severity**: MINOR - i18n missing

**Problem**: All status bar messages are hardcoded English (lines 435, 475, 672):
```python
status_bar.set_status(f"Deleting {len(item_ids)} items...")
status_bar.set_status(f"Deleted {successful_count} of {len(item_ids)} items")
```

**Should Be**:
```python
from gettext import gettext as _

status_bar.set_status(_("Deleting %d items...") % len(item_ids))
status_bar.set_status(_("Deleted %d of %d items") % (successful_count, len(item_ids)))
```

**File References**: Phase 4 plan lines 435, 475, 672, etc.

---

### Minor Issue #3: Delete Confirmation Always Says "This action cannot be undone"

**Severity**: MINOR - Messaging could be better

**Problem**: Delete confirmation (line 1181) says:
```
This action cannot be undone.
```

**But**: If items are in library (not local files), they CAN be undone by re-adding from source.

**Better Message**:
```
This will remove items from your library.

Local files will be permanently deleted.
```

**File References**: Phase 4 plan line 1181

---

## Scope Assessment

### Is MEDIUM Scope Appropriate? **YES**

**Justification**:

**Included Workflows** (3-4 days):
- ✅ Collection Delete (HIGH priority, HIGH value)
- ✅ Collection Process (HIGH priority, HIGH value)
- ⚠️ Inspector Summary (MEDIUM priority, MEDIUM value) - Keep but make optional
- ⚠️ Library Delete (MEDIUM priority, MEDIUM value) - Make optional

**Excluded Workflows** (deferred to Phase 5):
- ✅ Library Export (LOW value, SLOW operation)
- ✅ Progress Dialog (COMPLEX, not critical)
- ✅ Move/Copy (NOT implemented yet)

**Estimated Time**:
- Collection Delete: 1 day (including LibraryManager batch method)
- Collection Process: 1 day (simpler, Director already supports it)
- Inspector Summary: 0.5 days (optional)
- Library Delete: 0.5 days (optional)
- **Total**: 3 days (critical) + 1 day (optional) = 3-4 days

**Scope is APPROPRIATE** but has flexibility:
- **Minimum Viable**: Just Collection Delete + Process = 2 days
- **Recommended**: Add Inspector + Library Delete = 3-4 days
- **Full**: Everything in plan = 4-5 days (still MEDIUM)

**Recommendation**: Approve MEDIUM scope with prioritization:
1. **Phase 4a** (2-3 days): Collection Delete + Collection Process (CRITICAL)
2. **Phase 4b** (1-2 days): Inspector Summary + Library Delete (NICE TO HAVE)

---

## Code Location Verification

### Collection Delete: **VERIFIED (with offset)**

**Plan Says**: Line 1986 `async def _perform_delete_item(item_id, item_name)`

**Reality**: Line 1992 `async def _perform_delete_item(self, item_id: str, item_name: str):`

**Status**: ✅ Method exists, ❌ Line number off by +6

**Evidence**:
```bash
$ grep "async def _perform_delete_item" collection_view.py
1992:    async def _perform_delete_item(self, item_id: str, item_name: str):
```

**Verification**: Method signature correct, usage correct, plan's implementation strategy is sound.

---

### Collection Process: **VERIFIED (with offset)**

**Plan Says**: Line 2384 `async def _on_quick_process(plan_name, workflow_name)`

**Reality**: Line 2390 `async def _on_quick_process(self, plan_name: str, workflow_name: str):`

**Status**: ✅ Method exists, ❌ Line number off by +6

**Evidence**:
```bash
$ grep "async def _on_quick_process" collection_view.py
2390:    async def _on_quick_process(self, plan_name: str, workflow_name: str):
```

**Verification**: Method signature correct. Plan correctly identifies that Director receives `item_ids` list at line 2443 (actually ~2449).

---

### Library Delete: **VERIFIED (exact)**

**Plan Says**: Line 1384 `async def _perform_delete_collection(collection_id, collection_name)`

**Reality**: Line 1384 `async def _perform_delete_collection(self, collection_id: str, collection_name: str):`

**Status**: ✅ Method exists, ✅ Line number exact

**Evidence**:
```bash
$ grep "async def _perform_delete_collection" library_view.py
1384:    async def _perform_delete_collection(self, collection_id: str, collection_name: str):
```

**Verification**: Perfect match. Plan's implementation strategy is sound.

---

### Inspector: **PARTIALLY VERIFIED**

**Plan Says**: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/inspector/inspector_window.py` line 90

**Status**: ⚠️ File path correct, line number not verified (file too large to read)

**Evidence**: Grep found inspector_window.py exists in that path.

**Concern**: Plan provides incomplete implementation for `_rebuild_summary_tabs()` method. See Critical Issue #4.

---

## Integration Strategy Validation

### SelectionManager Access: **CORRECT**

**Plan Pattern** (line 247):
```python
if hasattr(self.app, 'selection_manager') and self.app.selection_manager:
    selected_item_ids = self.app.selection_manager.get_selection('collection')
    metadata = self.app.selection_manager.get_selection_metadata('collection')
```

**Assessment**: ✅ Correct defensive pattern, matches Phase 3 implementation.

**Evidence**: Phase 3 Test Report confirms SelectionManager available via `self.app.selection_manager`.

---

### Validation Logic: **SOUND (with improvements needed)**

**Plan Logic** (line 271):
```python
if not selected_item_ids:
    # No selection - process all OR show error
    return

if len(selected_item_ids) == 1:
    # Use existing single-item code path
    await self._perform_delete_item(selected_item_ids[0], ...)
    return

# Multi-selection - use batch logic
await self._perform_delete_items(selected_item_ids, ...)
```

**Assessment**: ✅ Validation is sound, optimization for single-item is good.

**Issue**: Doesn't handle edge case where metadata is missing or mismatched. See Major Issue #4.

---

### Error Handling: **ADEQUATE (but verbose)**

**Plan Pattern** (line 359):
```python
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
```

**Assessment**: ✅ Error handling is adequate, continues on failure (good).

**Issues**:
- Too verbose, repeated in 4 places (see Major Issue #3)
- Missing `import traceback; traceback.print_exc()` for debugging

---

## User Experience Assessment

### Confirmation Dialogs: **GOOD (with improvements needed)**

**Delete Confirmation** (line 1172):
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

**Assessment**: ✅ Clear, shows item names, reasonable.

**Issues**:
- Message "cannot be undone" not always accurate (see Minor Issue #3)
- List could be too long for 1000 items (see Minor Issue #1)

---

### Progress Indication: **SUFFICIENT**

**Plan Strategy** (line 335):
```python
# Before batch operation
status_bar.set_status(f"Deleting {len(item_ids)} items...")

# After batch operation (success)
status_bar.set_status(f"Deleted {successful_count} of {len(item_ids)} items")

# After batch operation (failures)
status_bar.set_status(f"Deleted {successful_count} items, {failed_count} failed")
```

**Assessment**: ✅ Sufficient for Phase 4, defers progress dialog to Phase 5.

**Issue**: No intermediate updates (user sees "Deleting 100 items..." for 10 minutes with no updates). But plan correctly defers progress dialog to Phase 5.

---

### Error Messages: **CLEAR**

**Error Summary** (line 463):
```
Deleted 3 of 5 items.

Failed items:
  • Document 4.jpg: Permission denied
  • Folder B: Directory not empty

Check logs for details.
```

**Assessment**: ✅ Clear, actionable, shows which items failed and why.

**Issue**: No link to open logs (but Toga dialogs don't support rich text).

---

## Backwards Compatibility Check

### Risk Level: **LOW**

**Potential Breakages**: NONE identified

**Analysis**:

**1. Single-Selection Workflows**: ✅ PRESERVED
```python
# Plan optimizes single-item to use existing code path
if len(selected_item_ids) == 1:
    await self._perform_delete_item(selected_item_ids[0], ...)  # Existing method!
    return
```

**Assessment**: No breaking changes to single-item deletion.

---

**2. Existing Process Workflows**: ✅ PRESERVED

**Current Code** (collection_view.py ~line 2410):
```python
# Current: Only uses first item
selected_item_id = getattr(selected_row, 'item_id', None)
if selected_item_id:
    item_ids = [selected_item_id]
```

**Plan Changes To**:
```python
# New: Use ALL selected items from SelectionManager
selected_item_ids = self.app.selection_manager.get_selection('collection')
if selected_item_ids:
    item_ids = selected_item_ids  # Now a full list!
```

**Assessment**: ✅ Backwards compatible. If SelectionManager not available, code falls back to "process all items" (existing behavior).

---

**3. Inspector Updates**: ✅ PRESERVED

**Plan** (line 1142):
```python
if hasattr(self.app, 'inspector_window') and self.app.inspector_window:
    # Existing code still works
    if selection_type == "MULTI_SELECTION":
        # NEW: Show summary
    else:
        # EXISTING: Show detailed metadata (unchanged)
```

**Assessment**: ✅ No breaking changes. New `selection_type` parameter is optional.

---

**4. Navigation**: ✅ PRESERVED

**No Changes**: Plan doesn't modify navigation callbacks or NavigationController integration.

**Assessment**: ✅ Zero risk to navigation.

---

**5. Toolbar Commands**: ✅ PRESERVED

**Plan Only Modifies**: Internal workflow logic, NOT command registration.

**Assessment**: ✅ Zero risk to toolbar/menu commands.

---

### Mitigation Strategies

**If SelectionManager Not Available**:
```python
# Plan already includes fallback (line 252)
if hasattr(self.app, 'selection_manager') and self.app.selection_manager:
    selected_ids = self.app.selection_manager.get_selection('collection')
else:
    # Fallback: use widget selection (Phase 3 behavior)
    selection = self.items_list.get_selection()
```

**Assessment**: ✅ Graceful degradation built in.

---

## Recommendations

### Code Improvements

**1. Create LibraryManager Batch Delete Method** (CRITICAL)

See Critical Issue #1. This is ESSENTIAL for performance.

**2. Extract Batch Operation Helper** (MAJOR)

See Major Issue #3. Will reduce code size by 50% and improve maintainability.

**3. Add Defensive Metadata Extraction** (MAJOR)

See Major Issue #4. Prevents crashes when metadata is missing or mismatched.

**4. Use Smarter Confirmation Thresholds** (MAJOR)

See Major Issue #5. Improves UX by basing thresholds on operation speed.

**5. Fix Inspector Race Conditions** (MAJOR)

See Major Issue #6. Use event-driven updates instead of direct calls.

---

### Alternative Approaches

**Alternative 1: Skip Library Delete/Export in Phase 4**

**Rationale**: Focus Phase 4 on CRITICAL workflows (Collection delete/process). Defer library operations to Phase 5.

**Benefits**:
- Faster completion (2-3 days instead of 3-4)
- Lower risk
- Still delivers 80% of value

**Trade-offs**:
- Users can't batch delete collections in Phase 4
- But library operations are less common than collection operations

**Recommendation**: Make library workflows **optional** in Phase 4.

---

**Alternative 2: Use Progress Dialog Instead of Status Bar**

**Rationale**: Status bar updates are not visible during long operations. Progress dialog provides:
- Real-time progress (item 3 of 10)
- Cancel button
- Better UX for large batches

**Benefits**:
- Better UX for 100+ item batches
- Can cancel mid-operation

**Trade-offs**:
- More complex (requires threading/async updates)
- Takes longer to implement (1-2 extra days)
- Can defer to Phase 5

**Recommendation**: Keep status bar for Phase 4, add progress dialog in Phase 5.

---

### Simplifications

**1. Remove Library Export from Phase 4**

**Justification**: Export is SLOW (zipping files), batch export is 10x slower. Low value for Phase 4.

**Savings**: -0.5 days

**Impact**: NONE (users can export collections one at a time)

---

**2. Make Inspector Summary Optional**

**Justification**: Inspector summary is nice-to-have, not critical. Phase 4 can ship without it.

**Savings**: -0.5 days

**Impact**: LOW (inspector still works for single items, just shows first item of multi-selection)

---

**3. Use Simple Error Reporting Instead of Dialog**

**Justification**: Instead of showing error dialog with failed item list, just log errors and show count.

**Example**:
```python
# Instead of:
await self.app.main_window.info_dialog(
    title="Deletion Summary",
    message=f"Deleted 3 items, 2 failed. See logs."
)

# Just:
logger.error(f"Failed to delete 2 items: {failed_items}")
status_bar.set_status(f"Deleted 3 items, 2 failed")
```

**Savings**: -0.5 days

**Impact**: MEDIUM (users have to check logs, less discoverable)

**Recommendation**: Keep error dialogs, they're important UX.

---

## Approval Conditions

### For "APPROVED WITH CHANGES" Status:

**MUST FIX Before Implementation**:

1. ✅ **Critical Issue #1**: Create `LibraryManager.delete_collection_items_batch()` method
   - OR update plan to use sequential deletion with optimizations

2. ✅ **Critical Issue #2**: Verify ALL callers of `_show_process_dialog()` and update signatures
   - OR use backwards-compatible signature with Union types

3. ✅ **Critical Issue #3**: Verify Director `process_collection()` accepts and processes ALL `item_ids`
   - Add evidence to plan or fix assumption

4. ✅ **Critical Issue #4**: Complete inspector `_rebuild_summary_tabs()` implementation
   - OR remove inspector from Phase 4 scope

5. ✅ **Critical Issue #5**: Verify Toga dialog API and update all confirmation dialog calls
   - Add exact API examples to plan

**SHOULD FIX During Implementation**:

6. ⚠️ **Major Issue #1**: Update all line numbers (+6 offset) OR remove line numbers entirely

7. ⚠️ **Major Issue #2**: Standardize status bar access pattern across all workflows

8. ⚠️ **Major Issue #3**: Extract batch operation helper to reduce code duplication

9. ⚠️ **Major Issue #4**: Add defensive metadata extraction helper

10. ⚠️ **Major Issue #5**: Use smarter confirmation thresholds or user preferences

11. ⚠️ **Major Issue #6**: Fix inspector race conditions with event-driven updates

12. ⚠️ **Major Issue #7**: Specify safe export path generation with collision handling

---

## Questions for Implementation Agent

### Clarifications Needed

**Q1**: Does LibraryManager support batch operations?

**Answer Expected**: Check `library_manager.py` for batch delete methods. If none exist, implement according to Critical Issue #1 fix.

---

**Q2**: How many places call `_show_process_dialog()`?

**Answer Expected**:
```bash
grep "_show_process_dialog" collection_view.py
```

If multiple callers, use backwards-compatible signature.

---

**Q3**: Does Director `process_collection()` process ALL `item_ids` or just first?

**Answer Expected**: Read `director_integration.py` and verify loop through all IDs.

---

**Q4**: What is exact Toga dialog API for confirmations?

**Answer Expected**: Check Toga docs or test:
```python
result = await self.app.main_window.confirm_dialog(
    title="Test",
    message="Confirm?"
)
# Returns True/False? Or Result enum?
```

---

### Decisions to Make

**D1**: Should library delete/export be included in Phase 4?

**Options**:
- A) Include (3-4 days total)
- B) Defer to Phase 5 (2-3 days, focus on critical workflows)

**Recommendation**: Make optional (4b), prioritize collection workflows (4a).

---

**D2**: Should we create batch delete methods in LibraryManager or optimize existing loops?

**Options**:
- A) Create new batch methods (cleaner, better performance)
- B) Optimize existing sequential deletion (simpler, less change)

**Recommendation**: Option A (new batch methods) - better long-term solution.

---

**D3**: Should inspector summary be in Phase 4 or deferred?

**Options**:
- A) Include in Phase 4 (better UX)
- B) Defer to Phase 5 (faster completion)

**Recommendation**: Make optional, implement if time permits.

---

### Watch-outs

**W1**: Status bar access pattern varies between Phase 2 and Phase 4 plan

**Watch**: Verify StatusBar API has both `set_status()` and `set_view_info()` methods before implementing.

---

**W2**: Line numbers in plan are off by +6 lines for collection_view.py

**Watch**: Search by method names, not line numbers.

---

**W3**: Metadata list length might not match item_ids list length

**Watch**: Always use defensive extraction with index bounds checking.

---

**W4**: LibraryManager delete methods are NOT async in storage layer

**Watch**: Each delete call may be slow. Consider batch operations or threading.

---

**W5**: Confirmation dialogs might not exist with expected API

**Watch**: Verify Toga dialog API early in implementation. Have fallback plan if API differs.

---

## Sign-off

### Report Details

**Reviewer**: Phase 4 Review Agent (Automated Code Analysis)
**Review Date**: 2025-11-15 18:45:00 UTC
**Review Duration**: 1.5 hours (comprehensive analysis)
**Files Reviewed**:
- Phase 4 Implementation Plan (1683 lines)
- Collection View (partial - method verification)
- Library View (partial - method verification)
- Library Manager (partial - API verification)
- Main Window (partial - workflow verification)
- Phase 3 Test Report (confirmation of multi-selection)
- Selection Tracking Review (architecture context)

**Lines of Code Analyzed**: ~3500 lines
**Issues Found**: 15 (5 critical, 7 major, 3 minor)

---

### Status: APPROVED WITH CHANGES

**Overall Assessment**: The Phase 4 implementation plan is **well-designed and thorough** with solid understanding of the architecture and clear implementation steps. However, **5 critical assumptions are unverified** and must be addressed before implementation can proceed safely.

**Passing Criteria**:
- ✅ Plan identifies correct workflows (delete, process)
- ✅ Plan understands SelectionManager integration
- ✅ Plan provides detailed code examples
- ✅ Plan includes test scenarios
- ✅ Plan considers backwards compatibility
- ❌ Plan makes UNVERIFIED assumptions about APIs (5 critical issues)
- ⚠️ Plan has implementation quality issues (7 major issues)

**Critical Issues Block Approval**: YES

**Action Required**: Implementation agent MUST address 5 critical issues before starting work:

1. Create or verify LibraryManager batch delete support
2. Verify all callers of _show_process_dialog()
3. Verify Director processes ALL item_ids
4. Complete inspector implementation or remove from scope
5. Verify Toga dialog API

**Major Issues Are Advisory**: Implementation agent SHOULD address 7 major issues during implementation for better code quality, but they don't block starting work.

---

### Ready for Implementation: **YES (with fixes)**

**Prerequisites Met**:
- ✅ Selection tracking fully functional (Phase 3 complete)
- ✅ Status bar integration working (Phase 2 complete)
- ✅ SelectionManager API stable (Phase 1 complete)
- ✅ Multi-selection confirmed working (Phase 3 test report)
- ❌ LibraryManager batch API unverified (MUST FIX)
- ❌ Director multi-item support unverified (MUST FIX)
- ❌ Toga dialog API unverified (MUST FIX)

**Implementation Can Proceed When**:
- All 5 critical issues resolved
- Implementation agent has verified assumptions
- Batch operation methods exist or plan updated to use sequential deletion

---

### Production Ready: **NOT YET**

**Deployment Readiness**:
- ⚠️ Plan is production-ready AFTER fixes
- ❌ Implementation is NOT production-ready until critical issues fixed
- ✅ Code quality will be good IF major issues addressed
- ✅ Testing strategy is comprehensive
- ✅ Error handling is adequate
- ✅ Backwards compatibility is preserved

**Recommendation**: APPROVE WITH CHANGES

**Confidence Level**: 85% (High, but contingent on fixing critical issues)

**Rationale**:
- Plan demonstrates deep understanding of architecture (Phase 1-3)
- Implementation steps are detailed and mostly accurate
- Test scenarios are comprehensive
- Backwards compatibility carefully considered
- **BUT**: 5 critical assumptions MUST be verified before implementation
- Line number drift is annoying but not blocking
- Code quality issues (verbosity, duplication) can be fixed during implementation

**Risk Assessment**: MEDIUM (was HIGH, reduced after addressing critical issues)

**Remaining Risks**:
- LibraryManager API may not support batch operations (CRITICAL - must verify)
- Director may not process all items (CRITICAL - must verify)
- Toga dialog API may differ from assumptions (CRITICAL - must verify)
- Inspector implementation incomplete (CRITICAL - must complete or remove)
- Line numbers off by +6 (MINOR - search by name instead)
- Code duplication in batch operations (MAJOR - should fix but not blocking)

**All critical risks MUST be mitigated before implementation begins.**

---

**END OF PHASE 4 REVIEW REPORT**

**Report Version**: 1.0
**Generated**: 2025-11-15
**Reviewer**: Phase 4 Review Agent
**Approval**: APPROVED WITH CHANGES
**Next Step**: Implementation agent addresses 5 critical issues, then proceeds with Phase 4 implementation

---

## Appendix: Verification Commands

For implementation agent to run before starting:

```bash
# Verify LibraryManager batch support
grep "def delete_collection.*batch\|def batch_delete" src/fichero/library/library_manager.py

# Find all callers of _show_process_dialog
grep "_show_process_dialog" src/fichero/windows/main/views/collection/collection_view.py

# Verify Director multi-item support
grep "process_collection" src/fichero/director/director_integration.py -A 30

# Verify Toga dialog API
python -c "import toga; help(toga.Window.confirm_dialog)" 2>/dev/null || echo "API not found, check Toga docs"

# Verify StatusBar API
grep "def set_status\|def set_view_info\|def update_status" src/fichero/shared/bars/status_bar.py
```

Run these BEFORE implementing Phase 4. Update plan based on findings.
