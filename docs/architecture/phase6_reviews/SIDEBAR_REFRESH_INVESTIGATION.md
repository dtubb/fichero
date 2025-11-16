# Sidebar Refresh Investigation Report

**Date**: November 15, 2025
**Component**: Library View Sidebar
**Scope**: Unexpected refresh/deletion behavior analysis

---

## Executive Summary

### Findings Overview
The investigation revealed **no critical bugs causing sidebar deletion**, but identified **multiple inefficiencies and potential race conditions** that contribute to the perception of "refreshing" or "deleting" behavior. The duplicate logs are explained by the interaction between `show()` and `_load_collections_async()`.

### Severity Assessment
- **P0 Issues**: None (no data loss or crashes)
- **P1 Issues**: 2 (duplicate refresh calls, potential race conditions)
- **P2 Issues**: 3 (logging clarity, missing guards, inefficient widget recreation)

### Root Cause
The sidebar is **working as designed**, but the design has overlapping refresh mechanisms:
1. `show()` method calls `_create_collections_display()` directly
2. `_load_collections_async()` also calls `_create_content()` → `_create_collections_display()`
3. Event handlers trigger additional refreshes
4. ListWidget.remove_item() triggers `set_data()` which rebuilds the entire widget

This creates a **cascade of refreshes** that appear as "deletion" or "unexpected refreshes" in the logs.

---

## Duplicate Logs Investigation

### Why Logs Appear Twice

The duplicate log pattern:
```
DEBUG:fichero.windows.main.views.library.library_view:Loaded 1 collections from library (sort: name, A-Z).
DEBUG:fichero.windows.main.views.library.library_view:Skipping widget recreation - no changes detected (1 collections)
DEBUG:fichero.windows.main.views.library.library_view:Created display for 1 collections
DEBUG:fichero.windows.main.views.library.library_view:Collections display refreshed
```

**Call Stack Analysis**:

1. **First Call Path**: `show()` → `_create_collections_display()` (line 190)
   - File: `library_view.py`, lines 164-193
   - Code:
   ```python
   def show(self):
       # ...
       if self.collections:
           logger.debug("🔄 Refreshing collections display on show()")
           self._create_collections_display()  # DIRECT CALL #1
   ```
   - This creates the first set of logs

2. **Second Call Path**: `_load_collections_async()` → `_create_content()` → `_create_collections_display()` (line 2219)
   - File: `library_view.py`, lines 2194-2219
   - Code:
   ```python
   async def _load_collections_async(self):
       # ... loads collections ...
       self._create_content()  # CALL #2 (via _create_content)
   ```
   - This creates the second set of logs

3. **Why Both Happen**: The `show()` method is called when the view becomes active, and it:
   - Checks if deferred load is needed → triggers `_load_collections_async()` (line 180)
   - ALSO immediately calls `_create_collections_display()` if collections exist (line 190)

   This creates a race: both paths execute, causing duplicate work.

**Code Locations**:
- `show()`: Lines 164-199 in `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/library/library_view.py`
- `_load_collections_async()`: Lines 2194-2226
- `_create_collections_display()`: Lines 298-307

---

## Refresh Trigger Analysis

### All Code Paths That Trigger Refreshes

| Trigger | Method | Line | Legitimate? | Notes |
|---------|--------|------|-------------|-------|
| **1. View Show** | `show()` → `_create_collections_display()` | 190 | Yes | Clears cached selection state |
| **2. Async Load** | `_load_collections_async()` → `_create_content()` | 2219 | Yes | Loads data from DB |
| **3. Deferred Load** | `show()` → `_load_collections_async()` | 180 | Yes | Event loop wasn't ready during init |
| **4. Collection Added** | `_on_collection_added_event()` → `_load_collections_async()` | 3150 | Yes | Event-driven sync |
| **5. Collection Updated** | `_on_collection_updated_event()` → `_load_collections_async()` | 3205 | Yes | Event-driven sync |
| **6. Collection Deleted** | `_on_collection_deleted_event()` → incremental or full refresh | 3179-3190 | Partial | Tries incremental, falls back to full |
| **7. Sort Toggle** | `_on_toggle_sort()` → `_load_collections_async()` | 2343 | Yes | User action |
| **8. Manual Refresh** | `refresh_collections()` → `_load_collections_async()` | 1852 | Yes | Public API |
| **9. Delete Action** | `_perform_delete_collection()` → incremental removal | Various | Yes | User action with smart update |

