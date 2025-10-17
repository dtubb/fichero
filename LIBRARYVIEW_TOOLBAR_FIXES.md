# LibraryView Toolbar Fixes

## Summary

Fixed critical toolbar issues in LibraryView affecting both desktop and mobile platforms:

**Desktop Fixes:**
1. **CRITICAL:** Desktop toolbar wasn't being created at all - added `build_native_toolbar()` call
2. Added Add File/Folder/URL commands to top toolbar
3. Added window navigation commands (Settings, Processing, About, Activity, Prompts, Plans) to top toolbar

**Mobile Fixes:**
4. Added Edit button to top-right of toolbar for mobile root views
5. Removed add commands from normal mode (should only appear in edit mode)
6. Fixed bottom toolbar button alignment (centered, not right-aligned)

## Problems Identified

### 1. Desktop Missing Toolbar Commands

**Error:**
Desktop LibraryView top toolbar was empty - missing Add File, Add Folder, and Add URL commands.

**Root Cause:**
- Add commands had `show_in_bottom_toolbar=True` (for mobile) but were missing `show_in_toolbar=True` (for desktop)
- Commands were configured for mobile bottom toolbar but not for desktop top toolbar

**Affected Commands:**
- `add_file` - line 1151
- `add_folder` - line 1165
- `add_url` - line 1179

### 2. Mobile Add Buttons Showing in Normal Mode

**Error:**
Mobile bottom toolbar was showing add commands in normal mode when they should only appear in edit mode.

**Root Cause:**
- Add commands had `context='normal'` which made them always visible
- Add commands had `show_in_bottom_toolbar=True` which displayed them in mobile normal mode
- User expects: normal mode should only show window commands (Settings, Processing, etc.), add commands should only show in edit mode

**Expected Behavior:**
- Normal mode: Settings, Processing, About, Activity, Prompts, Plans
- Edit mode: Add File, Add Folder, Add URL (via edit_import_* commands)

### 3. Mobile Missing Edit Button

**Error:**
Mobile top toolbar was missing the Edit button on the right side that triggers edit mode.

**Root Cause:**
- TopToolbar's `_add_edit_mode_support()` method created the Edit button but never added it to the visible UI
- Edit button was stored in `self.buttons["edit"]` but not registered in `_regular_buttons`
- Only registered buttons appear in the toolbar

**Expected Behavior:**
- Mobile root views (LibraryView with `auto_mobile_nav=False`) should show Edit button on top-right
- Edit button should trigger edit mode, which shows add commands in bottom toolbar

### 4. Desktop Missing Window Commands

**Error:**
Desktop top toolbar was missing window navigation commands (Settings, Processing, About, Activity, Prompts, Plans).

**Root Cause:**
- Window commands had `show_in_menu=True` (for native Window menu) but were missing `show_in_toolbar=True`
- Commands only appeared in native menus, not in the top toolbar

**Note:** Desktop uses Toga native toolbar - buttons are added via `show_in_toolbar=True`, positioning is handled by Toga.

### 5. Mobile Bottom Toolbar Buttons Right-Aligned

**Error:**
Mobile bottom toolbar buttons were right-aligned instead of centered.

**Root Cause:**
- Window commands had `toolbar_position='right'` which affected mobile bottom toolbar alignment
- The `toolbar_position` property only affects mobile/Toga bottom toolbar (not desktop)
- Should be `toolbar_position='center'` for centered mobile UI alignment

### 6. Desktop Toolbar Not Created At All

**Error:**
Desktop window showed NO toolbar whatsoever - completely empty area where toolbar should be.

**Root Cause:**
- Commands were registered with CommandManager via `register_commands()`
- Commands had correct `show_in_toolbar=True` flags
- BUT `CommandManager.build_native_toolbar()` was NEVER called
- Unlike OutputView (which calls `build_native_toolbar()`), LibraryView didn't create the native window toolbar
- Simply registering commands is not enough - the native `window.toolbar` must be explicitly built

**Key Insight:**
Desktop uses Toga's native `window.toolbar` which must be built by calling `CommandManager.build_native_toolbar()`. This is separate from command registration. Mobile uses custom BottomToolbar widgets which are automatically populated from registered commands, but desktop requires the explicit toolbar creation call.

---

## Fixes Applied

### Fix 0: Desktop Toolbar Creation (CRITICAL)

**Modified:** `src/fichero/windows/main/views/library/library_view.py` (lines 57-72)

