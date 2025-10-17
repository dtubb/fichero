# Toolbar Architecture - Platform-Adaptive Command System

**Last Updated**: October 9, 2025

## Overview

Fichero uses a **declarative, platform-adaptive command system** where views define **what commands are available**, and the system automatically figures out where and how to display them.

**Key Principle**: Views declare commands with metadata (labels, icons, flags). The CommandManager + BaseView + MainWindow handle all the details:
- Which platform (desktop vs mobile)
- Which toolbar (top, bottom, native)
- When to show/hide (context, view switching)
- How to render (icons, labels, positioning)

**Views don't micromanage**. They just say "here are my commands" and the system does the rest.

---

## Platform-Specific Behavior

### Desktop (macOS, Windows, Linux)

**Native Window Toolbar (`window.toolbar`)**:
- Uses Toga's native `window.toolbar` CommandSet
- Commands filtered using `toolbar_type="native"`
- Shows commands with `show_in_top_toolbar=True` or `show_in_bottom_toolbar=True`
- Supports icons + text labels
- Keyboard shortcuts work automatically

**View-Specific Toolbar Behavior**:
- **LibraryView**: Declares Add File/Folder/URL commands. MainWindow shows them in native toolbar.
- **CollectionView**: Declares collection commands. MainWindow shows them in native toolbar when collection selected.
- **OutputView**: Declares output editing commands. MainWindow shows them in native toolbar (always visible).

**Bottom Toolbar**:
- Desktop does NOT render bottom toolbar (skipped in `BaseView.set_toolbars()`)
- Commands intended for bottom toolbar are shown in native `window.toolbar` instead

### Mobile (iOS, Android)

**Custom Toolbars**:
- **Top Toolbar**: Navigation bar with back button + title + optional action buttons
- **Bottom Toolbar**: Primary action toolbar with commands

**Command Filtering**:
- Commands filtered using `toolbar_type="top"` or `toolbar_type="bottom"`
- Respects `mobile_only=True` flag (skips desktop-only commands)
- Mobile uses custom `BaseToolbar` implementation (not native Toga toolbar)

**View-Specific Toolbar Behavior**:
- **LibraryView**: Bottom toolbar with Add File, Add Folder, Add URL + window navigation buttons
- **CollectionView**: Bottom toolbar with collection-specific commands
- **OutputView**: Bottom toolbar with output-specific commands

---

## Command Definition Pattern

### Philosophy

Views are **declarative**:
- "I have these commands available"
- "This command needs an icon on mobile"
- "This command only makes sense in edit mode"

Views are **not imperative**:
- ❌ Don't create toolbar buttons
- ❌ Don't manage toolbar visibility
- ❌ Don't worry about platform differences
- ❌ Don't update toolbars when state changes

The system handles all that automatically.

### Basic Structure

```python
def define_commands(self):
    """Define all commands for this view - just declare what's available"""
    self.commands = {
        'command_name': FicheroCommand(
            id=f'{self.view_id}.command_name',
            label=_("Command Label"),
            action=self._handler_method,
            icon='resources/icons/toolbar/icon.png',  # Optional
            description=_("Command description"),

            # Menu visibility (desktop only)
            show_in_menu=False,  # True to show in native menu bar

            # Toolbar placement
            show_in_top_toolbar=False,     # Top toolbar (mobile) or native toolbar (desktop)
            show_in_bottom_toolbar=True,   # Bottom toolbar (mobile) or native toolbar (desktop)

            # Platform filtering
            desktop_only=False,  # True = desktop only
            mobile_only=False,   # True = mobile only

            # Context filtering
            context='normal',  # 'normal' or 'edit' (for edit mode commands)

            # Positioning
            toolbar_position='center',  # 'left', 'center', 'right' (mobile only)

            # Keyboard shortcuts (desktop only)
            shortcut=toga.Key.MOD_1 + 'n',  # Optional
            group=toga.Group.VIEW,  # Optional menu group
        ),
    }
```

### Command Registration

After defining commands, register them with CommandManager:

```python
def __init__(self, app, is_mobile=False):
    super().__init__(app, is_mobile)
    ViewCommandMixin.__init__(self)

    # Just define and register - that's it!
    self.define_commands()
    self.register_commands()

    # The system handles:
    # - Platform detection (desktop vs mobile)
    # - Toolbar creation (native vs custom)
    # - Command filtering (context, toolbar type)
    # - Icon loading (absolute path conversion)
```

---

## LibraryView Commands (Example)

### Desktop Commands

```python
# These 3 commands appear in native window.toolbar when collection is selected
'add_file': FicheroCommand(
    id='library.add_file',
    label=_("Add File"),
    action=self._on_import_files,
    icon='resources/icons/toolbar/document.png',
    show_in_menu=False,
    show_in_bottom_toolbar=True,  # Routes to native toolbar on desktop
    desktop_only=False,  # Available on both platforms
    context='normal'  # Always visible
),

'add_folder': FicheroCommand(
    id='library.add_folder',
    label=_("Add Folder"),
    action=self._on_import_folder,
    icon='resources/icons/toolbar/folder@10x.png',
    show_in_menu=False,
    show_in_bottom_toolbar=True,
    desktop_only=False,
    context='normal'
),

'add_url': FicheroCommand(
    id='library.add_url',
    label=_("Add URL"),
    action=self._on_import_urls,
    icon='resources/icons/toolbar/link.png',
    show_in_menu=False,
    show_in_bottom_toolbar=True,
    desktop_only=False,
    context='normal'
),
```