### Redundant Refresh Pattern (P1 Issue)

**Problem**: `show()` method triggers BOTH:
1. Direct refresh via `_create_collections_display()` (line 190)
2. Async data load via `_load_collections_async()` (line 180)

This causes the widget to be rebuilt twice in quick succession.

**Flow Diagram**:
```
show() called
    ├─> Check _needs_initial_load? (line 177)
    │   └─> YES: create_task(_load_collections_async())
    │           └─> _load_collections_async()
    │               └─> _create_content()
    │                   └─> _create_collections_display()  ← REFRESH #2
    │
    └─> Check if collections exist? (line 188)
        └─> YES: _create_collections_display()  ← REFRESH #1
```

**Impact**: Double refresh on every view activation when both conditions are true.

---

## Widget Update Mechanism Review

### How `remove_item()` Works

**File**: `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/widgets/list_widget/base.py`
**Lines**: 774-793

```python
def remove_item(self, item_id: str) -> bool:
    """Remove an item by its ID."""
    # Find and remove from _data
    original_len = len(self._data)
    self._data = [item for item in self._data if item.get('_item_id') != item_id]

    if len(self._data) == original_len:
        return False  # Item not found

    # Rebuild the widget data
    self.set_data(self._data)  # ← TRIGGERS FULL REBUILD
    return True
```

### Does It Trigger Full Rebuilds?

**YES**. The `remove_item()` method calls `set_data()` which:

1. **Converts data to tree format** (if tree widget): Lines 392-403
   ```python
   if is_tree_widget and data and any('path' in item for item in data):
       data = self._convert_flat_to_tree(data)
   ```

2. **Always recreates the source**: Lines 426-437
   ```python
   # ALWAYS recreate source - Toga doesn't properly refresh when using clear()/append()
   if is_tree_widget:
       self._source = TreeSource(accessors=accessors, data=source_data)
   else:
       self._source = ListSource(accessors=accessors, data=source_data)

   # Always re-attach the new source to the widget
   self.renderer.attach_source(self._source)
   ```

3. **For macOS sidebar (NSOutlineView)**: Calls `reloadData()` (line 700 in `macos_sidebar.py`)
   ```python
   def attach_source(self, source):
       # ...
       self._toga_sidebar.reloadData()  # ← FULL UI REBUILD
   ```

### Performance Characteristics

**Full Rebuild on Every Change**:
- Remove single item → Rebuild entire NSOutlineView
- Add single item → Rebuild entire NSOutlineView
- Update subtitle → Need to call `set_data()` → Rebuild entire NSOutlineView

**Why This Design?**:
From the comment in `base.py` line 426:
> "ALWAYS recreate source - Toga doesn't properly refresh when using clear()/append()"

This is a **workaround for Toga limitations**, not an intentional design choice.

**Impact**:
- Small lists (1-100 items): Negligible performance impact
- Large lists (100+ items): Noticeable lag on updates
- Current usage (1-10 collections): No user-facing impact

---

## Race Condition Analysis

### Async/Await Patterns

**Potential Race #1**: `show()` + `_load_collections_async()`

**Location**: Lines 164-193 in `library_view.py`

**Scenario**:
1. View is initialized without event loop
2. `_needs_initial_load = True` is set
3. Later, `show()` is called
4. Two things happen in parallel:
   - Line 180: `self._create_task(self._load_collections_async())`
   - Line 190: `self._create_collections_display()`

**Race Details**:
- Both modify `self.collections` (indirectly via `_load_collections_async`)
- Both call `_create_collections_display()`
- No lock or guard prevents concurrent execution
- `_create_task()` adds to background tasks, executes asynchronously
- Direct call to `_create_collections_display()` is synchronous