**THE CRITICAL FIX** - Without this, desktop has no toolbar at all:

```python
# BEFORE (BROKEN - no toolbar created):
def __init__(self, app, **kwargs):
    # ... initialization code ...
    self.register_commands()  # Commands registered but toolbar never built
    # ❌ No call to build_native_toolbar()!

# AFTER (FIXED - toolbar explicitly created):
def __init__(self, app, **kwargs):
    # ... initialization code ...
    self.register_commands()  # Register commands first

    # Setup native toolbar on desktop
    if not is_mobile and hasattr(app, 'main_window'):
        print("🔧 Setting up native desktop toolbar...")
        try:
            from fichero.shared.commands import CommandManager
            command_manager = CommandManager.get_instance()
            command_manager.build_native_toolbar(
                app.main_window,
                view_id='library',
                context='normal',
                mode='add'
            )
            print("✅ Native toolbar setup complete")
        except Exception as e:
            logger.error(f"Failed to setup native toolbar: {e}")
            print(f"❌ Native toolbar setup failed: {e}")
```

**Why This is Critical:**
1. Desktop uses `window.toolbar` (Toga native toolbar)
2. Mobile uses custom `BottomToolbar` widgets
3. Registering commands adds them to CommandRegistry
4. Mobile toolbars automatically query CommandRegistry when building
5. Desktop toolbar must be explicitly built via `build_native_toolbar()`
6. Without this call, desktop has NO toolbar at all

**Result:**
- Desktop: Native toolbar now appears with all registered commands
- Commands with `show_in_toolbar=True` now actually appear
- Toolbar is properly populated on window creation

**Additional Fix Required:**
After adding the `build_native_toolbar()` call, we discovered that `CommandManager.get_toolbar_commands()` with `toolbar_type="native"` was only checking for `show_in_top_toolbar` or `show_in_bottom_toolbar`, ignoring `show_in_toolbar`. This caused add commands to be filtered out.

**Fix:** Updated `command_manager.py` line 328-336 to also check `show_in_toolbar`:
```python
# BEFORE:
if getattr(cmd, 'show_in_top_toolbar', False) or getattr(cmd, 'show_in_bottom_toolbar', False)

# AFTER:
if (getattr(cmd, 'show_in_toolbar', False) or
    getattr(cmd, 'show_in_top_toolbar', False) or
    getattr(cmd, 'show_in_bottom_toolbar', False))
```

Now all 9 commands (3 add + 6 window) should appear in the desktop toolbar.

### Fix 1: Desktop Toolbar Commands

**Modified:** `src/fichero/windows/main/views/library/library_view.py` (lines 1151-1191)

Added desktop toolbar support to all three add commands:

```python
# BEFORE (BROKEN - no desktop support):
'add_file': FicheroCommand(
    show_in_menu=False,
    show_in_bottom_toolbar=True,  # Mobile only
    desktop_only=False,
    context='normal'
),

# AFTER (FIXED - desktop + mobile separation):
'add_file': FicheroCommand(
    show_in_menu=False,
    show_in_toolbar=True,  # ✅ Desktop top toolbar
    show_in_bottom_toolbar=False,  # ❌ NOT on mobile (use edit mode)
    desktop_only=True,  # ✅ Desktop only, not mobile
    context='normal'  # Always visible on desktop
),
```

**Changes Applied to:**
- `add_file` command (lines 1151-1163)
- `add_folder` command (lines 1165-1177)
- `add_url` command (lines 1179-1191)

**Result:**
- Desktop: Add commands appear in top toolbar (normal mode)
- Mobile: Add commands do NOT appear in bottom toolbar (normal mode)
- Mobile: Add commands still available via edit_import_* commands in edit mode

### Fix 2: Mobile Normal Mode - Remove Add Commands

**Modified:** Same file as Fix 1

Changed add commands from mobile bottom toolbar to desktop-only:

```python
# Key changes:
show_in_toolbar=True           # Show in desktop top toolbar
show_in_bottom_toolbar=False   # Hide from mobile bottom toolbar
desktop_only=True              # Only for desktop, not mobile
```

This ensures add commands don't appear in mobile normal mode. Mobile users will access add functionality through edit mode (edit_import_* commands).

**Existing edit mode commands** (no changes needed):
- `edit_import_files` (line 1323) - `context='edit'`, `mobile_only=True`
- `edit_import_folder` (line 1336) - `context='edit'`, `mobile_only=True`
- `edit_import_urls` (line 1310) - `context='edit'`, `mobile_only=True`

