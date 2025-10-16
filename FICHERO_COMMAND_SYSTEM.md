# FicheroCommand System Documentation

## Overview

The FicheroCommand system is a declarative architecture for managing UI commands in Fichero. It separates **what** commands do (declared by views) from **where** they appear (determined by toolbars and menus).

### Key Principles

1. **Views declare commands** - Each view defines FicheroCommand objects describing available actions
2. **Toolbars/menus query commands** - UI components ask CommandRegistry for commands matching their criteria
3. **Centralized registration** - CommandRegistry maintains a single source of truth
4. **Platform-aware** - Commands can specify mobile-only, desktop-only, or cross-platform availability
5. **Context-aware** - Commands belong to 'normal' or 'edit' modes

## Architecture Components

### 1. FicheroCommand (`src/fichero/shared/commands/fichero_command.py`)

A dataclass that describes a single command:

```python
@dataclass
class FicheroCommand:
    id: str                          # Unique identifier (e.g., 'output.rotate_left')
    label: str                       # Display name
    action: Callable                 # Function to execute

    # Menu integration
    group: str = None                # Menu group ('File', 'Edit', 'View', etc.)
    section: int = 0                 # Section within group
    order: int = 0                   # Order within section
    parent_id: str = None            # For submenus
    shortcut: toga.Key = None        # Keyboard shortcut

    # Toolbar integration
    show_in_top_toolbar: bool = False
    show_in_bottom_toolbar: bool = False
    toolbar_position: str = None     # 'left', 'center', 'right'
    toolbar_text: str = None         # Button label
    icon: str = None                 # Icon path

    # Context and platform
    context: str = 'normal'          # 'normal' or 'edit'
    mobile_only: bool = False
    desktop_only: bool = False

    # Other
    description: str = None
    show_in_menu: bool = True
```

### 2. CommandRegistry (`src/fichero/shared/commands/registry.py`)

Central registry that stores and filters commands:

```python
# Registration
registry.register(command)

# Querying
commands = registry.get_commands_for_view(
    view_id='output',
    context='edit',
    show_in_bottom_toolbar=True
)
```

**Key Methods:**
- `register(command)` - Add a command
- `unregister(command_id)` - Remove a command
- `get_commands_for_view()` - Filter by view, context, toolbar visibility
- `get_command(command_id)` - Get specific command

### 3. ViewCommandMixin (`src/fichero/shared/commands/view_mixin.py`)

Mixin that views inherit to integrate with the command system:

```python
class OutputView(BaseView, ViewCommandMixin):
    def __init__(self, ...):
        super().__init__(...)

        # Define commands
        self.commands = {
            'rotate_left': FicheroCommand(
                id=f'{self.view_id}.rotate_left',
                label=_("Rotate Left"),
                action=self._on_rotate_left,
                context='edit',
                show_in_bottom_toolbar=True,
                toolbar_position='left',
                # ... more properties
            ),
            # ... more commands
        }

        # Register with CommandRegistry
        self.register_commands()
```

### 4. CommandManager (`src/fichero/shared/commands/command_manager.py`)

Manages platform-specific command integration:
- Desktop: Creates native menu items
- Mobile: Provides command lists for toolbar buttons

### 5. ToolbarCoordinator (`src/fichero/shared/toolbars/toolbar_coordinator.py`)

Coordinates edit mode state and tracks active view:

```python
# Views notify coordinator when they become active
def show(self):
    self.coordinator.set_active_view('output')

# Coordinator remembers active view for edit mode
coordinator.set_edit_mode(EditModeState.EDIT)  # Uses stored view_id
```

## Command Flow

### Desktop Platform

1. **View declares commands**
   ```python
   commands = {
       'rotate_left': FicheroCommand(
           id='output.rotate_left',
           label="Rotate Left",
           action=self._on_rotate_left,
           group='Tools',
           shortcut=toga.Key.MOD_1 + 'l',
           show_in_menu=True
       )
   }
   ```

2. **CommandManager creates native menu**
   ```python
   command_manager.register_view_commands(view_id, commands)
   # → Adds "Rotate Left" to Tools menu with ⌘L shortcut
   ```