**Actual Risk**: **LOW** - The smart update logic in `_create_collections_detailed_list()` (lines 361-387) prevents widget recreation if data hasn't changed:
```python
needs_recreate = (
    not hasattr(self, 'collections_list') or
    not self.collections_list or
    len(collection_data) != self._last_collection_count or
    current_ids != last_ids
)

if needs_recreate:
    # ... recreate ...
else:
    logger.debug(f"Skipping widget recreation - no changes detected")
```

This acts as a **passive race guard** - whichever path runs second will see "no changes" and skip the update.

**However**: The logs show **both paths log "Created display"** (line 304), suggesting both paths reach the display creation code, but one skips widget recreation.

### Event Subscription Timing

**Location**: Lines 148-156 in `library_view.py`

**Events Subscribed**:
```python
subscribe_to_navigation("collection_added", self._on_collection_added_event)
subscribe_to_navigation("collection_deleted", self._on_collection_deleted_event)
subscribe_to_navigation("collection_updated", self._on_collection_updated_event)
subscribe_to_navigation("folder_import_started", self._on_folder_import_started_event)
subscribe_to_navigation("folder_import_progress", self._on_folder_import_progress_event)
subscribe_to_navigation("folder_import_completed", self._on_folder_import_completed_event)
```

**Race Scenario**:
1. User deletes a collection via UI (calls `_perform_delete_collection`)
2. `_perform_delete_collection` does incremental update (removes from sidebar)
3. `_perform_delete_collection` emits `collection_deleted` event
4. Event handler `_on_collection_deleted_event` receives event
5. Event handler checks if collection exists in list (line 3171)
6. **Race**: Collection might already be removed, causing handler to think it's an "external delete"

**Actual Implementation** (lines 3160-3196):
```python
def _on_collection_deleted_event(self, event):
    collection_exists = any(c.get('id') == collection_id for c in self.collections)

    if collection_exists:
        # External delete - remove incrementally
        self.collections = [c for c in self.collections if c.get('id') != collection_id]

        if hasattr(self, 'collections_list') and self.collections_list:
            removed = self.collections_list.remove_item(collection_id)
            # ...
    else:
        # Already removed by our own delete handler
        logger.debug(f"Collection already removed (local delete)")
```

**Guard Present**: Yes - checks if collection exists before removing
**Risk**: **LOW** - Properly handles both cases (external vs local delete)

### Concurrent Update Scenarios

**Scenario 1**: Multiple event handlers fire simultaneously
- **Risk**: Medium
- **Guard**: None explicit, but smart update logic prevents double-recreation
- **Example**: `collection_updated` + `folder_import_completed` both trigger `_load_collections_async()`
- **Impact**: Multiple async tasks created, each loads data and calls `_create_content()`

**Scenario 2**: User action during async load
- **Risk**: Low
- **Guard**: Smart update logic compares collection IDs
- **Example**: User clicks collection while `_load_collections_async()` is running
- **Impact**: Selection might be lost if widget is recreated

---

## Bugs Found

### P1-1: Duplicate Refresh on View Activation

**Priority**: P1 (Performance impact, confusing logs)

**Description**: The `show()` method triggers two refreshes when both conditions are met:
1. Collections data exists in memory
2. Deferred load flag is set

**Code Location**:
- File: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/library/library_view.py`
- Lines: 177-192

**Impact**:
- Widget rebuilt twice unnecessarily
- Duplicate log entries confuse debugging
- Wasted CPU cycles on every view activation
- User might see brief "flicker" if timing is right

**Recommended Fix**:
```python
def show(self):
    if self._showing:
        return

    self._showing = True
    try:
        # FIX: Only trigger ONE refresh path
        if getattr(self, '_needs_initial_load', False):
            self._needs_initial_load = False
            # Async load will call _create_content() → _create_collections_display()
            self._create_task(self._load_collections_async())
        elif self.collections:
            # Only refresh if NOT doing async load
            # (Async load would handle this)
            self._create_collections_display()

        if hasattr(self, 'coordinator') and self.coordinator:
            self.coordinator.set_active_view('library')
    finally:
        self._showing = False