### Fix 3: Mobile Edit Button Support

**Modified:** `src/fichero/shared/toolbars/top_toolbar.py`

**Change 1: Update navigation elements** (lines 129-148)

Added Edit button support for mobile root views:

```python
# BEFORE (BROKEN - no Edit button for root views):
def _add_navigation_elements(self) -> None:
    if self.is_mobile:
        if self.auto_mobile_nav:  # Child views
            self._add_back_button()
        # Add title
        self._add_contextual_title()

# AFTER (FIXED - Edit button for root views):
def _add_navigation_elements(self) -> None:
    if self.is_mobile:
        if self.auto_mobile_nav:  # Child views
            self._add_back_button()
        else:  # Root views
            self._add_edit_button_for_root_view()  # ✅ Add Edit button
        # Add title
        self._add_contextual_title()
```

**Change 2: New method to add Edit button** (lines 252-269)

Created new method to register Edit button for mobile root views:

```python
def _add_edit_button_for_root_view(self) -> None:
    """Add Edit button to right side for mobile root views"""
    try:
        if self.edit_button:
            # Register Edit button as a regular button that appears on the right
            self.register_regular_button(
                button_id="edit",
                button=self.edit_button,
                position="right",
                text=_("Edit"),
                on_press=self._on_edit_pressed
            )
            logger.debug("Edit button added to right side for mobile root view")
        else:
            logger.warning("Edit button not created yet, cannot add to toolbar")

    except Exception as e:
        logger.error(f"Failed to add Edit button for root view: {e}")
```

**How it works:**
1. TopToolbar's `_add_edit_mode_support()` creates Edit button (existing code)
2. `_create_toolbar()` now calls `_add_edit_mode_support()` FIRST (before navigation elements)
3. `_create_toolbar()` always calls `_add_navigation_elements()` (removed conditional)
4. For mobile root views (`auto_mobile_nav=False`), `_add_navigation_elements()` calls `_add_edit_button_for_root_view()`
5. `_add_edit_button_for_root_view()` uses `add_button_right()` to add Edit button to right side
6. Edit button is now visible on mobile root views

### Fix 4: Desktop Window Commands

**Modified:** `src/fichero/windows/main/views/library/library_view.py` (lines 1195-1289)

Added desktop toolbar support to all window navigation commands:

```python
# BEFORE (BROKEN - only in menus):
'settings': FicheroCommand(
    show_in_menu=True,         # Window menu only
    show_in_bottom_toolbar=True,  # Mobile bottom toolbar
    toolbar_position='center',
),

# AFTER (FIXED - menus + toolbar):
'settings': FicheroCommand(
    show_in_menu=True,         # Window menu
    show_in_toolbar=True,      # ✅ Desktop top toolbar
    show_in_bottom_toolbar=True,  # Mobile bottom toolbar
    toolbar_position='center',  # Mobile alignment only
),
```

**Changes Applied to:**
- `settings` command (lines 1195-1209)
- `processing` command (lines 1211-1225)
- `about` command (lines 1227-1241)
- `activity` command (lines 1243-1257)
- `prompts` command (lines 1259-1273)
- `plans` command (lines 1275-1289)

**Result:**
- Desktop: Window commands appear in both native menus AND top toolbar
- Mobile: Window commands appear in bottom toolbar (unchanged)

### Fix 5: Mobile Bottom Toolbar Alignment

**Modified:** Same commands as Fix 4

Ensured window commands use `toolbar_position='center'` for centered mobile bottom toolbar:

```python
# All window commands use:
toolbar_position='center'  # Center on mobile bottom toolbar (Toga only)
```

**Note:** The `toolbar_position` property only affects mobile/Toga bottom toolbar. Desktop Toga native toolbar handles positioning automatically.

**Result:**
- Mobile bottom toolbar: Buttons are centered (not right-aligned)
- Desktop toolbar: Unaffected (Toga handles positioning)

---

## Architecture Documentation

### Desktop vs Mobile Command Distribution

**Desktop (Normal Mode):**
```
Top Toolbar (Toga Native):
- Add File | Add Folder | Add URL | Settings | Processing | About | Activity | Prompts | Plans
  (Toga handles button positioning automatically)

Native Menus:
- Window Menu: Settings, Processing, About, Activity, Prompts, Plans
```

**Mobile (Normal Mode):**
```
Top Toolbar:
- [Left] (empty)
- [Center] Library (title)
- [Right] Edit

Bottom Toolbar:
- Settings | Processing | About | Activity | Prompts | Plans
```

