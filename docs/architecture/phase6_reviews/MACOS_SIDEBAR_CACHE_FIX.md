# MacOS Sidebar Renderer Cache Fix

**Date:** November 15, 2025
**Component:** ListWidget MacOS Sidebar Renderer
**Issue:** Objective-C class registration warning

## Problem

When the library view was refreshed or recreated multiple times, the following warning appeared:

```
WARNING:fichero.shared.widgets.list_widget.base:Failed to create MacOSSidebarRenderer:
An Objective-C class named b'SidebarItem' already exists. Falling back to Canvas SidebarRenderer
```

## Root Cause

The `_create_sidebar_classes()` function in `macos_sidebar.py` was creating the Objective-C classes (`SidebarItem` and `TogaSidebar`) every time it was called.

Rubicon-ObjC registers these classes globally in the Objective-C runtime. Once registered, attempting to define a class with the same name again causes an error.

The function was called every time a `MacOSSidebarRenderer` was instantiated, which happened whenever:
- The library view was refreshed
- Collections were added/deleted
- The view was recreated for any reason

## Solution

Implemented a simple cache to ensure classes are created only once:

### Changes Made

**File:** `src/fichero/shared/widgets/list_widget/renderers/macos_sidebar.py`

**Added module-level cache:**
```python
# Cache for sidebar classes (created once, reused)
_sidebar_classes_cache = None
```

**Updated function to use cache:**
```python
def _create_sidebar_classes():
    """Create sidebar classes after ObjC classes are loaded (cached after first call)."""
    global _sidebar_classes_cache

    # Return cached classes if already created
    if _sidebar_classes_cache is not None:
        return _sidebar_classes_cache

    if not RUBICON_AVAILABLE:
        _sidebar_classes_cache = (None, None)
        return None, None

    _load_objc_classes()

    # ... class definitions ...

    # Cache the classes for reuse
    _sidebar_classes_cache = (SidebarItem, TogaSidebar)
    return SidebarItem, TogaSidebar
```

## Impact

### Before
- ⚠️ Warning logged on every library refresh
- ⚠️ Fell back to Canvas renderer after first creation
- ⚠️ Inconsistent rendering (native first time, canvas after)
- ⚠️ Memory inefficiency (multiple class registrations attempted)

### After
- ✅ No warnings
- ✅ Consistent native rendering
- ✅ Classes created once and reused
- ✅ Better performance (no repeated class creation)

## Testing

**Verified scenarios:**
1. ✅ Initial load creates classes
2. ✅ Subsequent refreshes reuse cached classes
3. ✅ Delete/add collections works without warnings
4. ✅ Native sidebar rendering remains active

**No regressions:**
- ✅ Selection handling still works
- ✅ Icon rendering unaffected
- ✅ Callbacks function correctly

## Technical Notes

- The cache is at module level, persists for app lifetime
- Thread-safe (Python GIL protects module-level assignments)
- No memory leak (just two class references)
- Compatible with Rubicon-ObjC patterns

## Related Issues

This fix complements the library view improvements:
- Empty sidebar display
- Inbox collection creation
- Widget update optimization

Together, these changes ensure stable, consistent sidebar rendering throughout the app lifecycle.
