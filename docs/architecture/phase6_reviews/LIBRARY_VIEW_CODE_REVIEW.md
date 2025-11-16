# Library View Code Review
**Phase 6 - Universal Navigation & Workspace Management**

**Date:** November 15, 2025
**Reviewer:** Claude Code Assistant
**Files Reviewed:**
- `src/fichero/windows/main/views/library/library_view.py` (3031 lines)
- `src/fichero/windows/main/main_window.py` (1973 lines)
- `src/fichero/shared/views/base_view.py`

---

## Executive Summary

The LibraryView implementation shows a generally solid architecture with good use of composition patterns and event-driven design. However, the code review identified **7 critical bugs (P0)**, **12 major issues (P1)**, and **15 minor issues (P2)** that could impact functionality, performance, and maintainability. The most serious concerns involve missing cleanup handlers (memory leaks), synchronization issues between UI updates and async operations, excessive widget recreation, and inconsistent error handling.

---

## Critical Bugs (P0 - Blocks Functionality)

### P0-1: Missing Event Cleanup on View Destruction
**Location:** `library_view.py:144-149`

**Issue:**
```python
# Subscribe to library state events for automatic synchronization
subscribe_to_navigation("collection_added", self._on_collection_added_event)
subscribe_to_navigation("collection_deleted", self._on_collection_deleted_event)
subscribe_to_navigation("collection_updated", self._on_collection_updated_event)
subscribe_to_navigation("folder_import_started", self._on_folder_import_started_event)
subscribe_to_navigation("folder_import_progress", self._on_folder_import_progress_event)
subscribe_to_navigation("folder_import_completed", self._on_folder_import_completed_event)
```

**Problem:** LibraryView subscribes to 6 navigation events but never unsubscribes. There's no `cleanup()` or `__del__()` method to unregister these handlers.

**Root Cause:** Missing lifecycle management. When LibraryView is destroyed or replaced, these event handlers remain registered, causing:
1. Memory leaks (view instance cannot be garbage collected)
2. Orphaned callbacks triggering on destroyed views
3. Multiple handlers firing if view is recreated
4. Potential crashes when accessing deallocated widgets

**Recommendation:**
```python
def cleanup(self):
    """Clean up resources and unsubscribe from events"""
    try:
        from fichero.shared.navigation.navigation_event_bus import unsubscribe_from_navigation

        # Unsubscribe from all events
        unsubscribe_from_navigation("collection_added", self._on_collection_added_event)
        unsubscribe_from_navigation("collection_deleted", self._on_collection_deleted_event)
        unsubscribe_from_navigation("collection_updated", self._on_collection_updated_event)
        unsubscribe_from_navigation("folder_import_started", self._on_folder_import_started_event)
        unsubscribe_from_navigation("folder_import_progress", self._on_folder_import_progress_event)
        unsubscribe_from_navigation("folder_import_completed", self._on_folder_import_completed_event)

        # Clean up toolbar coordinator
        if hasattr(self, 'coordinator') and self.coordinator:
            # Unregister from navigation controller
            if hasattr(self.app, 'view_integration'):
                nav = self.app.view_integration.navigation_controller
                if nav:
                    nav.unregister_toolbar_coordinator(self.coordinator)

        logger.debug("LibraryView cleanup completed")
    except Exception as e:
        logger.error(f"Failed to cleanup LibraryView: {e}")
```

Call this from MainWindow's `_cleanup_all_cached_views()` method.

---

### P0-2: Race Condition in Async Collection Loading
**Location:** `library_view.py:132-139, 1976-2005`

**Issue:**
```python
# In __init__:
try:
    asyncio.create_task(self._load_collections_async())
except RuntimeError:
    threading.Thread(target=self._load_collections_sync, daemon=True).start()
```

**Problem:** Multiple race conditions:
1. `_load_collections_async()` modifies `self.collections` without thread safety
2. `_load_collections_sync()` creates a new event loop in a background thread
3. Both methods call `_create_content()` which manipulates Toga widgets (not thread-safe!)
4. No guarantee about when collections will be loaded vs when `show()` is called

**Root Cause:** Mixing async/sync loading without proper synchronization. Toga widgets MUST be manipulated on the main thread only.

**Evidence of UI Thread Safety Violations:**
```python
# _load_collections_async (line 1998)
self._create_content()  # ❌ Called from async context - may not be on main thread

# _load_collections_sync (line 2031-2032)
# We'll skip UI update here and let it happen when the view is shown
# ❌ Comment acknowledges the problem but doesn't fix it properly
```

**Recommendation:**
```python
async def _load_collections_async(self):
    """Load collections asynchronously and update UI safely"""
    try:
        if self.library_service:
            sort_by = "name"
            all_collections = await self.library_service.get_collections_for_ui(sort_by=sort_by)

            # Store data
            self.collections = all_collections
            if not self.sort_ascending:
                self.collections.reverse()

            logger.debug(f"Loaded {len(self.collections)} collections")

            # Schedule UI update on main thread
            self.app.add_background_task(self._create_content)
        else:
            logger.warning("Library service not initialized")
            self.collections = []
    except Exception as e:
        logger.error(f"Failed to load collections: {e}")
        self.collections = []
```

And remove the threading fallback entirely - it's dangerous.

---

### P0-3: Excessive Widget Recreation on Every Update
**Location:** `library_view.py:278-340`

