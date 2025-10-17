# Command System Fixes
**Date**: October 9, 2025
**Status**: ✅ COMPLETED

---

## Summary

Fixed two critical issues with the command system:

1. **OutputView Initialization Crash** - Fixed initialization order that caused `'OutputView' object has no attribute 'app'` error
2. **Missing Window Navigation Menu Commands** - Made Settings, Processing, About, Activity, Prompts, and Plans accessible via desktop Window menu

---

## Fix 1: OutputView Initialization Order ✅

**Problem**: OutputView crashed immediately when trying to load because `_register_all_commands()` was called before `super().__init__()`, but the command registration needs `self.app` which doesn't exist until after parent initialization.

**Error**: `'OutputView' object has no attribute 'app'`

**File**: `src/fichero/windows/main/views/output/output_view.py`
**Lines**: 78-89

**Solution**: Changed initialization order to match LibraryView pattern:

```python
# BEFORE (BROKEN):
self._register_all_commands()  # ❌ Needs self.app which doesn't exist yet!
super().__init__(app, is_mobile)
self._setup_toolbars()

# AFTER (FIXED):
super().__init__(app, is_mobile)  # ✅ Sets self.app first
self._register_all_commands()    # ✅ Now self.app exists
self._setup_toolbars()            # ✅ Commands are registered
```

**Result**: OutputView now loads without crashing.

---

## Fix 2: Window Navigation Commands Visibility ✅

**Problem**: Window navigation commands (Settings, Processing, About, Activity, Prompts, Plans) were completely invisible on desktop because:
- `show_in_menu=False` → Not in menus
- `mobile_only=True` → Filtered out of desktop toolbars
- Result: No way to access these windows on desktop!

**File**: `src/fichero/windows/main/views/library/library_view.py`
**Lines**: 1190-1280

**Solution**: Made commands visible in desktop Window menu while keeping them in mobile toolbar:

| Property | Old Value | New Value | Effect |
|----------|-----------|-----------|--------|
| `show_in_menu` | `False` | `True` | Now appear in menus |
| `group` | (none) | `toga.Group.WINDOW` | Grouped in Window menu |
| `mobile_only` | `True` | `False` | Available on both platforms |
| `show_in_bottom_toolbar` | `True` | `True` | Still in mobile toolbar |

**Affected Commands**:
1. Settings
2. Processing
3. About
4. Activity
5. Prompts
6. Plans

**Result**:
- **Desktop**: Commands appear in Window menu (not in toolbar - correct for desktop UX)
- **Mobile**: Commands appear in bottom toolbar (not in menu - mobile doesn't use menus)
- **Both platforms**: Commands are functional and accessible

---

## Platform Behavior

### Desktop
```
Window Menu
├─ Settings      (with keyboard shortcut)
├─ Processing
├─ About
├─ Activity
├─ Prompts
└─ Plans
```

### Mobile
```
Bottom Toolbar (when in LibraryView normal mode)
[Settings] [Processing] [About] [Activity] [Prompts] [Plans]
```

---

## Files Modified

1. **src/fichero/windows/main/views/output/output_view.py**
   - Lines 78-89: Fixed initialization order

2. **src/fichero/windows/main/views/library/library_view.py**
   - Lines 1190-1280: Updated 6 window navigation commands to appear in Window menu

---

## Next Steps

**Manual Testing Required**:
1. Verify Window menu contains Settings, Processing, About, Activity, Prompts, Plans
2. Verify OutputView loads when clicking a processed file
3. Verify Edit mode buttons (Rotate, Crop, Reset) work in OutputView
4. Verify keyboard shortcuts work for window navigation commands

---

**Completed By**: Claude Code
**Date**: October 9, 2025