```

**Alternative Fix**: Remove line 190's direct call to `_create_collections_display()` and rely solely on async load path.

---

### P1-2: Full Widget Rebuild on Single Item Removal

**Priority**: P1 (Scalability concern, inefficient)

**Description**: `remove_item()` calls `set_data()` which rebuilds the **entire** widget instead of removing just one item from the native widget.

**Code Location**:
- File: `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/widgets/list_widget/base.py`
- Line: 792 (`self.set_data(self._data)`)
- File: `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/widgets/list_widget/renderers/macos_sidebar.py`
- Line: 700 (`self._toga_sidebar.reloadData()`)

**Impact**:
- O(n) operation for removing 1 item from n items
- Loses selection state (must be restored manually)
- Unnecessary work for NSOutlineView (could remove single row)
- Will become noticeable with 100+ collections

**Recommended Fix**:

Option 1: **Implement incremental removal in MacOSSidebarRenderer**
```python
# In macos_sidebar.py
def remove_item_by_id(self, item_id: str) -> bool:
    """Remove a single item without full rebuild"""
    # Find item index
    index = None
    for i, item in enumerate(self._wrapped_items):
        if item._python_data.get('id') == item_id:
            index = i
            break

    if index is None:
        return False

    # Remove from data
    self._data.pop(index)
    self._wrapped_items.pop(index)

    # Use NSOutlineView's incremental update API
    index_set = NSIndexSet.indexSetWithIndex(index)
    self._toga_sidebar.removeItemsAtIndexes(index_set, inParent=None)

    return True
```

Option 2: **Keep current behavior but add comment explaining why**
```python
# WORKAROUND: Toga's ListSource/TreeSource don't properly update when using
# remove() or clear(). We must recreate the entire source and call reloadData()
# to ensure the widget reflects changes. This is inefficient for large lists
# but necessary until Toga fixes its source update mechanism.
self.set_data(self._data)
```

---

### P2-1: Missing Event Handler Guards

**Priority**: P2 (Defensive programming, edge case handling)

**Description**: Event handlers like `_on_collection_updated_event` always trigger full refresh without checking if the collection is actually in the current view.

**Code Location**:
- File: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/library/library_view.py`
- Lines: 3198-3208

```python
def _on_collection_updated_event(self, event):
    collection_name = event.data.get("collection_name", "Unknown")
    logger.info(f"📡 Event received: collection_updated - {collection_name}")

    # Reload collections to show updates
    self._create_task(self._load_collections_async())  # ← Always full refresh
```

**Impact**:
- Full database query + widget rebuild for updates to collections not in current view
- Multiple concurrent events trigger multiple async tasks
- Potential for event storm (many updates → many refreshes)

**Recommended Fix**:
```python
def _on_collection_updated_event(self, event):
    collection_id = event.data.get("collection_id")
    collection_name = event.data.get("collection_name", "Unknown")
    logger.info(f"📡 Event received: collection_updated - {collection_name}")

    # Check if this collection is in our view
    collection_in_view = any(c.get('id') == collection_id for c in self.collections)

    if collection_in_view:
        # Incremental update: find and update just this collection
        # (Would need new method: update_collection_by_id)
        self._create_task(self._update_single_collection(collection_id))
    else:
        # Not in view, ignore (it might be filtered out by current sort)
        logger.debug(f"Collection {collection_name} not in current view, ignoring update")
```

---

### P2-2: Unclear Logging for Smart Update

**Priority**: P2 (Developer experience, debugging clarity)

**Description**: The log message "Skipping widget recreation - no changes detected" doesn't explain **what** changed or **why** it's skipping. Also, "Created display for N collections" appears even when widget wasn't recreated.

**Code Location**:
- File: `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/library/library_view.py`
- Lines: 304, 387