**Issue:**
```python
# ALWAYS recreate - Toga widgets don't properly update when data changes via set_data()
logger.info(f"🔄 Library: Recreating ListWidget with {len(collection_data)} collections")
self._recreate_detailed_list(collection_data)
```

**Problem:** Every time collections are updated (add, delete, rename, import progress), the entire `ListWidget` is destroyed and recreated. This happens:
- On initial load
- On every collection add/delete/update event (6 event types!)
- On sort toggle
- On force refresh
- On show() if collections exist (line 178)

**Performance Impact:**
- Destroying and recreating Toga widgets is expensive (native bridge overhead)
- Loses scroll position
- Loses focus state
- Causes visible flicker
- O(n) memory allocations for every update

**Root Cause:** Comment suggests Toga's `set_data()` doesn't work properly, but this workaround is excessive.

**Recommendation:**
Implement smarter update strategy:
```python
def _update_collections_display(self, force_recreate=False):
    """Update collections display with minimal widget recreation"""
    try:
        # Only recreate if:
        # 1. Widget doesn't exist yet
        # 2. Collection count changed significantly (add/remove)
        # 3. force_recreate flag is set
        needs_recreate = (
            not hasattr(self, 'collections_list') or
            not self.collections_list or
            force_recreate
        )

        # For count changes, compare lengths
        if hasattr(self, '_last_collection_count'):
            if len(self.collections) != self._last_collection_count:
                needs_recreate = True

        if needs_recreate:
            self._recreate_detailed_list(collection_data)
            self._last_collection_count = len(self.collections)
        else:
            # Try to update in place (if Toga supports it)
            # Otherwise, skip update (changes will appear on next navigation)
            logger.debug("Skipping widget recreation - using cached view")
    except Exception as e:
        logger.error(f"Failed to update collections display: {e}")
```

---

### P0-4: Recursion Guard Implementation is Incomplete
**Location:** `library_view.py:158-187`

**Issue:**
```python
def show(self):
    """Called when view becomes active - refresh DetailedList to clear cached selections"""
    if self._showing:
        logger.warning("⏭️ Recursion detected in LibraryView.show() - preventing recursive call")
        return

    self._showing = True
    try:
        # ... work ...
        if self.collections:
            self._create_collections_display()  # ❌ Can call show() indirectly!
    finally:
        self._showing = False
```

**Problem:**
1. Recursion guard is cleared in `finally` block, but `_create_collections_display()` might trigger callbacks that call `show()` again
2. No similar guards on other entry points like `_on_collection_selected()`
3. The warning suggests this IS happening in practice (hence the guard)

**Root Cause:** Circular dependencies between view lifecycle and callbacks. The fact that a guard was needed indicates a design flaw.

**Recommendation:**
1. Add recursion guards to all entry points
2. Investigate WHY `show()` is being called recursively (fix root cause)
3. Add telemetry to detect recursion in production:

```python
def show(self):
    """Called when view becomes active"""
    if self._showing:
        logger.error("RECURSION DETECTED in LibraryView.show()")
        import traceback
        logger.error(f"Call stack:\n{''.join(traceback.format_stack())}")
        # Don't just suppress - report this as a bug
        if hasattr(self.app, 'error_reporter'):
            self.app.error_reporter.report_recursion('LibraryView.show')
        return

    self._showing = True
    try:
        # Existing code...
    finally:
        self._showing = False
```

---

### P0-5: Main Window Integration - Cached View Never Cleaned Up
**Location:** `main_window.py:61, 705-720, 1223-1237`

**Issue:**
```python
# main_window.py:61
self.cached_library_view: Optional[LibraryView] = None

# main_window.py:705-708
if self.cached_library_view is None:
    logger.debug("Creating new LibraryView instance")
    self.cached_library_view = LibraryView(self.app, self.is_mobile)
    self.cached_library_view.register_collection_callback(self._on_collection_selected)
```

**Problem:**
1. LibraryView is created once and cached forever
2. `_cleanup_all_cached_views()` exists but only cleans up EXISTING cleanup methods - doesn't null out the reference
3. View persists for entire app lifetime, accumulating event handlers
4. On macOS, window can be closed and reopened - cached view from old window persists

**Code in cleanup:**
```python
# main_window.py:1223-1237
if self.cached_library_view:
    try:
        if hasattr(self.cached_library_view, 'cleanup_callbacks'):
            self.cached_library_view.cleanup_callbacks()  # ❌ This method doesn't exist!
    except Exception as e:
        logger.error(f"Failed to cleanup cached library view: {e}")
```

**Root Cause:** Incomplete cleanup implementation. The cleanup method being called doesn't exist (see P0-1).

**Recommendation:**
```python
def _cleanup_all_cached_views(self):
    """Clean up all cached views to prevent memory leaks"""
    try:
        if self.cached_library_view:
            # Call cleanup if it exists
            if hasattr(self.cached_library_view, 'cleanup'):
                self.cached_library_view.cleanup()
            # Null out reference to allow garbage collection
            self.cached_library_view = None
            logger.debug("Cleaned up cached LibraryView")

        # Same for other cached views
        if self.cached_collection_view:
            if hasattr(self.cached_collection_view, 'cleanup'):
                self.cached_collection_view.cleanup()
            self.cached_collection_view = None

        if self.cached_output_view:
            if hasattr(self.cached_output_view, 'cleanup'):
                self.cached_output_view.cleanup()
            self.cached_output_view = None

        logger.debug("All cached views cleaned up")
    except Exception as e:
        logger.error(f"Failed to cleanup all cached views: {e}")
```