3. **User clicks menu item**
   ```
   User clicks "Tools → Rotate Left"
   → CommandManager executes command.action()
   → View's _on_rotate_left() is called
   ```

### Mobile Platform

1. **View declares commands**
   ```python
   commands = {
       'process': FicheroCommand(
           id='collection.process',
           label="Process",
           action=self._on_process,
           show_in_bottom_toolbar=True,
           toolbar_position='center',
           icon='resources/icons/process.png'
       )
   }
   ```

2. **Toolbar queries commands**
   ```python
   commands = registry.get_commands_for_view(
       view_id='collection',
       context='normal',
       show_in_bottom_toolbar=True
   )
   # → Returns ['process'] command
   ```

3. **Toolbar creates button**
   ```python
   for command in commands:
       button = toolbar.add_command_button(command, position='center')
   # → Creates "Process" button in center of bottom toolbar
   ```

4. **User taps button**
   ```
   User taps "Process" button
   → Button calls command.action()
   → View's _on_process() is called
   ```

## Edit Mode System

### Normal vs Edit Context

Commands belong to one of two contexts:
- **`context='normal'`** - Available in normal mode (default)
- **`context='edit'`** - Available only when Edit mode is active

### Edit Mode Flow

1. **User clicks Edit button** (in TopToolbar)
   ```python
   # TopToolbar Edit button
   coordinator.set_edit_mode(EditModeState.EDIT)
   ```

2. **Coordinator propagates to toolbars**
   ```python
   # ToolbarCoordinator
   def set_edit_mode(state, context):
       # Uses stored active view_id
       context['view_id'] = self._current_view_id

       # Update toolbars
       top_toolbar.set_edit_mode(state, context)
       bottom_toolbar.set_edit_mode(state, context)
   ```

3. **Bottom toolbar queries edit commands**
   ```python
   # BottomToolbar
   def set_edit_mode(state, context):
       if state == EditModeState.EDIT:
           view_id = context.get('view_id')

           # Query edit commands for this view
           commands = registry.get_commands_for_view(
               view_id=view_id,
               context='edit',
               show_in_bottom_toolbar=True
           )

           # Create buttons
           for command in commands:
               self.add_command_button(command, command.toolbar_position)
   ```

4. **User clicks Done**
   ```python
   coordinator.set_edit_mode(EditModeState.NORMAL)
   # → Edit buttons removed, normal buttons restored
   ```

### Sticky Context Pattern

The coordinator remembers which view is active:

```python
# LibraryView.show()
def show(self):
    self.coordinator.set_active_view('library')

# Later, when Edit is clicked without explicit context
coordinator.set_edit_mode(EditModeState.EDIT)
# → Automatically uses 'library' as view_id
```

This allows the Edit button in TopToolbar to work without knowing which view is active.

## Platform-Specific Behavior

### Desktop (`is_mobile=False`)

**Menus:**
- Commands with `show_in_menu=True` appear in native menu bar
- Organized by `group`, `section`, `order`
- Keyboard shortcuts work system-wide

**Toolbars:**
- Top toolbar: Native window toolbar (optional)
- Bottom toolbar: Not typically used, but available for edit mode
- Commands query: `show_in_bottom_toolbar=True` for edit mode

**Edit Mode:**
- Edit button in native toolbar
- Edit commands appear in bottom toolbar when Edit is clicked

### Mobile (`is_mobile=True`)

**Menus:**
- No native menu bar
- Commands can still be registered but won't appear visually

**Toolbars:**
- Top toolbar: Custom Toga Box with title and buttons
- Bottom toolbar: Main command interface
- Commands query: `show_in_bottom_toolbar=True` for normal mode

**Edit Mode:**
- Edit button in top toolbar
- Edit commands replace normal commands in bottom toolbar

### Cross-Platform Commands

Use neither `mobile_only` nor `desktop_only`:

```python
FicheroCommand(
    id='output.rotate_left',
    label="Rotate Left",

    # Desktop: appears in menu
    group='Tools',
    show_in_menu=True,
    shortcut=toga.Key.MOD_1 + 'l',

    # Mobile: appears in edit toolbar
    show_in_bottom_toolbar=True,
    toolbar_position='left',
    context='edit',

    # Neither mobile_only nor desktop_only
    mobile_only=False,
    desktop_only=False
)
```