**Mobile (Edit Mode):**
```
Top Toolbar:
- [Left] Done
- [Center] (empty - title hidden in edit mode)
- [Right] Sort (A-Z / Z-A)

Bottom Toolbar (Edit Actions):
- Export | Bulk | URLs | Files | Folder
```

### Command Registration Pattern

**Desktop-Only Commands:**
```python
FicheroCommand(
    show_in_toolbar=True,      # Desktop top toolbar
    show_in_bottom_toolbar=False,  # NOT mobile
    desktop_only=True,         # Desktop-only flag
    context='normal'
)
```

**Mobile-Only Edit Commands:**
```python
FicheroCommand(
    show_in_bottom_toolbar=True,  # Mobile bottom toolbar
    mobile_only=True,          # Mobile-only flag
    context='edit'             # Edit mode only
)
```

**Cross-Platform Commands:**
```python
FicheroCommand(
    show_in_menu=True,         # Desktop native menus
    show_in_bottom_toolbar=True,  # Mobile bottom toolbar
    context='normal'           # Always visible
)
```

---

## Testing Status

**Before Fixes:**
- ❌ Desktop top toolbar: Empty, no add commands, no window commands
- ❌ Mobile normal mode: Add commands incorrectly visible
- ❌ Mobile root view: No Edit button
- ❌ Mobile bottom toolbar: Buttons right-aligned

**After Fixes:**
- ✅ Desktop add commands: `show_in_toolbar=True`, `desktop_only=True`
- ✅ Desktop window commands: `show_in_toolbar=True`, `show_in_menu=True`
- ✅ Mobile normal mode: Add commands hidden (only window commands visible)
- ✅ Mobile Edit button: Added via `_add_edit_button_for_root_view()`
- ✅ Mobile edit mode: Add commands available via edit_import_* commands
- ✅ Mobile bottom toolbar: Buttons centered with `toolbar_position='center'`

**Next Steps:**
- [ ] Test desktop LibraryView toolbar - verify Add File, Add Folder, Add URL appear
- [ ] Test mobile normal mode - verify only window commands appear
- [ ] Test mobile Edit button - verify it appears on top-right and triggers edit mode
- [ ] Test mobile edit mode - verify add commands appear in bottom toolbar

---

## Files Changed

1. **src/fichero/windows/main/views/library/library_view.py**
   - **CRITICAL: Added `build_native_toolbar()` call in `__init__()` (lines 57-72)**
   - Fixed `add_file` command (lines 1151-1163)
   - Fixed `add_folder` command (lines 1165-1177)
   - Fixed `add_url` command (lines 1179-1191)
   - Fixed `settings` command (lines 1195-1209)
   - Fixed `processing` command (lines 1211-1225)
   - Fixed `about` command (lines 1227-1241)
   - Fixed `activity` command (lines 1243-1257)
   - Fixed `prompts` command (lines 1259-1273)
   - Fixed `plans` command (lines 1275-1289)
   - Changes:
     - **Added explicit `build_native_toolbar()` call to create desktop toolbar**
     - Added `show_in_toolbar=True`, `desktop_only=True` to add commands
     - Changed `show_in_bottom_toolbar=False` for add commands
     - Added `show_in_toolbar=True` to all window commands
     - Changed `toolbar_position='center'` for all window commands

2. **src/fichero/shared/toolbars/top_toolbar.py**
   - Modified `_create_toolbar()` method (lines 107-127) - calls `_add_edit_mode_support()` first
   - Modified `_add_navigation_elements()` method (lines 129-148) - adds Edit button for root views
   - Added `_add_edit_button_for_root_view()` method (lines 252-269)
   - Changes: Edit button now registered and visible for mobile root views

3. **src/fichero/shared/commands/command_manager.py**
   - **CRITICAL:** Modified `get_toolbar_commands()` method (lines 328-336)
   - Fixed native toolbar filtering to include `show_in_toolbar` flag
   - Changes: Desktop native toolbar now properly includes all commands with `show_in_toolbar=True`
   - Before: Only checked `show_in_top_toolbar` or `show_in_bottom_toolbar`
   - After: Checks `show_in_toolbar` OR `show_in_top_toolbar` OR `show_in_bottom_toolbar`

---

## Key Learnings

### Desktop Toolbar Creation Requirement

**CRITICAL:** Desktop toolbars must be explicitly created via `build_native_toolbar()`:

