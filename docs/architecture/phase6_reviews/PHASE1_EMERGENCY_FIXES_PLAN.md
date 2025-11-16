# Phase 1 Emergency Fixes - Implementation Plan

**Date:** November 16, 2025
**Status:** IN PROGRESS
**Priority:** P0 - CRITICAL

## Issues to Fix

### 1. Incremental Remove Failure (BLOCKING)
**Symptom:**
```
WARNING:...base:Incremental remove failed, falling back to full rebuild
```

**Root Cause:**
NSOutlineView `removeItemsAtIndexes` method not working as expected. Your trace logging shows it's hitting one of these errors:
- Method doesn't exist on the object
- Wrong method signature
- Rubicon parameter marshalling issue

**Fix Strategy:**
The issue is that `TogaSidebar` (our custom NSOutlineView subclass) needs to use `reloadData()` instead of the incremental `removeItemsAtIndexes`. Those methods are for parent-child hierarchies, not flat lists.

**Solution:**
For NSOutlineView with flat data (no tree hierarchy), use:
1. Update data arrays (already doing this)
2. Call `reloadData()` (simple, reliable, fast for small lists)

OR use the proper APIs:
1. `beginUpdates()` / `endUpdates()`
2. `removeRowsAtIndexes:withAnimation:` (NOT removeItemsAtIndexes)

### 2. Duplicate Event Execution (CRITICAL)

**Symptom:**
Every log appears twice:
```
INFO:...Successfully deleted collection: Untitled Collection
INFO:...Successfully deleted collection: Untitled Collection
```

**Root Causes:**
1. Event handler subscribed twice
2. Method called from multiple code paths
3. Event emitted multiple times for same action

**Fix Strategy:**
Add event deduplication wrapper and audit subscriptions.

## Implementation Steps

### Step 1: Fix NSOutlineView Incremental Remove

**File:** `src/fichero/shared/widgets/list_widget/renderers/macos_sidebar.py`

**Option A: Use reloadData() (Simple, Reliable)**
```python
def remove_item_at_index(self, index: int) -> bool:
    try:
        if not self._toga_sidebar or not self._wrapped_items:
            return False

        if index < 0 or index >= len(self._wrapped_items):
            return False

        # Remove from data
        self._wrapped_items.pop(index)
        self._data.pop(index)

        # For flat lists (no hierarchy), reloadData() is fastest
        # It's ~2ms for <100 items, plenty fast
        self._toga_sidebar.reloadData()

        logger.info(f"✅ Native reload after remove: index {index}")
        return True

    except Exception as e:
        logger.error(f"Failed to remove: {e}")
        return False
```

**Option B: Use NSTableView APIs (More Complex)**
```python
def remove_item_at_index(self, index: int) -> bool:
    try:
        # Remove from data FIRST
        self._wrapped_items.pop(index)
        self._data.pop(index)

        # Use NSTableView's row-based removal (NSOutlineView inherits from NSTableView)
        # For flat lists, use removeRowsAtIndexes, NOT removeItemsAtIndexes
        from rubicon.objc import ObjCClass
        NSIndexSet = ObjCClass("NSIndexSet")
        NSAnimationContext = ObjCClass("NSAnimationContext")

        index_set = NSIndexSet.indexSetWithIndex(index)

        # Wrap in animation context
        NSAnimationContext.beginGrouping()
        self._toga_sidebar.removeRowsAtIndexes_withAnimation_(
            index_set,
            0x10  # NSTableViewAnimationSlideUp
        )
        NSAnimationContext.endGrouping()

        logger.info(f"✅ Removed row {index} with animation")
        return True

    except Exception as e:
        logger.error(f"Failed: {e}")
        # Restore data
        self._wrapped_items.insert(index, removed_item)
        self._data.insert(index, removed_data)
        return False
```

**Recommendation:** Start with Option A (`reloadData()`). It's simpler, reliable, and fast enough for library sidebar (<100 collections).

### Step 2: Add Event Deduplication