## Example: OutputView Edit Commands

Full example showing rotate, crop, and reset commands:

```python
class OutputView(BaseView, ViewCommandMixin):
    def _define_commands(self) -> Dict[str, FicheroCommand]:
        tools_group = CommandGroup.TOOLS.value

        return {
            'rotate_left': FicheroCommand(
                id=f'{self.view_id}.rotate_left',
                label=_("Rotate Left"),
                action=self._on_rotate_left,
                shortcut=toga.Key.MOD_1 + 'l',
                icon='resources/icons/toolbar/rotate.left@10x.png',
                description=_("Rotate image 90° counter-clockwise"),
                group=tools_group,
                section=0,
                order=0,
                toolbar_text=_("Rotate\nLeft"),
                toolbar_position='left',
                show_in_menu=True,
                show_in_bottom_toolbar=True,
                desktop_only=False,
                context='edit'  # Only in edit mode
            ),

            'rotate_right': FicheroCommand(
                id=f'{self.view_id}.rotate_right',
                label=_("Rotate Right"),
                action=self._on_rotate_right,
                shortcut=toga.Key.MOD_1 + 'r',
                icon='resources/icons/toolbar/rotate.right@10x.png',
                description=_("Rotate image 90° clockwise"),
                group=tools_group,
                section=0,
                order=1,
                toolbar_text=_("Rotate\nRight"),
                toolbar_position='left',
                show_in_menu=True,
                show_in_bottom_toolbar=True,
                desktop_only=False,
                context='edit'  # Only in edit mode
            ),

            'crop': FicheroCommand(
                id=f'{self.view_id}.crop',
                label=_("Crop Image"),
                action=self._on_crop,
                shortcut=toga.Key.MOD_1 + 'k',
                icon='resources/icons/toolbar/crop@10x.png',
                description=_("Crop image to selection"),
                group=tools_group,
                section=0,
                order=2,
                toolbar_text=_("Crop"),
                toolbar_position='right',
                show_in_menu=True,
                show_in_bottom_toolbar=True,
                desktop_only=False,
                context='edit'  # Only in edit mode
            ),

            'reset': FicheroCommand(
                id=f'{self.view_id}.reset',
                label=_("Reset to Original"),
                action=self._on_reset,
                shortcut=toga.Key.MOD_1 + '0',
                icon='resources/icons/toolbar/reset@10x.png',
                description=_("Reset to original image"),
                group=tools_group,
                section=0,
                order=3,
                toolbar_text=_("Reset"),
                toolbar_position='right',
                show_in_menu=True,
                show_in_bottom_toolbar=True,
                desktop_only=False,
                context='edit'  # Only in edit mode
            ),
        }
```

## Example: LibraryView Import Commands

Commands available in edit mode for importing content:

```python
'export': FicheroCommand(
    id=f'{self.view_id}.export',
    label=_("Export"),
    action=self._on_export_collection,
    icon='resources/icons/toolbar/download.png',
    description=_("Export selected collection"),
    show_in_menu=False,
    show_in_bottom_toolbar=True,
    toolbar_position='center',
    mobile_only=False,  # Available on desktop too!
    context='edit'
),

'bulk_import': FicheroCommand(
    id=f'{self.view_id}.bulk_import',
    label=_("Bulk Import"),
    action=self._on_bulk_import,
    icon='resources/icons/toolbar/bulk_import.png',
    description=_("Import multiple items"),
    show_in_menu=False,
    show_in_bottom_toolbar=True,
    toolbar_position='left',
    mobile_only=False,
    context='edit'
),
```

## Best Practices

### 1. Command Naming

Use descriptive IDs with view prefix:
```python
# Good
id='output.rotate_left'
id='library.export'

# Bad
id='rotate'  # Too generic
id='btn_1'   # Non-descriptive
```

### 2. Context Selection

Choose context based on frequency:
```python
# Normal mode: Frequent actions
context='normal'  # Process, navigate, view

# Edit mode: Less frequent, potentially destructive
context='edit'    # Rotate, crop, delete, export
```