```python
# ✅ CORRECT: Create desktop toolbar explicitly
def __init__(self, app, **kwargs):
    # ... initialization ...
    self.register_commands()  # Register commands with CommandManager

    # Desktop: Explicitly build native toolbar
    if not is_mobile and hasattr(app, 'main_window'):
        command_manager = CommandManager.get_instance()
        command_manager.build_native_toolbar(
            app.main_window,
            view_id='library',
            context='normal',
            mode='add'
        )

# ❌ WRONG: Only register commands, don't create toolbar
def __init__(self, app, **kwargs):
    # ... initialization ...
    self.register_commands()  # Commands registered but toolbar never appears!
```

**Key Points:**
- Desktop uses `window.toolbar` (Toga native toolbar)
- Mobile uses custom `BottomToolbar` widgets
- `register_commands()` adds commands to CommandRegistry
- Mobile toolbars automatically query CommandRegistry when building
- Desktop toolbar must be explicitly built via `build_native_toolbar()`
- Without this call, desktop will have NO toolbar at all (even if commands are registered)

### Command Platform Targeting

**Use `desktop_only` and `mobile_only` flags properly:**

```python
# ✅ CORRECT: Separate commands for different platforms
# Desktop command
'add_file': FicheroCommand(
    show_in_toolbar=True,
    desktop_only=True,
    context='normal'
)

# Mobile command (edit mode)
'edit_import_files': FicheroCommand(
    show_in_bottom_toolbar=True,
    mobile_only=True,
    context='edit'
)

# ❌ WRONG: One command for both platforms with conflicting settings
'add_file': FicheroCommand(
    show_in_toolbar=True,          # Desktop
    show_in_bottom_toolbar=True,   # Mobile
    context='normal'  # Conflict: desktop normal mode, but mobile should be edit mode
)
```

### Edit Button Registration

**TopToolbar Edit button must be explicitly registered:**

```python
# ✅ CORRECT: Register Edit button for root views
def _add_navigation_elements(self):
    if self.is_mobile and not self.auto_mobile_nav:
        self._add_edit_button_for_root_view()

def _add_edit_button_for_root_view(self):
    self.register_regular_button(
        button_id="edit",
        button=self.edit_button,
        position="right",
        ...
    )

# ❌ WRONG: Just creating button without registration
def _add_edit_mode_support(self):
    self.edit_button = self.create_button(...)
    self.buttons["edit"] = self.edit_button
    # Button created but never added to UI!
```

### Mobile Edit Mode Pattern

**Mobile edit mode transforms the entire interface:**

1. **Top Toolbar Changes:**
   - Normal mode: Title center, Edit button right
   - Edit mode: Done button left, title hidden, edit actions right

2. **Bottom Toolbar Changes:**
   - Normal mode: Window navigation commands
   - Edit mode: Context-specific edit actions (add/import for LibraryView)

3. **Command Context:**
   - `context='normal'` - Always visible
   - `context='edit'` - Only in edit mode

---

## Verification Checklist

**Code Changes:**
- [x] **CRITICAL: Desktop `build_native_toolbar()` call added to LibraryView.__init__()**
- [x] Desktop add commands have `show_in_toolbar=True`
- [x] Desktop add commands have `desktop_only=True`
- [x] Desktop window commands have `show_in_toolbar=True`
- [x] Desktop window commands have `show_in_menu=True`
- [x] Mobile add commands removed from normal mode (`show_in_bottom_toolbar=False`)
- [x] Mobile edit mode commands remain with `mobile_only=True` and `context='edit'`
- [x] Mobile bottom toolbar commands use `toolbar_position='center'`
- [x] Mobile Edit button added via `_add_edit_button_for_root_view()`
- [x] TopToolbar `_create_toolbar()` calls `_add_edit_mode_support()` first
- [x] TopToolbar `_create_toolbar()` always calls `_add_navigation_elements()`
- [x] TopToolbar `_add_navigation_elements()` calls `_add_edit_button_for_root_view()` for mobile root views

**Testing:**
- [ ] Test desktop mode - verify toolbar shows Add File, Add Folder, Add URL, Settings, Processing, About, Activity, Prompts, Plans
- [ ] Test desktop native menus - verify Window menu shows all window commands
- [ ] Test mobile normal mode - verify bottom toolbar shows centered window commands only
- [ ] Test mobile Edit button - verify it appears on top-right and triggers edit mode
- [ ] Test mobile edit mode - verify add commands appear in centered bottom toolbar
