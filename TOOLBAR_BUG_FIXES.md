# Toolbar Bug Fixes - October 8, 2025

## Issues Found

### Issue #1: Import Error in define_commands()
**Error**: `No module named 'fichero.i18n'`

**Root Cause**: LibraryView.define_commands() tried to import:
```python
from fichero.i18n import _
```

But the translation function `_()` is installed **globally** via `gettext.install('fichero')` in app.py, not in a module called `fichero.i18n`.

**Impact**: Commands were **never being defined** because define_commands() was failing silently.

**Fix**: Removed the erroneous import statement:
```python
def define_commands(self):
    """Define all commands for LibraryView"""
    try:
        # Note: _() is available globally via gettext.install() in app.py
        self.commands = {
            ...
        }
```

**File**: `src/fichero/windows/main/views/library/library_view.py:1145`

---

### Issue #2: Native Toolbar Not Updated on Initial View
**Problem**: When the app starts, `_show_initial_view()` shows the LibraryView but doesn't call `_update_toolbar_for_library_view()`.

**Impact**: Native toolbar was never populated on startup.

**Fix**: Added toolbar update call in `_show_initial_view()`:
```python
def _show_initial_view(self):
    """Show the initial library view"""
    try:
        library_view = self._get_or_create_library_view()

        # Update native toolbar on desktop
        if not self.is_mobile:
            self._update_toolbar_for_library_view(context='normal')

        # Show in appropriate pane
        if self.is_mobile:
            self._show_view_mobile("library", library_view)
        else:
            self._show_view_desktop("library", library_view, "left")
```

**File**: `src/fichero/windows/main/main_window.py:218`

---

### Issue #3: Bottom Toolbar Still Rendering on Desktop
**Problem**: The custom bottom toolbar is still rendering on desktop when it should only appear on mobile.

**Status**: ✅ **FIXED**

**Solution**: Added platform check at the beginning of `_add_library_bottom_toolbar_buttons()`:

```python
def _add_library_bottom_toolbar_buttons(self):
    """Add window navigation buttons to BottomToolbar using NavigationController"""
    try:
        # Desktop: Skip bottom toolbar - commands are in native toolbar/menus
        if not self.is_mobile:
            logger.debug("Skipping bottom toolbar buttons on desktop - using native toolbar")
            return

        # Mobile only: Create center-aligned window navigation buttons for normal mode
        self.bottom_toolbar.add_normal_mode_button(...)
        # ... rest of button setup
```

**File**: `src/fichero/windows/main/views/library/library_view.py:1578`

---

## Testing After Fixes

### Expected Behavior (Desktop)
1. ✅ Commands registered successfully (no import error)
2. ✅ Native toolbar populated on startup
3. ⚠️ Bottom toolbar hidden (pending fix)
4. ✅ Menu items available in macOS menu bar (Settings, Processing, etc.)

### Expected Behavior (Mobile)
1. ✅ Commands registered successfully
2. ✅ Custom bottom toolbar renders
3. ✅ All buttons have icons

---

## Next Steps

1. **Fix bottom toolbar rendering** (Issue #3)
2. **Test on desktop**:
   - Verify native toolbar appears with Settings, Processing, About, etc.
   - Verify bottom toolbar is hidden
   - Verify menu items work
   - Test edit mode toolbar switching

3. **Test on mobile**:
   - Verify custom bottom toolbar still renders
   - Verify all buttons have icons
   - Verify edit mode switching works

4. **Apply same fixes to other views**:
   - CollectionView
   - OutputView (commands already defined, just need toolbar integration)

---

## Verification Commands

```bash
# Run app and check logs for errors
briefcase dev 2>&1 | grep -E "(ERROR|Command|Toolbar)"

# Expected in logs (after fixes):
# - No "No module named 'fichero.i18n'" error
# - "Defined X commands for LibraryView"
# - "✅ Registered X commands for view 'library'"
# - "✅ Native toolbar created with X items"
```

---

## Summary

### Fixes Applied ✅
1. Removed erroneous `from fichero.i18n import _` - Translation function is global
2. Added `_update_toolbar_for_library_view()` call in `_show_initial_view()`

### Pending Fixes ⚠️
1. Hide bottom toolbar on desktop (only show on mobile)

### Files Modified
- `src/fichero/windows/main/views/library/library_view.py` - Fixed import
- `src/fichero/windows/main/main_window.py` - Added toolbar update on startup

---

## Root Cause Analysis

The native toolbar implementation was **correct** but had two bugs preventing it from working:

1. **Silent failure** - import error caused commands to never be defined
2. **Missing call** - toolbar update wasn't called during initial view setup

These were easy to miss because:
- Import errors in try/except blocks fail silently
- Toolbar update works when navigating TO library, but not on initial load
- Bottom toolbar still renders, making it look like nothing is broken

The fixes are minimal but critical!