### 3. Platform Targeting

Default to cross-platform unless there's a specific reason:
```python
# Cross-platform (default - omit both flags)
mobile_only=False
desktop_only=False

# Mobile-only (touch-optimized, no keyboard)
mobile_only=True

# Desktop-only (requires keyboard shortcuts, complex menus)
desktop_only=True
```

### 4. Toolbar Position

Use consistent positioning:
```python
toolbar_position='left'    # Destructive or primary actions
toolbar_position='center'  # Main action
toolbar_position='right'   # Secondary or cancel actions
```

### 5. Icons and Text

Provide both for flexibility:
```python
icon='resources/icons/toolbar/process.png'
toolbar_text=_("Process")  # Used when no icon or as tooltip
```

### 6. Menu Organization

Group related commands:
```python
# File operations
group='File'
section=0  # New, Open
section=1  # Import submenu
section=2  # Save, Export

# View operations
group='View'
section=0  # Zoom commands
section=1  # Navigation commands
```

## Common Patterns

### Pattern 1: View with Normal and Edit Commands

```python
def _define_commands(self):
    return {
        # Normal mode - always visible
        'zoom_in': FicheroCommand(
            context='normal',
            show_in_menu=True,
            # ...
        ),

        # Edit mode - only when editing
        'rotate': FicheroCommand(
            context='edit',
            show_in_bottom_toolbar=True,
            # ...
        ),
    }
```

### Pattern 2: Platform-Specific Variants

```python
def _define_commands(self):
    commands = {
        # Desktop: Menu item with shortcut
        'settings_desktop': FicheroCommand(
            id=f'{self.view_id}.settings',
            desktop_only=True,
            show_in_menu=True,
            shortcut=toga.Key.MOD_1 + ',',
            # ...
        ) if not self.is_mobile else None,

        # Mobile: Toolbar button
        'settings_mobile': FicheroCommand(
            id=f'{self.view_id}.settings',
            mobile_only=True,
            show_in_bottom_toolbar=True,
            # ...
        ) if self.is_mobile else None,
    }
    return {k: v for k, v in commands.items() if v is not None}
```

### Pattern 3: Submenu Commands

```python
# Parent menu item
'import': FicheroCommand(
    id=f'{self.view_id}.import',
    label=_("Import"),
    action=None,  # No action, just a parent
    show_in_menu=True,
    group='File',
),

# Children
'import_file': FicheroCommand(
    id=f'{self.view_id}.import_file',
    label=_("File…"),
    action=self._on_import_file,
    parent_id=f'{self.view_id}.import',  # Links to parent
    show_in_menu=True,
),
```

## Troubleshooting

### Commands Not Appearing in Toolbar

**Check:**
1. `show_in_bottom_toolbar=True` (or `show_in_top_toolbar=True`)
2. Correct `context` ('normal' or 'edit')
3. Platform flags (`mobile_only`/`desktop_only` not excluding current platform)
4. View is calling `coordinator.set_active_view()` in `show()`

**Debug:**
```python
# In toolbar code
commands = registry.get_commands_for_view(view_id, context, show_in_bottom_toolbar=True)
logger.debug(f"Found {len(commands)} commands for {view_id} in {context} mode")
```

### Commands Not Appearing in Menu (Desktop)

**Check:**
1. `show_in_menu=True`
2. `group` is specified (e.g., 'File', 'Edit', 'View')
3. Not `mobile_only=True`

**Debug:**
```python
# In CommandManager
logger.debug(f"Adding to menu: {command.id} → {command.group} [section={command.section}]")
```

### Edit Mode Not Working

**Check:**
1. Commands have `context='edit'`
2. View calls `coordinator.set_active_view()` in `show()`
3. Edit button calls `coordinator.set_edit_mode(EditModeState.EDIT)`
4. Buttons are added to UI in `bottom_toolbar.py` (see line 432-446)

**Debug:**
```python
# In ToolbarCoordinator
logger.debug(f"Active view: {self._current_view_id}")
logger.debug(f"Edit mode: {self._edit_mode_state}")
```

