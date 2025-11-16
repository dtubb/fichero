# Library View UX Improvements

**Date:** November 15, 2025
**Phase:** Phase 6 - Universal Navigation
**Component:** Library View (MainWindow)

## Summary

Implemented UX improvements to the library view based on user feedback:

1. **Removed placeholder content** - No more "Use the + button" message
2. **Always show sidebar** - Empty sidebar displays when no collections exist
3. **Added permanent Inbox** - Auto-created system collection that cannot be deleted
4. **Fixed async issues** - Corrected unawaited coroutines
5. **Fixed widget updates** - Collections now update properly when deleting/adding

## Changes Made

### 1. Removed Placeholder Content (Lines 280-295)

**Before:**
```python
# Check if we have collections to display
if self.collections:
    self._create_collections_display()
else:
    self._create_placeholder_content()
```

**After:**
```python
# Always create the collections display (will show empty sidebar if no collections)
self._create_collections_display()
```

**Rationale:** Empty sidebar is better UX than showing placeholder text. The ListWidget naturally handles empty state.

### 2. Added Inbox Collection (Lines 2135-2156)

**New Method:**
```python
async def _ensure_inbox_exists(self):
    """Ensure the Inbox collection exists, create if missing"""
    # Auto-creates "Inbox" collection if it doesn't exist
    # Called on every collection load to ensure it's always present
```

**Integration:**
```python
async def _load_collections_async(self):
    if self.library_service:
        # Ensure Inbox collection exists (auto-create if needed)
        await self._ensure_inbox_exists()
        # ... rest of loading logic
```

**Rationale:** Users always have at least one collection to work with. Inbox serves as default target for imports.

### 3. Prevent Inbox Deletion (Lines 1595-1621)

**Added Check:**
```python
def _confirm_delete_collection(self, collection_id: str, collection_name: str):
    # Prevent deletion of Inbox collection
    if collection_name == "Inbox":
        logger.warning("Cannot delete Inbox collection")
        self._create_task(self._show_inbox_delete_error())
        return
    # ... continue with normal deletion
```

**New Error Dialog:**
```python
async def _show_inbox_delete_error(self):
    dialog = toga.InfoDialog(
        title=_("Cannot Delete Inbox"),
        message=_("The Inbox collection cannot be deleted. It's a permanent system collection.")
    )
    await self.app.main_window.dialog(dialog)
```

**Rationale:** Prevents user confusion and ensures library always has at least one collection.

### 4. Fixed Async Coroutine Issues

**Issue 1: Line 1648 (unawaited in async context)**
```python
# Before:
self.refresh_collections()

# After:
await self.refresh_collections()
```

**Issue 2: Line 2053 (unawaited in sync context)**
```python
# Before:
def refresh(self):
    self.refresh_collections()  # RuntimeWarning: coroutine never awaited

# After:
def refresh(self):
    self._create_task(self.refresh_collections())  # Properly scheduled
```

**Rationale:** Fixes RuntimeWarning and ensures proper async execution.

### 5. Fixed Widget Update Logic (Lines 364-390)

**Before:**
```python
# Only checked collection count
needs_recreate = (
    not hasattr(self, 'collections_list') or
    not self.collections_list or
    len(collection_data) != self._last_collection_count
)
```

**After:**
```python
# Check both count AND collection IDs
current_ids = {item['id'] for item in collection_data}
last_ids = getattr(self, '_last_collection_ids', set())

needs_recreate = (
    not hasattr(self, 'collections_list') or
    not self.collections_list or
    len(collection_data) != self._last_collection_count or
    current_ids != last_ids  # NEW: Detect ID changes
)

if needs_recreate:
    # ... recreate widget
    self._last_collection_ids = current_ids  # NEW: Track IDs
```

**Rationale:** Fixes bug where deleting collection A and adding collection B (same count) wouldn't update the display.

### 6. Fixed Method Signature (Lines 280-298)

**Before:**
```python
def _create_content(self):
    # TypeError when called by add_background_task
```

**After:**
```python
def _create_content(self, widget=None):
    """Create the library view content

    Args:
        widget: Optional widget parameter (ignored, for compatibility with Toga callbacks)
    """
```

**Rationale:** Toga callbacks pass widget parameter, method signature must accept it.

## Testing Recommendations

### Test Case 1: Empty Library
1. Delete all collections except Inbox
2. Try to delete Inbox - should show error
3. Verify empty sidebar displays (no placeholder text)
4. Verify Inbox remains visible

### Test Case 2: Delete and Add
1. Start with 3 collections (Inbox + 2 others)
2. Delete one collection
3. Add a new collection
4. Verify new collection appears immediately
5. Verify count stays at 3

### Test Case 3: Fresh Start
1. Delete library database
2. Launch app
3. Verify Inbox auto-created
4. Verify no errors on first load

### Test Case 4: Async Operations
1. Rapidly delete/add collections
2. Verify no RuntimeWarnings in logs
3. Verify UI remains responsive
4. Verify no race conditions

## Files Modified

- `src/fichero/windows/main/views/library/library_view.py` (~200 lines changed)

## Impact Assessment

### Positive
- ✅ Cleaner UX (no confusing placeholder text)
- ✅ Always-available Inbox provides clear default
- ✅ Fixes widget update bug
- ✅ Eliminates async warnings
- ✅ Better empty state handling

### Neutral
- ℹ️ Inbox cannot be deleted (intentional constraint)
- ℹ️ Inbox auto-created on every load (minimal overhead)

### Risks
- ⚠️ Migration: Existing users without Inbox will get one auto-created
- ⚠️ Translation: "Inbox" hardcoded (should add to i18n strings)
- ⚠️ Future: If we add collection types, Inbox should be flagged as "system" type

## Follow-up Tasks

1. **Add i18n support** - Translate "Inbox" collection name
2. **Add collection metadata** - Flag Inbox as system collection in database
3. **Update documentation** - Explain Inbox concept to users
4. **Add visual indicator** - Consider icon/badge to show Inbox is special
5. **Test mobile UI** - Verify empty sidebar works on iOS/Android

## Code Quality

- ✅ Maintains backward compatibility
- ✅ Follows existing patterns (_create_task, async/await)
- ✅ Proper error handling
- ✅ Clear logging
- ✅ No deprecated APIs used
- ✅ Type hints where applicable

## Performance

- **Inbox check:** O(n) scan on every load - acceptable for typical collection counts
- **ID comparison:** Set comparison O(n) - minimal overhead vs previous count-only check
- **Auto-creation:** Only happens once per app lifecycle when Inbox missing

## Conclusion

These changes improve the library view UX by:
1. Removing confusing placeholder UI
2. Ensuring users always have a default collection
3. Fixing critical async bugs
4. Improving widget update reliability

The implementation is clean, follows existing patterns, and has minimal performance impact. Ready for testing and user feedback.