**File:** `src/fichero/shared/navigation/navigation_event_bus.py`

**Add deduplication decorator:**
```python
import time
from functools import wraps

class EventDeduplicator:
    """Prevents duplicate event emissions within time window"""
    def __init__(self):
        self._last_events = {}  # (event_type, data_hash) -> timestamp
        self._window_ms = 50  # 50ms window

    def should_emit(self, event_type: str, data: dict) -> bool:
        """Check if event should be emitted or is duplicate"""
        # Create hash from critical data only
        critical_keys = ['collection_id', 'item_id', 'file_path']
        data_values = tuple(data.get(k) for k in critical_keys if k in data)
        key = (event_type, data_values)

        now = time.time() * 1000
        last_time = self._last_events.get(key, 0)

        if now - last_time < self._window_ms:
            logger.debug(f"⏭️ Skipping duplicate event: {event_type}")
            return False

        self._last_events[key] = now
        return True

# Global deduplicator
_deduplicator = EventDeduplicator()

def emit(event_type: str, data: dict):
    """Emit event with deduplication"""
    if not _deduplicator.should_emit(event_type, data):
        return  # Skip duplicate

    # Original emit logic...
```

### Step 3: Fix Duplicate Subscriptions

**Check these files:**

1. **src/fichero/windows/main/main_window.py**
   - Search for `subscribe_to_navigation`
   - Check if same handler subscribed multiple times
   - Consolidate

2. **src/fichero/windows/main/views/collection/collection_view.py**
   - Check `__init__` for duplicate subscriptions
   - Check if `show()` re-subscribes

3. **src/fichero/windows/main/views/library/library_view.py**
   - Same checks

**Pattern to find:**
```python
# BAD - subscribes every time show() is called
def show(self):
    subscribe_to_navigation("event", self.handler)

# GOOD - subscribe once in __init__
def __init__(self):
    subscribe_to_navigation("event", self.handler)
    self._subscribed = True
```

### Step 4: Consolidate Event Emissions

**File:** `src/fichero/shared/navigation/navigation_controller.py`

**Check for patterns like:**
```python
# BAD - emits multiple events for same action
def navigate_to_collection(self, collection_id):
    emit("SHOW_COLLECTION", {...})
    emit("SELECTION_CHANGED", {...})  # Duplicate!
    emit("STATE_CHANGED", {...})      # Another duplicate!

# GOOD - emit ONE event with all data
def navigate_to_collection(self, collection_id):
    emit("STATE_CHANGED", {
        'context': 'collection',
        'collection_id': collection_id,
        # ... all needed data
    })
```

## Testing Plan

### Test 1: Verify Incremental Remove Works
```bash
briefcase dev
# Delete a collection
# ✅ Should see: "✅ Native reload after remove"
# ❌ Should NOT see: "Incremental remove failed, falling back"
```

### Test 2: Verify No Duplicate Logs
```bash
briefcase dev
# Delete a collection
# ✅ Each log line appears ONCE
# ✅ No duplicate "Successfully deleted collection"
```

### Test 3: Verify Performance
```bash
# Delete 5 collections rapidly
# ✅ UI remains responsive
# ✅ No lag or freezing
```

## Success Criteria

1. ✅ No "Incremental remove failed" warnings
2. ✅ Each log line appears exactly once
3. ✅ Delete operations are smooth and fast
4. ✅ No duplicate event emissions in trace logs

## Implementation Order

1. **Fix NSOutlineView remove** (30 min) - Stops fallback loop
2. **Add event deduplication** (30 min) - Safety net for duplicates
3. **Audit subscriptions** (1 hour) - Find and fix duplicate handlers
4. **Consolidate event emissions** (1 hour) - Reduce event spam
5. **Test thoroughly** (30 min) - Verify all fixes work

**Total Time:** ~3.5 hours

## Next Steps After Phase 1

Once duplicates are eliminated:
- Phase 2: Implement LibraryService with caching
- Phase 3: Refactor to cleaner architecture

But first, we MUST stop the bleeding with these emergency fixes.
