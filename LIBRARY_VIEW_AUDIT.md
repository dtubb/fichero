# LibraryView Audit - Platform-Adaptive Toolbar Implementation

**Date**: October 8, 2025
**Status**: ⚠️ HYBRID APPROACH - Needs Migration

## Current State

### ✅ What's Working

1. **Commands are Defined** (lines 1145-1300)
   - LibraryView has comprehensive FicheroCommand definitions
   - 12 commands total:
     - Top Toolbar: Edit button
     - Normal Mode (6): Settings, Processing, About, Activity, Prompts, Plans
     - Edit Mode (5): Export, Bulk Import, Import URLs, Import Files, Import Folder

2. **Commands are Registered**
   - Using ViewCommandMixin
   - Calls `define_commands()` and `register_commands()` in `__init__`

3. **Platform-Specific Icons**
   - Commands use `icon='...' if self.is_mobile else None`
   - Correctly provides icons only for mobile

4. **Context-Aware Commands**
   - Normal mode commands have `context='normal'` (default)
   - Edit mode commands have `context='edit'`

### ❌ What's Broken

1. **Manual Button Creation** (line 344-407)
   - `_add_library_bottom_toolbar_buttons()` manually creates buttons
   - Calls `bottom_toolbar.add_normal_mode_button()` 6 times
   - This bypasses the command system entirely!

2. **Duplicate Button Logic**
   - Commands are defined but not used for toolbar population
   - Button creation logic is duplicated in two places:
     1. Command definitions (metadata)
     2. Manual button creation (actual UI)

3. **Not Platform-Adaptive**
   - Bottom toolbar buttons are manually added regardless of platform
   - Should be handled by BaseView.set_toolbars()

### 🔧 What Needs to Change

## Migration Plan

### Step 1: Update Command Definitions
Commands need `show_in_bottom_toolbar` flags (already using deprecated `show_in_toolbar`):

```python
'settings': FicheroCommand(
    id=f'{self.view_id}.settings',
    label=_("Settings"),
    action=self._on_open_settings_window,
    icon='resources/icons/toolbar/settings.png' if self.is_mobile else None,
    description=_("Open settings window"),
    show_in_menu=False,
    show_in_bottom_toolbar=True,  # NEW FLAG
    toolbar_position='center',
    desktop_only=False
),
```

### Step 2: Remove Manual Button Creation
Delete or comment out `_add_library_bottom_toolbar_buttons()` entirely:

```python
# BEFORE (line 91):
self._add_library_bottom_toolbar_buttons()

# AFTER:
# Buttons auto-populated by BaseView.set_toolbars()
```

### Step 3: Let BaseView Handle Population
BaseView.set_toolbars() now auto-populates:

```python
# In LibraryView.__init__ (line 93):
self.set_toolbars(self.top_toolbar, self.bottom_toolbar)
# ✅ This now calls bottom_toolbar.populate_from_commands() automatically!
```

## Expected Behavior After Migration

### Desktop
- ✅ No bottom toolbar rendered
- ✅ Commands appear in native window.toolbar (via MainWindow)
- ✅ Settings, Processing, About, etc. available in menu/toolbar

### Mobile
- ✅ Bottom toolbar renders with 6 buttons
- ✅ Auto-populated from commands (context='normal')
- ✅ Edit mode switches to 5 edit buttons (context='edit')

## Files to Modify

1. **`library_view.py`** (line 1145-1300)
   - Update all commands to use `show_in_bottom_toolbar=True`
   - Remove `show_in_toolbar` (deprecated)

2. **`library_view.py`** (line 91)
   - Remove call to `_add_library_bottom_toolbar_buttons()`

3. **`library_view.py`** (line 344-407)
   - Delete entire `_add_library_bottom_toolbar_buttons()` method

## Implementation Status

- [x] FicheroCommand enhanced with `show_in_top_toolbar` and `show_in_bottom_toolbar`
- [x] BaseToolbar.add_button_from_command() implemented
- [x] BaseToolbar.populate_from_commands() updated to use add_button_from_command()
- [x] BaseView.set_toolbars() made platform-adaptive
- [ ] LibraryView commands updated with new flags
- [ ] LibraryView manual button creation removed
- [ ] Testing on desktop and mobile

## Notes

- Edit mode buttons are created dynamically via `_create_add_context_once()` (line 244)
- This is correct! Edit mode uses ToolbarCoordinator for dynamic context
- Normal mode buttons should use command system exclusively

## Next Steps

1. Update LibraryView command definitions
2. Remove manual button creation
3. Test on desktop (verify no bottom toolbar)
4. Test on mobile (verify bottom toolbar renders)
5. Repeat for CollectionView and OutputView