### Mobile-Only Commands

```python
# Window navigation (mobile bottom toolbar only)
'settings': FicheroCommand(
    id='library.settings',
    label=_("Settings"),
    action=self._on_open_settings_window,
    icon='resources/icons/toolbar/settings.png',
    show_in_menu=False,
    show_in_bottom_toolbar=True,
    mobile_only=True,  # Only on mobile
    context='normal'
),

# Edit mode import commands (mobile bottom toolbar, edit mode only)
'bulk_import': FicheroCommand(
    id='library.bulk_import',
    label=_("Bulk Import"),
    action=self._on_import_bulk,
    icon='resources/icons/toolbar/document.png',
    show_in_menu=False,
    show_in_bottom_toolbar=True,
    mobile_only=True,  # Only on mobile
    context='edit'  # Only in edit mode
),
```

---

## Command Filtering Logic

### CommandManager.get_toolbar_commands()

```python
def get_toolbar_commands(self, view_id: str = None, context: str = None,
                         toolbar_type: str = None) -> list:
    """
    Get commands suitable for toolbar display

    Args:
        view_id: Filter by view (e.g., "library", "collection", "output")
        context: Filter by context ("normal" or "edit")
        toolbar_type: Filter by toolbar type ("top", "bottom", "native")

    Returns:
        List of FicheroCommand instances
    """
```

**Filter Stages**:

1. **Toolbar Type Filter**:
   - `toolbar_type="top"` → Only commands with `show_in_top_toolbar=True`
   - `toolbar_type="bottom"` → Only commands with `show_in_bottom_toolbar=True`
   - `toolbar_type="native"` → Commands with either flag (desktop native toolbar)
   - `toolbar_type=None` → Any toolbar flag (legacy)

2. **View Filter** (if `view_id` provided):
   - Only commands with IDs starting with `{view_id}.`
   - Example: `view_id="library"` → matches `library.add_file`, `library.settings`, etc.

3. **Context Filter** (if `context` provided):
   - Only commands with matching `context` attribute
   - Example: `context="edit"` → only edit mode commands
   - Example: `context="normal"` → only normal mode commands

4. **Platform Filter** (automatic):
   - Desktop: Skips commands with `mobile_only=True`
   - Mobile: Skips commands with `desktop_only=True`

---

## BaseView Integration

### Automatic Toolbar Population

```python
def set_toolbars(self, top_toolbar=None, bottom_toolbar=None):
    """
    Set toolbars with platform-adaptive rendering

    Platform behavior:
    - Desktop: Only renders top toolbar. Bottom toolbar skipped (native window.toolbar used instead)
    - Mobile: Renders both toolbars. Auto-populates from registered commands.
    """
```

**Desktop**:
```python
# Top toolbar rendered
if top_toolbar:
    self.set_top_toolbar(top_toolbar)
    top_toolbar.populate_from_commands(
        view_id=self.view_id,
        context='normal',
        toolbar_type='top'
    )

# Bottom toolbar SKIPPED on desktop
if bottom_toolbar:
    logger.debug("Skipping bottom toolbar on desktop - using native window.toolbar")
```

**Mobile**:
```python
# Top toolbar rendered
if top_toolbar:
    self.set_top_toolbar(top_toolbar)
    top_toolbar.populate_from_commands(
        view_id=self.view_id,
        context='normal',
        toolbar_type='top'
    )

# Bottom toolbar rendered
if bottom_toolbar:
    self.set_bottom_toolbar(bottom_toolbar)
    bottom_toolbar.populate_from_commands(
        view_id=self.view_id,
        context='normal',
        toolbar_type='bottom'
    )
```

---

## System Responsibilities (Not View Responsibilities)

### MainWindow: Manages Desktop Native Toolbar

MainWindow is responsible for calling `build_native_toolbar()` when views change:

```python
# In MainWindow
def _on_show_library(self, event):
    """Show library view and update toolbar"""
    library_view = self._get_or_create_library_view()

    # MainWindow manages toolbar - view just declared commands
    if not self.is_mobile:
        self._update_toolbar_for_library_view(context='normal')

    # Show view
    self._show_view_desktop("library", library_view, "left")

def _on_show_collection(self, event):
    """Show collection view and update toolbar"""
    collection_view = self._get_or_create_collection_view(collection_id, collection_name)

    # MainWindow manages toolbar - view just declared commands
    if not self.is_mobile:
        self._update_toolbar_for_collection_view(context='normal')

    # Show view
    self._show_view_desktop("collection", collection_view, "center")
```

**Views don't call these methods**. MainWindow does it automatically when switching views.

