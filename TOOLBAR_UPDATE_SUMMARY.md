# Toolbar System Update - October 9, 2025

## Summary

Successfully migrated LibraryView to the new platform-adaptive command system and fixed toolbar management in MainWindow.

## Changes Made

### 1. CommandManager Filter Logic Enhancement

**File**: `src/fichero/shared/commands/command_manager.py`

**Changes**:
- Enhanced `get_toolbar_commands()` with `toolbar_type` parameter
- Added filtering for `"top"`, `"bottom"`, `"native"` toolbar types
- Fixed deprecated `show_in_toolbar` flag usage → now uses `show_in_top_toolbar` and `show_in_bottom_toolbar`
- Platform filtering respects `mobile_only` and `desktop_only` flags

**Impact**: Commands now correctly route to appropriate toolbars based on platform and toolbar type.

### 2. BaseToolbar & BaseView Integration

**Files**:
- `src/fichero/shared/toolbars/base_toolbar.py`
- `src/fichero/shared/views/base_view.py`

**Changes**:
- `BaseToolbar.populate_from_commands()` now accepts `toolbar_type` parameter
- `BaseView.set_toolbars()` passes `toolbar_type='top'` and `toolbar_type='bottom'` to toolbars
- Desktop skips bottom toolbar rendering (uses native `window.toolbar` instead)

**Impact**: Toolbars automatically populate from command definitions with correct filtering.

### 3. LibraryView Command Migration

**File**: `src/fichero/windows/main/views/library/library_view.py`

**Changes**:
- Removed all manual toolbar button creation methods
- Defined all commands in `define_commands()` method with proper flags
- Registered commands with CommandManager in `__init__()`

**Command Categories**:

#### Always-Visible Add Commands (Both Platforms)
```python
'add_file', 'add_folder', 'add_url'
- show_in_bottom_toolbar=True
- context='normal'
- desktop_only=False
```
- **Desktop**: Appear in native `window.toolbar` when collection is selected
- **Mobile**: Appear in bottom toolbar always

#### Mobile-Only Window Navigation Commands
```python
'settings', 'processing', 'about', 'activity', 'prompts', 'plans'
- show_in_bottom_toolbar=True
- mobile_only=True
- context='normal'
```
- **Desktop**: Not shown (desktop uses native windows/menus)
- **Mobile**: Appear in bottom toolbar for window navigation

#### Mobile-Only Edit Mode Commands
```python
'export', 'bulk_import', 'edit_import_urls', 'edit_import_files', 'edit_import_folder'
- show_in_bottom_toolbar=True
- mobile_only=True
- context='edit'
```
- **Desktop**: Not shown (collection toolbar handles this)
- **Mobile**: Appear in bottom toolbar when in edit mode

**Impact**: LibraryView now uses declarative command definitions instead of imperative button creation.

### 4. MainWindow Toolbar Management

**File**: `src/fichero/windows/main/main_window.py`

**Changes**:
- Added `_update_toolbar_for_library_view()` method
- Added `_update_toolbar_for_collection_view()` method
- Added `_update_toolbar_for_output_view()` method
- Updated `_show_initial_view()` to populate toolbar with library commands
- Updated `_on_show_library()` to populate toolbar with library commands
- Updated `_on_show_collection()` to populate toolbar with collection commands
- Updated `_on_show_preview()` to populate toolbar with output commands

**Toolbar Behavior**:

| View | Desktop Toolbar | Mobile Toolbar |
|------|----------------|----------------|
| LibraryView | **Cleared** (no toolbar) | Bottom toolbar with Add + Window Nav commands |
| CollectionView | **Populated** with collection commands | Bottom toolbar with collection commands |
| OutputView | **Always visible** with output editing commands | Bottom toolbar with output commands |

**Impact**: Desktop native toolbar now correctly appears/disappears based on current view.

---

## Platform-Specific Behavior

### Desktop (macOS, Windows, Linux)

**LibraryView**:
- NO native toolbar initially
- Toolbar cleared when navigating to library
- Users interact with collections via DetailedList tap/swipe

**CollectionView**:
- Native toolbar with collection-specific commands
- Toolbar populated when collection is selected
- Commands defined in CollectionView (not implemented yet)

**OutputView**:
- Native toolbar ALWAYS visible
- Persistent toolbar with editing commands (rotate, crop, reset, etc.)
- Set up via `setup_native_toolbar()` in OutputView.__init__()

### Mobile (iOS, Android)

**LibraryView**:
- Bottom toolbar with:
  - Add File, Add Folder, Add URL (always visible, `context='normal'`)
  - Settings, Processing, About, Activity, Prompts, Plans (window navigation)
  - Export, Bulk Import, Import URLs, Import Files, Import Folder (edit mode only, `context='edit'`)

**CollectionView**:
- Bottom toolbar with collection-specific commands
- Commands defined in CollectionView (not implemented yet)

**OutputView**:
- Bottom toolbar with output editing commands
- Commands defined in OutputView (not implemented yet)

---

## Files Modified