**Impact**:
- Confusing logs make debugging harder
- Can't tell from logs whether widget was actually recreated or not
- Duplicate "Created display" messages misleading

**Recommended Fix**:
```python
if needs_recreate:
    logger.info(f"🔄 Library: Recreating ListWidget with {len(collection_data)} collections (reason: {recreate_reason})")
    self._recreate_detailed_list(collection_data)
    self._last_collection_count = len(collection_data)
    self._last_collection_ids = current_ids

    if current_selection_id:
        self._restore_selection(collection_data, current_selection_id)

    logger.debug(f"✅ Widget recreated successfully")
else:
    logger.debug(f"⏭️ Skipping widget recreation - data unchanged ({len(collection_data)} collections, same IDs)")

# Remove or move this log to only appear after recreation
# logger.debug(f"Created display for {len(self.collections)} collections")
```

Where `recreate_reason` is:
```python
recreate_reason = []
if not hasattr(self, 'collections_list') or not self.collections_list:
    recreate_reason.append("widget missing")
if len(collection_data) != self._last_collection_count:
    recreate_reason.append(f"count changed ({self._last_collection_count} → {len(collection_data)})")
if current_ids != last_ids:
    recreate_reason.append("IDs changed")

recreate_reason = ", ".join(recreate_reason) if recreate_reason else "unknown"
```

---

### P2-3: No Debouncing for Event Storms

**Priority**: P2 (Performance under stress)

**Description**: Multiple rapid events (e.g., bulk import adding 10 collections) trigger 10 separate `_load_collections_async()` tasks with no debouncing or throttling.

**Code Location**:
- All event handlers: Lines 3143-3207 in `library_view.py`

**Impact**:
- Multiple concurrent database queries
- Multiple widget rebuilds
- CPU waste, potential UI freezing during bulk operations
- Last refresh wins, but all intermediate work is wasted

**Recommended Fix**:
```python
class LibraryView(BaseView, ViewCommandMixin):
    def __init__(self, app, is_mobile: bool = False):
        # ...
        self._pending_refresh = None  # Track pending refresh task
        self._refresh_debounce_delay = 0.3  # 300ms debounce

    def _schedule_refresh_debounced(self, reason: str):
        """Schedule a debounced refresh (cancels previous if pending)"""
        # Cancel existing pending refresh
        if self._pending_refresh and not self._pending_refresh.done():
            self._pending_refresh.cancel()
            logger.debug(f"Cancelled pending refresh (new reason: {reason})")

        # Schedule new refresh
        async def debounced_refresh():
            await asyncio.sleep(self._refresh_debounce_delay)
            logger.debug(f"Executing debounced refresh (reason: {reason})")
            await self._load_collections_async()

        self._pending_refresh = self._create_task(debounced_refresh())

    def _on_collection_added_event(self, event):
        collection_name = event.data.get("collection_name", "Unknown")
        logger.info(f"📡 Event received: collection_added - {collection_name}")

        # Use debounced refresh instead of immediate
        self._schedule_refresh_debounced(f"collection_added: {collection_name}")
```

---

## Recommendations

### Immediate Fixes Needed

1. **Fix P1-1** (Duplicate refresh on show)
   - Priority: High
   - Effort: Low (5 minutes)
   - Impact: Eliminates confusing duplicate logs, improves performance
   - Change: Modify `show()` method to avoid double refresh

2. **Add logging clarity** (P2-2)
   - Priority: Medium
   - Effort: Low (10 minutes)
   - Impact: Makes debugging much easier
   - Change: Improve log messages with reasons and outcomes

3. **Document P1-2** (Full rebuild behavior)
   - Priority: Medium
   - Effort: Very Low (2 minutes)
   - Impact: Explains current behavior to future developers
   - Change: Add comment explaining why full rebuild is necessary

### Architecture Improvements

1. **Implement Incremental Updates**
   - Replace full `set_data()` rebuilds with incremental operations
   - Add methods to NSOutlineView renderer:
     - `add_item_at_index()`
     - `remove_item_at_index()`
     - `update_item_at_index()`
   - Requires deeper Toga/NSOutlineView integration
   - **Benefit**: O(1) updates instead of O(n) rebuilds