### BaseView: Auto-Populates Custom Toolbars (Mobile)

On mobile, BaseView automatically populates toolbars from commands:

```python
# In BaseView.set_toolbars() - called automatically during view init
if self.is_mobile:
    # Auto-populate bottom toolbar from registered commands
    bottom_toolbar.populate_from_commands(
        view_id=self.view_id,
        context='normal',
        toolbar_type='bottom'
    )
```

**Views don't call this**. It happens automatically during initialization.

---

## Testing

### Desktop Testing

```bash
# Desktop UI mode
FORCE_MOBILE_UI=false TOGA_BACKEND=toga_cocoa briefcase dev

# Expected behavior:
# - LibraryView: No toolbar initially
# - Select collection → Native toolbar appears with collection commands
# - OutputView: Native toolbar always visible with edit commands
```

### Mobile Testing

```bash
# Mobile UI mode (desktop simulation)
FORCE_MOBILE_UI=true TOGA_BACKEND=toga_cocoa briefcase dev

# iOS Simulator
FORCE_MOBILE_UI=true briefcase build iOS -u
FORCE_MOBILE_UI=true briefcase run iOS -d "DEVICE_UUID"

# Expected behavior:
# - LibraryView: Bottom toolbar with Add File, Add Folder, Add URL + window nav
# - Edit mode: Bottom toolbar shows edit mode import commands
# - CollectionView: Bottom toolbar with collection commands
# - OutputView: Bottom toolbar with output commands
```

---

## Common Patterns

### Always-Visible Commands (Normal Mode)

```python
'my_command': FicheroCommand(
    id=f'{self.view_id}.my_command',
    label=_("My Command"),
    action=self._handler,
    show_in_bottom_toolbar=True,
    context='normal'  # Always visible
)
```

### Edit Mode Commands

```python
'edit_command': FicheroCommand(
    id=f'{self.view_id}.edit_command',
    label=_("Edit Command"),
    action=self._handler,
    show_in_bottom_toolbar=True,
    context='edit'  # Only in edit mode
)
```

### Mobile-Only Window Navigation

```python
'settings': FicheroCommand(
    id=f'{self.view_id}.settings',
    label=_("Settings"),
    action=self._on_settings,
    show_in_bottom_toolbar=True,
    mobile_only=True,  # Not shown on desktop
    context='normal'
)
```

### Desktop Menu + Toolbar Command

```python
'my_command': FicheroCommand(
    id=f'{self.view_id}.my_command',
    label=_("My Command"),
    action=self._handler,
    show_in_menu=True,  # Show in native menu bar
    show_in_bottom_toolbar=True,  # Show in toolbar
    shortcut=toga.Key.MOD_1 + 'n',  # Keyboard shortcut
    group=toga.Group.VIEW,  # Menu group
)
```

---

## Migration Checklist

When migrating a view to the new command system:

- [ ] Remove all manual toolbar button creation methods
- [ ] Define all commands in `define_commands()` method
- [ ] Call `self.register_commands()` in `__init__()`
- [ ] Use `show_in_top_toolbar` and `show_in_bottom_toolbar` flags (NOT deprecated `show_in_toolbar`)
- [ ] Mark mobile-only commands with `mobile_only=True`
- [ ] Mark desktop-only commands with `desktop_only=True`
- [ ] Set `context='edit'` for edit mode commands
- [ ] For persistent desktop toolbars: Call `setup_native_toolbar()` in view's `__init__()`
- [ ] For dynamic desktop toolbars: Manage in MainWindow/NavigationController
- [ ] Test on both desktop and mobile

---

## Files Modified

### Core System

- `src/fichero/shared/commands/command_manager.py` - Enhanced filtering logic
- `src/fichero/shared/toolbars/base_toolbar.py` - Toolbar population from commands
- `src/fichero/shared/views/base_view.py` - Platform-adaptive toolbar rendering

### Views

- `src/fichero/windows/main/views/library/library_view.py` - Migrated to new command system
- `src/fichero/windows/main/views/collection/collection_view.py` - TODO: Audit and migrate
- `src/fichero/windows/main/views/output/output_view.py` - TODO: Audit and migrate

---

## Next Steps

1. **Verify MainWindow Native Toolbar Management**:
   - Check if MainWindow properly manages toolbar when switching between LibraryView and CollectionView
   - Ensure toolbar cleared when showing LibraryView
   - Ensure toolbar populated when showing CollectionView

2. **Test on Desktop**:
   - Verify no toolbar on LibraryView initially
   - Verify toolbar appears when collection selected
   - Verify OutputView toolbar always visible

3. **Audit CollectionView**:
   - Review command definitions
   - Ensure proper `show_in_bottom_toolbar` usage
   - Test native toolbar population

4. **Audit OutputView**:
   - Verify persistent toolbar setup
   - Ensure `setup_native_toolbar()` called in `__init__()`
   - Test toolbar always visible

---

## References

- `ICON_FIX.md` - Icon loading fix documentation
- `CLAUDE.md` - General development guide
- Toga source: `build/fichero/macos/app/app_packages.arm64/toga/`