---

### P0-6: Inconsistent Error Handling in Event Handlers
**Location:** Multiple locations

**Issue:** Event handlers have inconsistent error handling patterns:

```python
# Pattern 1: Catch but don't report to user
def _on_collection_added_event(self, event):
    try:
        # ... work ...
    except Exception as e:
        logger.error(f"Failed to handle collection_added event: {e}")
        # ❌ User never knows this failed!

# Pattern 2: Catch and try to show dialog (but might fail)
async def _confirm_and_delete_collection(self, collection_id: str, collection_name: str):
    try:
        # ... work ...
    except Exception as e:
        logger.error(f"Failed to confirm and delete collection: {e}")
        await self.app.main_window.dialog(...)  # ❌ What if dialog fails?

# Pattern 3: No error handling at all (lines with just logger.error)
```

**Problem:**
1. Silent failures leave UI in inconsistent state
2. No way for user to recover from errors
3. Some errors might crash the app if not caught
4. Async errors might be lost entirely

**Recommendation:**
Implement consistent error handling strategy:

```python
class LibraryView(BaseView):
    async def _safe_show_error(self, title: str, message: str):
        """Safely show error dialog to user"""
        try:
            if hasattr(self.app, 'main_window') and self.app.main_window:
                await self.app.main_window.dialog(
                    toga.ErrorDialog(title=title, message=message)
                )
            else:
                # Fallback: log only
                logger.error(f"Cannot show dialog - {title}: {message}")
        except Exception as e:
            logger.error(f"Failed to show error dialog: {e}")

    def _on_collection_added_event(self, event):
        """Handle collection_added event with proper error handling"""
        try:
            collection_name = event.data.get("collection_name", "Unknown")
            logger.info(f"📡 Event received: collection_added - {collection_name}")
            asyncio.create_task(self._load_collections_async())
        except Exception as e:
            logger.error(f"Failed to handle collection_added event: {e}")
            # Show error to user
            asyncio.create_task(
                self._safe_show_error(
                    "Update Failed",
                    f"Failed to refresh collections: {str(e)}"
                )
            )
```

---

### P0-7: Desktop Layout - View Added to Slots But show() Still Called
**Location:** `main_window.py:1316-1325`

**Issue:**
```python
# NOTE: Do NOT call view.show() here when using UniversalLayoutManager
# The layout manager handles view lifecycle management
# Calling show() can cause recursion issues
# if hasattr(view, 'show'):
#     view.show()

logger.debug(f"Desktop view '{view_key}' displayed in '{pane}' pane")
```

**Problem:** Comment says "DO NOT call view.show()" but earlier in the same file:

```python
# main_window.py:695 (_show_initial_view)
else:
    self._show_view_desktop("library", library_view, "left")
```

And in `library_view.py`:
```python
# library_view.py:158-187
def show(self):
    """Called when view becomes active - refresh DetailedList"""
    if self._showing:
        logger.warning("⏭️ Recursion detected")  # ❌ This IS firing!
```

**Root Cause:** Mixed lifecycle management. UniversalLayoutManager handles slot visibility, but something is still calling `show()` on views.

**Recommendation:**
1. Audit all call sites to `show()` and remove manual calls
2. Let layout manager control view lifecycle exclusively
3. Add assertion to detect manual show() calls:

```python
def show(self):
    """Called when view becomes active"""
    # Detect if being called manually vs by layout manager
    import traceback
    stack = traceback.extract_stack()
    caller = stack[-2]

    if 'layout_manager' not in caller.filename:
        logger.warning(f"show() called from {caller.filename}:{caller.lineno} - should only be called by layout_manager")

    # Rest of show() implementation...
```

---

## Major Issues (P1 - Significant Impact)

### P1-1: Toolbar Coordinator Registration Never Cleaned Up
**Location:** `library_view.py:79-84`

**Issue:**
```python
try:
    if hasattr(app, 'view_integration') and hasattr(app.view_integration, 'navigation_controller'):
        app.view_integration.navigation_controller.register_toolbar_coordinator(self.coordinator)
        logger.debug("Registered toolbar coordinator with navigation controller")
except Exception as e:
    logger.warning(f"Could not register toolbar coordinator with navigation controller: {e}")
```

**Problem:** Coordinator is registered but never unregistered. If LibraryView is recreated, coordinator accumulates in navigation controller.

**Impact:** Memory leak, duplicate coordinators, conflicting toolbar updates

**Recommendation:** Add to cleanup method:
```python
if hasattr(self.app, 'view_integration'):
    nav = self.app.view_integration.navigation_controller
    if nav and hasattr(nav, 'unregister_toolbar_coordinator'):
        nav.unregister_toolbar_coordinator(self.coordinator)
```

---

### P1-2: Icon Cache Never Invalidated
**Location:** `library_view.py:48, 243-257`

**Issue:**
```python
self._folder_icon_cache = None  # In __init__

# Later:
if self._folder_icon_cache is not None:
    folder_icon = self._folder_icon_cache
else:
    folder_icon_path = self.app.paths.app / "resources" / "icons" / ...
    folder_icon = toga.Image(str(folder_icon_path))
    self._folder_icon_cache = folder_icon
```

**Problem:** Icon is cached forever. If icon file changes or app theme changes, cached icon is stale.