2. **Add Event Debouncing**
   - Implement debounced refresh scheduler (P2-3 fix)
   - Prevents event storms from causing performance issues
   - **Benefit**: Smooth UI during bulk operations

3. **Smart Event Filtering**
   - Event handlers should check if update affects current view before refreshing
   - Only refresh for collections actually visible
   - **Benefit**: Reduces unnecessary work

4. **Separate Concerns**
   - Move refresh logic out of `show()` method
   - Create dedicated `_refresh_if_needed()` method
   - Call from both `show()` and async load completion
   - **Benefit**: Single code path, no duplication

### Debugging Instrumentation to Add

1. **Refresh Tracking**
   ```python
   class LibraryView(BaseView):
       def __init__(self, ...):
           self._refresh_count = 0  # Track total refreshes
           self._refresh_history = []  # Track last 10 refresh reasons

       def _track_refresh(self, reason: str, full_rebuild: bool):
           self._refresh_count += 1
           self._refresh_history.append({
               'timestamp': time.time(),
               'reason': reason,
               'full_rebuild': full_rebuild,
               'collection_count': len(self.collections)
           })
           if len(self._refresh_history) > 10:
               self._refresh_history.pop(0)

           logger.debug(f"📊 Refresh #{self._refresh_count}: {reason} (full={full_rebuild})")
   ```

2. **Performance Metrics**
   ```python
   import time

   def _create_collections_detailed_list(self):
       start_time = time.time()
       try:
           # ... existing code ...
       finally:
           elapsed = (time.time() - start_time) * 1000  # ms
           logger.debug(f"⏱️ Widget recreation took {elapsed:.2f}ms")

           if elapsed > 100:  # Warn if > 100ms
               logger.warning(f"⚠️ Slow widget recreation: {elapsed:.2f}ms for {len(self.collections)} collections")
   ```

3. **Smart Update Decision Logging**
   ```python
   # In _create_collections_detailed_list
   if needs_recreate:
       logger.info(f"🔄 REBUILD: {recreate_reason}")
       logger.debug(f"   Previous: {self._last_collection_count} items, IDs={self._last_collection_ids}")
       logger.debug(f"   Current: {len(collection_data)} items, IDs={current_ids}")
   else:
       logger.debug(f"⏭️ SKIP: No changes")
   ```

4. **Event Storm Detection**
   ```python
   class LibraryView(BaseView):
       def __init__(self, ...):
           self._event_timestamps = []  # Track event timing

       def _on_collection_added_event(self, event):
           now = time.time()
           self._event_timestamps.append(now)

           # Clean old timestamps (>5 seconds)
           self._event_timestamps = [t for t in self._event_timestamps if now - t < 5.0]

           # Detect storm (>5 events in 5 seconds)
           if len(self._event_timestamps) > 5:
               logger.warning(f"⚠️ EVENT STORM: {len(self._event_timestamps)} events in 5 seconds!")

           # ... rest of handler ...
   ```

---

## Conclusion

The sidebar is **not actually deleting itself** - it's working as designed. However, the design has multiple overlapping refresh mechanisms that create the **perception** of unexpected behavior:

1. **Smart update logic prevents most inefficiency** - The `needs_recreate` check means duplicate calls to `_create_collections_display()` are mostly harmless
2. **Logs are misleading** - "Created display" appears even when widget wasn't recreated
3. **Double refresh pattern is real** - `show()` method genuinely triggers two refresh paths unnecessarily
4. **Full rebuilds are intentional** - Due to Toga limitations, not a bug

**Next Steps**:
1. Fix P1-1 (duplicate refresh) immediately - 5 minute fix
2. Improve logging (P2-2) for better debugging - 10 minute fix
3. Consider incremental update architecture for future scalability
4. Add instrumentation to track refresh patterns in production

**No emergency action needed** - Current behavior is stable and functional, just inefficient.