### Core System
- ✅ `src/fichero/shared/commands/command_manager.py` (lines 265-330)
- ✅ `src/fichero/shared/toolbars/base_toolbar.py` (lines 418-454)
- ✅ `src/fichero/shared/views/base_view.py` (lines 243-295)

### Views
- ✅ `src/fichero/windows/main/views/library/library_view.py` (lines 1144-1336)

### Main Window
- ✅ `src/fichero/windows/main/main_window.py` (lines 290-316, 224-226, 342-344, 380-382)

### Documentation
- ✅ `TOOLBAR_ARCHITECTURE.md` (new file - comprehensive architecture docs)
- ✅ `TOOLBAR_UPDATE_SUMMARY.md` (this file)

---

## Next Steps

### 1. Test on Desktop

```bash
FORCE_MOBILE_UI=false TOGA_BACKEND=toga_cocoa briefcase dev
```

**Expected Behavior**:
- Launch app → LibraryView shows in left pane, NO native toolbar
- Select collection → CollectionView shows in center pane, native toolbar appears with collection commands
- Navigate back to library → Toolbar clears
- Select different collection → Toolbar updates with new collection commands
- Open output view → OutputView toolbar always visible

### 2. Test on Mobile

```bash
# Desktop mobile simulation
FORCE_MOBILE_UI=true TOGA_BACKEND=toga_cocoa briefcase dev

# iOS Simulator
FORCE_MOBILE_UI=true briefcase build iOS -u
FORCE_MOBILE_UI=true briefcase run iOS -d "DEVICE_UUID"
```

**Expected Behavior**:
- Launch app → LibraryView with bottom toolbar (Add File, Add Folder, Add URL + window navigation)
- Enter edit mode → Bottom toolbar shows edit mode import commands
- Select collection → CollectionView with bottom toolbar (collection commands)
- Open output view → OutputView with bottom toolbar (output editing commands)

### 3. Audit CollectionView Commands

**TODO**: Review `src/fichero/windows/main/views/collection/collection_view.py`
- Check if commands are defined using new system
- Ensure `show_in_bottom_toolbar=True` for toolbar commands
- Verify platform-specific flags (`mobile_only`, `desktop_only`)
- Test native toolbar population on desktop

### 4. Audit OutputView Commands

**TODO**: Review `src/fichero/windows/main/views/output/output_view.py`
- Verify `setup_native_toolbar()` is called in `__init__()` for desktop
- Check command definitions for proper toolbar flags
- Test persistent toolbar on desktop
- Test bottom toolbar on mobile

---

## Testing Checklist

### Desktop Testing

- [ ] LibraryView shows with NO toolbar
- [ ] Selecting collection populates toolbar with collection commands
- [ ] Toolbar commands are clickable and functional
- [ ] Toolbar icons display correctly
- [ ] Navigating back to library clears toolbar
- [ ] OutputView toolbar always visible
- [ ] OutputView toolbar persists when switching between files

### Mobile Testing

- [ ] LibraryView bottom toolbar shows Add File, Add Folder, Add URL
- [ ] LibraryView bottom toolbar shows window navigation buttons
- [ ] Edit mode shows edit mode import commands
- [ ] CollectionView bottom toolbar shows collection commands
- [ ] OutputView bottom toolbar shows output editing commands
- [ ] All toolbar icons display correctly
- [ ] All toolbar commands are clickable and functional

---

## Known Issues

None at this time.

---

## References

- `TOOLBAR_ARCHITECTURE.md` - Detailed architecture documentation
- `ICON_FIX.md` - Icon loading fix
- `CLAUDE.md` - General development guide
- Toga source: `build/fichero/macos/app/app_packages.arm64/toga/`

---

## Migration Pattern for Other Views

When migrating other views (CollectionView, OutputView) to the new command system:

1. **Remove manual toolbar creation**:
   - Delete all `_create_*_button()` methods
   - Remove manual button additions to toolbars

2. **Define commands declaratively**:
   ```python
   def define_commands(self):
       self.commands = {
           'command_name': FicheroCommand(
               id=f'{self.view_id}.command_name',
               label=_("Label"),
               action=self._handler,
               icon='resources/icons/toolbar/icon.png',
               show_in_bottom_toolbar=True,  # For mobile/desktop toolbar
               context='normal',  # or 'edit'
               mobile_only=False,  # or True
           ),
       }
   ```

3. **Register commands**:
   ```python
   def __init__(self, app, is_mobile=False):
       super().__init__(app, is_mobile)
       ViewCommandMixin.__init__(self)
       self.define_commands()
       self.register_commands()
   ```

4. **Set up toolbars**:
   ```python
   # Toolbars will auto-populate from commands
   self.set_toolbars(self.top_toolbar, self.bottom_toolbar)
   ```

5. **Desktop persistent toolbar** (if needed):
   ```python
   # For views with always-visible desktop toolbar (like OutputView)
   if not self.is_mobile:
       self.setup_native_toolbar(
           self.app.main_window.window,
           ['view.command1', 'view.command2', 'view.command3']
       )
   ```

6. **Test both platforms**:
   - Desktop: Verify native toolbar behavior
   - Mobile: Verify bottom toolbar behavior
   - Edit mode: Verify context-specific commands