**Impact:** Icon doesn't update when app resources change (debugging, theme switching)

**Recommendation:**
1. Add cache invalidation method
2. Or better: Let Toga handle icon caching (just load fresh each time - it's already cached internally)

---

### P1-3: Selection State Not Preserved During Refresh
**Location:** `library_view.py:228-237`

**Issue:**
```python
# Store current selection to restore later
current_selection_id = None
if (hasattr(self, 'collections_list') and self.collections_list):
    try:
        selection = self.collections_list.get_selection()
        if selection:
            current_selection_id = selection.collection_data.get('id')
    except:
        pass
```

**Problem:**
1. Selection ID is stored but NEVER RESTORED! Code reads selection but doesn't reapply it after recreation.
2. Bare `except:` catches all exceptions, even KeyboardInterrupt
3. Silent failure - user loses selection with no indication

**Impact:** User experience - selection is lost on every refresh

**Recommendation:**
```python
def _create_collections_detailed_list(self):
    """Create or update detailed list view for collections with selection preservation"""
    try:
        # Store current selection
        current_selection_id = None
        if hasattr(self, 'collections_list') and self.collections_list:
            try:
                selection = self.collections_list.get_selection()
                if selection:
                    current_selection_id = selection.collection_data.get('id')
                    logger.debug(f"Preserving selection: {current_selection_id}")
            except Exception as e:
                logger.debug(f"Could not get current selection: {e}")

        # Format collections...
        # Recreate list...
        self._recreate_detailed_list(collection_data)

        # RESTORE SELECTION
        if current_selection_id and hasattr(self, 'collections_list'):
            try:
                # Find the row with matching ID and select it
                for i, item in enumerate(collection_data):
                    if item.get('id') == current_selection_id:
                        self.collections_list.select_row(i)
                        logger.debug(f"Restored selection: {current_selection_id}")
                        break
            except Exception as e:
                logger.debug(f"Could not restore selection: {e}")

    except Exception as e:
        logger.error(f"Failed to create collections list: {e}")
```

---

### P1-4: Async Task Creation Without Tracking
**Location:** Multiple locations

**Issue:** Code creates async tasks without tracking them:
```python
asyncio.create_task(self._load_collections_async())  # Line 132
asyncio.create_task(self._perform_delete_collection(...))  # Line 376
asyncio.create_task(self._show_rename_dialog(...))  # Line 432
# ... 10+ more instances
```

**Problem:**
1. No way to cancel tasks when view is destroyed
2. Tasks might complete after view is gone (accessing dead widgets)
3. No error handling if task raises exception
4. No way to wait for tasks to complete during shutdown

**Impact:** Potential crashes, resource leaks, unhandled exceptions

**Recommendation:**
```python
class LibraryView(BaseView):
    def __init__(self, ...):
        # ... existing init ...
        self._background_tasks = set()  # Track running tasks

    def _create_task(self, coro):
        """Create and track an async task"""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        # Add error handler
        def _handle_task_error(t):
            try:
                t.result()  # Raises if task failed
            except Exception as e:
                logger.error(f"Background task failed: {e}", exc_info=True)

        task.add_done_callback(_handle_task_error)
        return task

    async def cleanup(self):
        """Clean up resources"""
        # Cancel all running tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()

        # Wait for cancellation
        await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()

        # ... rest of cleanup ...
```

---

### P1-5: No Validation of library_service Before Use
**Location:** Multiple locations

**Issue:**
```python
if self.library_service:
    all_collections = await self.library_service.get_collections_for_ui(...)
```

**Problem:** Code checks `if self.library_service` but:
1. Doesn't validate it has required methods
2. Doesn't handle partial initialization
3. Silently degrades to empty state if service is None

**Impact:** Silent failures, empty UI with no explanation

**Recommendation:**
```python
def _validate_library_service(self):
    """Validate library service is properly initialized"""
    if not self.library_service:
        raise RuntimeError("Library service not initialized")

    # Check required methods exist
    required_methods = [
        'get_collections_for_ui',
        'add_collection_for_ui',
        'delete_collection',
    ]

    for method in required_methods:
        if not hasattr(self.library_service, method):
            raise RuntimeError(f"Library service missing method: {method}")

    return True

async def _load_collections_async(self):
    """Load collections with validation"""
    try:
        self._validate_library_service()
        all_collections = await self.library_service.get_collections_for_ui(...)
        # ... rest of method ...
    except RuntimeError as e:
        logger.error(f"Library service error: {e}")
        # Show error to user
        await self._safe_show_error(
            "Library Not Available",
            "The library system is not properly initialized. Please restart the application."
        )
        self.collections = []
```

---

### P1-6: Import Progress Updates Disabled Due to Performance Issues
**Location:** `library_view.py:3013-3029`

**Issue:**
```python
def _update_collection_subtitle(self, collection_id: str, subtitle: str):
    """Update the subtitle for a collection in the DetailedList"""
    try:
        # DISABLED: Updating subtitles during import causes hundreds of full refreshes
        # and freezes the app. Toga's DetailedList doesn't support partial updates.
        # The subtitle will be correct when the user refreshes or navigates back.

        # Find the collection in our list and update the data (but don't refresh UI)
        for collection in self.collections:
            if collection.get("id") == collection_id:
                collection["subtitle"] = subtitle
                logger.debug(f"Updated subtitle for collection {collection_id}: {subtitle}")
                break

        # DO NOT call self._create_content() here - it causes app freeze during large imports
```

**Problem:**
1. Feature is completely disabled because of performance issues
2. User gets no feedback during long imports
3. Subtitle data is updated in memory but UI never reflects it
4. Root cause (excessive widget recreation) is not addressed

**Impact:** Poor user experience during imports, no progress indication

**Recommendation:**
Fix the root cause (P0-3) instead of disabling the feature. Once selective updates are implemented, re-enable this:

```python
def _update_collection_subtitle(self, collection_id: str, subtitle: str):
    """Update the subtitle for a collection efficiently"""
    try:
        # Update data
        for collection in self.collections:
            if collection.get("id") == collection_id:
                collection["subtitle"] = subtitle
                logger.debug(f"Updated subtitle: {subtitle}")
                break

        # Smart update: Only refresh if not currently importing (avoid UI freeze)
        # Or use rate limiting (max 1 update per second)
        current_time = time.time()
        if not hasattr(self, '_last_subtitle_update'):
            self._last_subtitle_update = 0

        if current_time - self._last_subtitle_update > 1.0:  # Max 1 Hz updates
            self._update_collections_display(force_recreate=False)
            self._last_subtitle_update = current_time
    except Exception as e:
        logger.error(f"Failed to update subtitle: {e}")
```

---

### P1-7: Three Different Selection Handler Methods
**Location:** `library_view.py:690, 797, 806`

**Issue:**
```python
def _on_collection_selected(self, widget):  # Line 690 - Main handler

def _on_collection_selected_fallback(self, widget):  # Line 797 - Fallback

def _on_collection_selected_simple(self, widget):  # Line 806 - Simple handler
```

**Problem:**
1. Three different handlers for same event
2. Fallback and simple handlers are never called (dead code)
3. Confusing which one is actually used
4. Maintenance burden - changes need to be applied to all three?

**Impact:** Code complexity, potential bugs if wrong handler is called

**Recommendation:** Remove unused handlers, consolidate into one:

```python
def _on_collection_selected(self, widget):
    """Handle collection selection (single authoritative handler)"""
    logger.info(f"Collection selected: widget={widget}")

    # Trigger focus ring
    if self.on_click:
        self.on_click()

    try:
        # Extract selection from widget (handle all formats)
        selection = self._extract_selection_from_widget(widget)

        if selection:
            self._handle_selection(selection)
        else:
            self._handle_no_selection()

    except Exception as e:
        logger.error(f"Failed to handle selection: {e}", exc_info=True)
        self._handle_no_selection()

def _extract_selection_from_widget(self, widget):
    """Extract selection data from various widget types"""
    # Consolidate selection extraction logic here
    # ... implementation ...

def _handle_selection(self, selection):
    """Handle valid selection"""
    # ... existing selection handling logic ...

def _handle_no_selection(self):
    """Handle cleared selection"""
    # ... existing clear logic ...
```

---

### P1-8: Complex Tree Selection Wrapper Could Fail Silently
**Location:** `library_view.py:544-687`

**Issue:** 143 lines of complex selection wrapper logic with nested classes:

```python
def _on_tree_select(self, selection):
    """Wrapper for ListWidget selection (Phase 6)"""
    try:
        # Create wrapper classes
        class SelectionWrapper:
            def __init__(self, item_data, collection_map):
                self.collection_data = item_data.get('_collection_data')
                # ... 10 lines of fallback logic ...

        class WidgetWrapper:
            def __init__(self, selection_wrapper):
                self.selection = selection_wrapper

        # Handle Tree Node objects - 20 lines
        # Handle Row objects - 30 lines
        # Handle dict - 20 lines
        # Handle objects with _collection_data - 10 lines

        wrapper = SelectionWrapper(item_data, self._tree_data_map)
        widget_wrapper = WidgetWrapper(wrapper)
        self._on_collection_selected(widget_wrapper)

    except Exception as e:
        logger.error(f"Error in _on_tree_select: {e}", exc_info=True)
        # ❌ Error is logged but selection is lost silently
```

**Problem:**
1. Overly complex with multiple fallback paths
2. Silent failure - exception is caught and logged but user doesn't know selection failed
3. Inner classes created on every selection (memory churn)
4. Multiple lookup strategies (by accessor, by ID, by text) - could mismatch

**Impact:** Selection might fail silently, performance overhead

**Recommendation:**
1. Simplify by using data classes instead of inner classes
2. Add user-facing error handling
3. Cache wrapper classes:

```python
from dataclasses import dataclass

@dataclass
class CollectionSelection:
    collection_data: dict
    item_id: str

def _on_tree_select(self, selection):
    """Handle tree selection with clear error reporting"""
    try:
        if selection is None:
            self._on_collection_selected(None)
            return

        # Extract data based on selection type
        collection_data = self._extract_collection_data(selection)

        if collection_data:
            # Create simple wrapper
            wrapper = type('obj', (object,), {
                'selection': type('obj', (object,), {
                    'collection_data': collection_data
                })
            })()

            self._on_collection_selected(wrapper)
        else:
            # Clear selection
            logger.warning(f"Could not extract collection data from selection: {type(selection)}")
            self._on_collection_selected(None)

            # Show error to user
            asyncio.create_task(
                self._safe_show_error(
                    "Selection Error",
                    "Could not select collection. Please try again."
                )
            )

    except Exception as e:
        logger.error(f"Selection failed: {e}", exc_info=True)
        self._on_collection_selected(None)
```

---

### P1-9: Daemon Threads Created Without Tracking
**Location:** `library_view.py:138`

**Issue:**
```python
except RuntimeError:
    # No event loop running, use thread-safe approach
    threading.Thread(target=self._load_collections_sync, daemon=True).start()
```

**Problem:**
1. Daemon thread created without reference - can't be stopped
2. Thread might outlive the view
3. Thread creates new event loop (memory leak)
4. No error handling if thread crashes

**Impact:** Resource leaks, potential crashes

**Recommendation:**
Don't use threading at all. If event loop isn't running, defer loading:

```python
# In __init__:
try:
    loop = asyncio.get_running_loop()
    asyncio.create_task(self._load_collections_async())
except RuntimeError:
    # No event loop yet - defer loading until show()
    logger.debug("No event loop - deferring collection load until show()")
    self._needs_initial_load = True

# In show():
def show(self):
    if getattr(self, '_needs_initial_load', False):
        self._needs_initial_load = False
        asyncio.create_task(self._load_collections_async())
    # ... rest of show() ...
```

---

### P1-10: Collection Deletion Has Two Different Code Paths
**Location:** `library_view.py:365-380, 484-531`

**Issue:** Two separate deletion flows:

```python
# Path 1: Swipe delete (mobile) - no confirmation
def _on_swipe_delete_collection(self, widget, row):
    asyncio.create_task(self._perform_delete_collection(collection_id, collection_name))

# Path 2: Command delete (desktop) - with confirmation
def _on_delete_collection(self, widget, item=None):
    asyncio.create_task(self._confirm_and_delete_collection(collection_id, collection_name))
```

**Problem:**
1. Inconsistent behavior between platforms
2. Mobile has no confirmation (easy to accidentally delete)
3. Two code paths to maintain
4. HIG violation - iOS should also confirm destructive actions

**Impact:** Data loss risk, inconsistent UX

**Recommendation:**
Always confirm destructive actions:

```python
def _on_swipe_delete_collection(self, widget, row):
    """Handle swipe delete - show confirmation first"""
    try:
        if hasattr(row, 'collection_data'):
            collection = row.collection_data
            collection_id = collection.get('id', '')
            collection_name = collection.get('name', 'Unknown')

            # Always confirm, even on swipe
            asyncio.create_task(
                self._confirm_and_delete_collection(collection_id, collection_name)
            )
    except Exception as e:
        logger.error(f"Failed to handle swipe delete: {e}")

def _on_delete_collection(self, widget, item=None):
    """Handle delete command - unified with swipe"""
    if not self.selected_collection:
        return

    collection_id = self.selected_collection.get('id', '')
    collection_name = self.selected_collection.get('name', '')

    asyncio.create_task(
        self._confirm_and_delete_collection(collection_id, collection_name)
    )
```

---

### P1-11: Multiple Methods Have Magic Strings for View IDs
**Location:** Multiple locations

**Issue:**
```python
self.view_id = "library"  # Line 35
self.app.selection_manager.set_selection(view_id='library', ...)  # Line 725
coordinator.set_active_view('library')  # Line 172
context={'view_id': 'library'}  # Line 2063
```

**Problem:** View ID repeated as string literal in ~10 places. If ID changes, all must be updated.

**Impact:** Refactoring hazard, typo risk

**Recommendation:**
Define as constant:

```python
class LibraryView(BaseView):
    VIEW_ID = 'library'  # Class constant

    def __init__(self, ...):
        self.view_id = self.VIEW_ID
        # ... rest of init ...

    def show(self):
        self.coordinator.set_active_view(self.VIEW_ID)
        # ... etc ...
```

---

### P1-12: Main Window's _on_show_library Clears Output View
**Location:** `main_window.py:832-834`

**Issue:**
```python
# Clear output view when navigating to library (no file selected)
if hasattr(self, 'cached_output_view') and self.cached_output_view:
    logger.info("📤 Clearing output view (navigating to library)")
    self.cached_output_view.load_output()  # ❌ Clears without checking if preview is visible
```

**Problem:**
1. Clears preview even if user still wants it visible
2. Doesn't check if preview pane is actually showing
3. No way to navigate library while keeping preview open (common workflow)

**Impact:** User workflow disruption - can't browse library while viewing a file

**Recommendation:**
Only clear preview if preview pane is hidden OR user explicitly deselected:

```python
def _on_show_library(self, event):
    """Handle show library event"""
    try:
        # Check if this is an explicit deselection vs navigation
        deselect = event.data.get('deselect', False) if hasattr(event, 'data') else False

        # Only clear preview if explicitly deselecting or preview pane is hidden
        preview_visible = self._is_preview_pane_visible()

        if deselect or not preview_visible:
            if hasattr(self, 'cached_output_view') and self.cached_output_view:
                logger.info("📤 Clearing output view")
                self.cached_output_view.load_output()

        # ... rest of method ...
```

---

## Minor Issues (P2 - Polish/Optimization)

### P2-1: Excessive Debug Logging with Print Statements
**Location:** `library_view.py:31-155`

**Issue:** __init__ has 15+ print statements plus logger calls:

```python
print(f"🔧 LibraryView.__init__ starting...")  # Line 31
logger.debug(f"LibraryView.__init__ called...")  # Line 32
print("🔧 Setting initial attributes...")  # Line 38
# ... 12 more print statements ...
```

**Problem:**
1. Print statements bypass logging system
2. No control over verbosity
3. Emoji usage inconsistent
4. Performance overhead

**Recommendation:** Remove all print statements, use logger only with appropriate levels:

```python
logger.debug("LibraryView initialization started")
logger.debug("Setting initial attributes")
# ... etc ...
logger.info("LibraryView initialization complete")
```

---

### P2-2: Unused Callback Attributes
**Location:** Multiple locations

**Issue:** Callbacks defined but never used:

```python
# library_view.py:929-933
if self.bottom_toolbar:
    self.bottom_toolbar.on_activity_monitor = self._on_activity_monitor  # ❌ Method doesn't exist
    self.bottom_toolbar.on_library_settings = self._on_library_settings  # ❌ Method doesn't exist
    self.bottom_toolbar.on_global_inbox = self._on_global_inbox  # ❌ Method doesn't exist
    self.bottom_toolbar.on_tags = self._on_tags  # ❌ Method doesn't exist
```

**Problem:** References to methods that don't exist. Code will crash if toolbar calls these.

**Recommendation:** Either implement the methods or remove the assignments.

---

### P2-3: Inconsistent Docstring Format
**Location:** Throughout file

**Issue:** Mix of docstring formats:

```python
def show(self):
    """Called when view becomes active - refresh DetailedList to clear cached selections"""

def _create_content(self):
    """Create the library view content"""

def _on_tree_select(self, selection):
    """
    Wrapper for ListWidget selection (Phase 6).

    Converts ListWidget selection format to the format expected by
    _on_collection_selected.
    """
```

**Problem:** Inconsistent (single line vs multi-line, with/without details)

**Recommendation:** Use consistent Google-style docstrings:

```python
def show(self):
    """Show the library view and refresh display.

    Called when view becomes active. Refreshes the collections list
    to clear any cached DetailedList selection state.

    Note: Uses recursion guard to prevent infinite loops.
    """
```

---

### P2-4: Gettext Import Not Always Available
**Location:** Multiple locations

**Issue:**
```python
_("Library")  # Used in many places
_("Delete Collection")  # Used without try/except
```

**Problem:** Code assumes `_()` function is globally available. If gettext isn't installed, will crash.

**Recommendation:**
```python
# At top of file:
try:
    from gettext import gettext as _
except ImportError:
    def _(s): return s  # Fallback for missing gettext
```

---

### P2-5: Hard-Coded Colors
**Location:** Multiple locations

**Issue:**
```python
color="#8E8E93"  # iOS-style secondary text color
```

**Problem:** Hard-coded hex colors don't adapt to dark mode or theme changes

**Recommendation:** Use theme constants or Toga's system colors

---

### P2-6: Method _show_message() Called But Not Defined
**Location:** `library_view.py:832, 837, 857, etc.`

**Issue:**
```python
self._show_message("Selection", "Please select a collection from the list.")
```

**Problem:** Method is called 10+ times but not defined in LibraryView

**Recommendation:** Either implement it or remove calls (likely dead code from refactoring)

---

### P2-7: Empty Placeholder Content Has Fixed Width
**Location:** `library_view.py:883, 897`

**Issue:**
```python
width=150  # Ensure label has minimum width for visibility
```

**Problem:** Hard-coded width doesn't adapt to sidebar size changes

**Recommendation:** Use flex or max-width instead

---

### P2-8: Import Statements Not Organized
**Location:** Top of file

**Issue:** Imports scattered, some in wrong order

**Recommendation:** Organize as: stdlib, third-party, local

---

### P2-9: Type Hints Incomplete
**Location:** Throughout file

**Issue:** Some methods have type hints, others don't:

```python
def __init__(self, app, is_mobile: bool = False):  # ✅ Has types

def show(self):  # ❌ Missing return type
    """Called when view becomes active"""
```

**Recommendation:** Add complete type hints for consistency:

```python
def show(self) -> None:
    """Called when view becomes active"""
```

---

### P2-10: Magic Numbers for Sizes
**Location:** Multiple locations

**Issue:**
```python
margin=(20, 20, 15, 20)  # Magic numbers
width=150
width=200
```

**Recommendation:** Define as named constants

---

### P2-11: Redundant Existence Checks
**Location:** Multiple locations

**Issue:**
```python
if self.content_container:
    self.content_container.add(title)

if self.content_container:  # Checked again 5 lines later
    self.content_container.add(empty_message)
```

**Recommendation:** Check once at start of method

---

### P2-12: Comment Says Feature Was Removed But Code Remains
**Location:** `library_view.py:2091-2099`

**Issue:**
```python
# REMOVED: Parallel non-declarative system methods
# - _create_add_context_once() - Created action dicts...
# - _clear_add_context() - Cleared parallel system...
```

**Problem:** Comment says "REMOVED" but methods might still exist

**Recommendation:** Remove completely or update comment to "DEPRECATED"

---

### P2-13: Inconsistent Naming - "collection" vs "Collection"
**Location:** Throughout file

**Issue:** Variable names mix capitalization:

```python
selected_collection  # lowercase
collection_data  # lowercase
collection_name  # lowercase
```

But class name is `CollectionView` (titlecase)

**Recommendation:** Maintain consistent naming convention

---

### P2-14: Try/Except Blocks Too Broad
**Location:** Multiple locations

**Issue:**
```python
try:
    # 50 lines of code
except Exception as e:
    logger.error(f"Failed to X: {e}")
```

**Problem:** Catches too many operations, hard to debug which line failed

**Recommendation:** Narrow exception scope or add more specific handlers

---

### P2-15: No Metrics/Telemetry for Performance Issues
**Location:** Throughout file

**Issue:** Comments indicate performance problems but no metrics:

```python
# DISABLED: Updating subtitles causes hundreds of full refreshes and freezes
```

**Recommendation:** Add performance telemetry:

```python
import time

def _recreate_detailed_list(self, data):
    start_time = time.time()
    try:
        # ... existing code ...
    finally:
        duration = time.time() - start_time
        if duration > 0.5:  # Log slow operations
            logger.warning(f"Slow list recreation: {duration:.2f}s for {len(data)} items")
```

---

## Code Quality Observations

### Positive Patterns

1. **Event-driven architecture**: Good use of event bus for decoupling
2. **Service layer integration**: Clean separation with library_service
3. **Platform awareness**: Proper mobile vs desktop handling
4. **Composition over inheritance**: Good use of BaseView and mixins
5. **Recursion detection**: Proactive prevention of infinite loops (line 162)
6. **Cache optimization**: Icon caching shows performance awareness (line 243)

### Anti-Patterns Detected

1. **God class**: LibraryView is 3031 lines - should be split
2. **Excessive widget recreation**: Full rebuild on every update
3. **Missing cleanup**: No lifecycle management for resources
4. **Silent failures**: Many error handlers that don't inform users
5. **Dead code**: Multiple unused methods and handlers
6. **Mixed sync/async**: Dangerous threading + asyncio combination
7. **State leakage**: Callbacks registered globally, never cleaned up
8. **Magic strings**: View IDs, event names scattered everywhere

### Architectural Concerns

1. **Tight coupling**: LibraryView depends on MainWindow, NavigationController, SelectionManager, ToolbarCoordinator, LibraryService
2. **Circular dependencies**: MainWindow ↔ LibraryView callbacks
3. **No interface contracts**: No ABC or Protocol for dependencies
4. **Global state**: Event bus subscriptions are global, not scoped
5. **Testing difficulty**: Massive init method, many side effects

---

## Recommendations Summary

### Immediate Actions (P0)

1. ✅ Implement `cleanup()` method with event unsubscription
2. ✅ Fix async/threading race conditions - remove threading entirely
3. ✅ Implement smarter widget update strategy (avoid full recreation)
4. ✅ Fix recursion guard and investigate root cause
5. ✅ Fix MainWindow cleanup to null out cached views
6. ✅ Implement consistent error handling with user feedback
7. ✅ Remove manual `show()` calls, let layout manager control lifecycle

### High Priority (P1)

1. ✅ Track and cancel async tasks on cleanup
2. ✅ Validate library_service before use
3. ✅ Fix selection preservation during refresh
4. ✅ Re-enable import progress updates (after fixing P0-3)
5. ✅ Consolidate selection handlers (remove dead code)
6. ✅ Simplify tree selection wrapper
7. ✅ Add confirmation to mobile deletion
8. ✅ Use constants for view IDs

### Medium Priority (P2)

1. ✅ Remove print statements, use logger only
2. ✅ Clean up unused callbacks and dead code
3. ✅ Standardize docstrings
4. ✅ Add complete type hints
5. ✅ Use named constants instead of magic numbers
6. ✅ Add performance telemetry
7. ✅ Organize imports properly

### Long-term Refactoring

1. **Split LibraryView**: Extract to multiple classes (3000+ lines is too large)
   - `LibraryViewController` (coordination)
   - `LibraryListView` (widget management)
   - `LibraryCommands` (command handlers)
   - `LibraryEventHandler` (event subscriptions)

2. **Interface contracts**: Define protocols for dependencies
   ```python
   class LibraryServiceProtocol(Protocol):
       async def get_collections_for_ui(self, sort_by: str) -> List[Dict]: ...
       async def add_collection_for_ui(self, ...) -> str: ...
   ```

3. **Dependency injection**: Pass dependencies explicitly instead of accessing `self.app`
   ```python
   def __init__(
       self,
       app,
       library_service: LibraryServiceProtocol,
       selection_manager: SelectionManager,
       navigation_controller: NavigationController,
       is_mobile: bool = False
   ):
   ```

4. **State machine**: Formal state management for view lifecycle
   ```python
   class LibraryViewState(Enum):
       INITIALIZING = 'initializing'
       LOADING = 'loading'
       READY = 'ready'
       SHOWING = 'showing'
       REFRESHING = 'refreshing'
       CLEANUP = 'cleanup'
   ```

5. **Testing**: Add unit tests for:
   - Selection handling (all code paths)
   - Event handling (all 6 event types)
   - Async operations (with mocked service)
   - Widget lifecycle (creation, update, destruction)
   - Error handling (network failures, missing service, etc.)

---

## Conclusion

The LibraryView implementation demonstrates good architectural awareness with its use of composition, event-driven patterns, and platform-specific handling. However, several critical issues around resource cleanup, widget lifecycle management, and async/threading safety need immediate attention.

The most impactful fixes would be:
1. Implementing proper cleanup to prevent memory leaks
2. Fixing the excessive widget recreation pattern
3. Removing threading and using async properly
4. Adding user-facing error handling

These changes would significantly improve stability, performance, and user experience.

---

**End of Review**