### Icons Not Showing

**Check:**
1. Icon path is relative to app root: `'resources/icons/...'`
2. Icon file exists and is accessible
3. Icon format is supported (PNG recommended)

## Migration Guide

### From Imperative to Declarative

**Before (Imperative):**
```python
# In view __init__
self.process_button = toga.Button(
    "Process",
    on_press=self._on_process,
    style=Pack(padding=5)
)
toolbar.add_button(self.process_button, position='center')
```

**After (Declarative):**
```python
# In view _define_commands()
'process': FicheroCommand(
    id=f'{self.view_id}.process',
    label=_("Process"),
    action=self._on_process,
    show_in_bottom_toolbar=True,
    toolbar_position='center',
    icon='resources/icons/process.png'
)

# Toolbar automatically creates button by querying registry
```

## Testing

### Testing Command Registration

```python
def test_command_registration():
    registry = CommandRegistry()

    command = FicheroCommand(
        id='test.action',
        label="Test",
        action=lambda: None,
        context='normal'
    )

    registry.register(command)
    assert registry.get_command('test.action') == command
```

### Testing Command Filtering

```python
def test_edit_command_filtering():
    registry = CommandRegistry()

    # Register normal and edit commands
    registry.register(FicheroCommand(
        id='view.normal',
        context='normal',
        show_in_bottom_toolbar=True
    ))
    registry.register(FicheroCommand(
        id='view.edit',
        context='edit',
        show_in_bottom_toolbar=True
    ))

    # Query edit commands
    edit_cmds = registry.get_commands_for_view(
        view_id='view',
        context='edit',
        show_in_bottom_toolbar=True
    )

    assert len(edit_cmds) == 1
    assert edit_cmds[0].id == 'view.edit'
```

## Performance Considerations

### Registry Lookups

The CommandRegistry uses a simple dict-based lookup, which is O(1) for getting commands by ID and O(n) for filtering. This is acceptable for the expected number of commands (dozens, not thousands).

### Command Creation Timing

Commands are created once during view initialization, not on every toolbar update. This keeps the system responsive.

### Toolbar Button Creation

Buttons are created on-demand when toolbars query for commands. This is efficient because:
1. Only active toolbar buttons are created
2. Buttons are cached and reused
3. Edit mode toggle simply swaps button sets

## Future Enhancements

### Possible Extensions

1. **Dynamic Command Enabling/Disabling**
   ```python
   command.enabled = can_process()
   registry.notify_changed(command.id)
   ```

2. **Command Badges**
   ```python
   command.badge = notification_count
   ```

3. **Command State**
   ```python
   command.toggled = is_selected
   ```

4. **Async Actions**
   ```python
   async def action():
       await long_operation()
   ```

## Related Files

- `src/fichero/shared/commands/fichero_command.py` - FicheroCommand dataclass
- `src/fichero/shared/commands/registry.py` - CommandRegistry
- `src/fichero/shared/commands/view_mixin.py` - ViewCommandMixin
- `src/fichero/shared/commands/command_manager.py` - Platform integration
- `src/fichero/shared/toolbars/toolbar_coordinator.py` - Edit mode coordination
- `src/fichero/shared/toolbars/base_toolbar.py` - Toolbar button creation
- `src/fichero/shared/toolbars/bottom_toolbar.py` - Bottom toolbar implementation
- `src/fichero/shared/toolbars/top_toolbar.py` - Top toolbar implementation
- `src/fichero/windows/main/views/output/output_view.py` - Example: OutputView commands
- `src/fichero/windows/main/views/library/library_view.py` - Example: LibraryView commands

## Summary

The FicheroCommand system provides a clean, declarative way to manage UI commands across platforms and contexts. Key benefits:

- **Separation of concerns** - Views focus on what, UI focuses on where
- **Platform adaptability** - Same commands work on mobile and desktop
- **Context awareness** - Normal vs edit modes handled automatically
- **Maintainability** - Commands defined in one place, used everywhere
- **Testability** - Easy to test command logic independently of UI

By following the patterns and best practices in this document, you can create consistent, cross-platform command interfaces throughout Fichero.
