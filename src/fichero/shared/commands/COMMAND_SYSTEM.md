# Unified Command System for Fichero

## Overview

The Fichero command system provides a single, unified way to define commands that work seamlessly across:
- **Desktop**: Native menus with keyboard shortcuts + custom toolbars
- **Mobile**: Custom toolbars only (no native menus)

Define your commands once, and the system automatically routes them to the appropriate UI elements based on the platform.

## Architecture

### Core Components

1. **FicheroCommand** (`command.py`)
   - Represents a single command with all metadata
   - Platform-agnostic definition

2. **CommandRegistry** (`registry.py`)
   - Singleton registry storing all commands
   - Centralized command lookup and execution

3. **CommandManager** (`command_manager.py`)
   - Platform orchestrator
   - Routes commands to menus (desktop) or toolbars (mobile/desktop)
   - Handles native Toga command creation

4. **ViewCommandMixin** (`view_mixin.py`)
   - Helper mixin for views
   - Simplifies command registration
   - One-line toolbar population

5. **BaseToolbar** (`../toolbars/base_toolbar.py`)
   - Command consumer
   - Auto-populates from CommandRegistry
   - Handles platform-specific rendering

## Quick Start

### Step 1: Define Commands in Your View

```python
import toga
from fichero.shared.views.base_view import BaseView
from fichero.shared.commands import FicheroCommand, ViewCommandMixin

class OutputView(BaseView, ViewCommandMixin):
    """Output view with unified commands"""

    def __init__(self, app, is_mobile=False):
        # Set view identifier BEFORE calling super()
        self.view_id = "output"

        # Call parent constructors
        super().__init__(app, is_mobile)
        ViewCommandMixin.__init__(self)

        # Define and register commands
        self.define_commands()
        self.register_commands()

        # Create toolbars (commands will be auto-populated)
        self._setup_toolbars()

    def define_commands(self):
        """Define all commands for this view"""
        self.commands = {
            'rotate_left': FicheroCommand(
                id=f'{self.view_id}.rotate_left',
                label='Rotate Left',
                action=self._rotate_left,
                shortcut=toga.Key.MOD_1 + 'l',  # Cmd+L / Ctrl+L
                icon='resources/icons/rotate_left.png',
                toolbar_text='Rotate\nLeft',  # Multi-line for toolbar
                toolbar_position='center',     # left, center, or right
                show_in_menu=True,            # Desktop: add to menu
                show_in_toolbar=True          # Both: add to toolbar
            ),
            'rotate_right': FicheroCommand(
                id=f'{self.view_id}.rotate_right',
                label='Rotate Right',
                action=self._rotate_right,
                shortcut=toga.Key.MOD_1 + 'r',
                icon='resources/icons/rotate_right.png',
                toolbar_text='Rotate\nRight',
                toolbar_position='center',
                show_in_menu=True,
                show_in_toolbar=True
            ),
            'crop': FicheroCommand(
                id=f'{self.view_id}.crop',
                label='Crop',
                action=self._crop,
                shortcut=toga.Key.MOD_1 + 'k',
                icon='resources/icons/crop.png',
                toolbar_text='Crop',
                toolbar_position='center',
                show_in_menu=True,
                show_in_toolbar=True
            )
        }

    def _setup_toolbars(self):
        """Setup toolbars with auto-population"""
        from fichero.shared.toolbars import TopToolbar, BottomToolbar

        # Create toolbars
        self.top_toolbar = TopToolbar(
            app=self.app,
            title="Output",
            is_mobile=self.is_mobile
        )

        self.bottom_toolbar = BottomToolbar(
            app=self.app,
            is_mobile=self.is_mobile
        )

        # Auto-populate toolbars with commands
        self.populate_toolbar_with_commands(self.top_toolbar, context="normal")
        self.populate_toolbar_with_commands(self.bottom_toolbar, context="edit")

        # Set toolbars on view
        self.set_toolbars(self.top_toolbar, self.bottom_toolbar)

    # Command implementations
    def _rotate_left(self, widget):
        """Rotate image left"""
        logger.info("Rotating left")
        # Implementation here

    def _rotate_right(self, widget):
        """Rotate image right"""
        logger.info("Rotating right")
        # Implementation here

    def _crop(self, widget):
        """Crop image"""
        logger.info("Cropping")
        # Implementation here
```

### Step 2: That's It!

The system automatically:
- ✅ **Desktop**: Adds commands to native menus with keyboard shortcuts
- ✅ **Desktop**: Adds commands to custom toolbars
- ✅ **Mobile**: Adds commands to custom toolbars only
- ✅ **Both**: Handles platform differences transparently

## Platform-Specific Behavior

### Desktop Platform

Commands with `show_in_menu=True`:
- Added to native macOS/Windows/Linux menus
- Keyboard shortcuts work system-wide
- Appear in appropriate menu group (Edit, View, Window, etc.)

Commands with `show_in_toolbar=True`:
- Added to custom toolbars (or native Toga toolbar if desired)
- Can include icons and multi-line text

### Mobile Platform

Commands with `show_in_menu=True`:
- Ignored (mobile doesn't use native menus)

Commands with `show_in_toolbar=True`:
- Added to custom toolbars
- Touch-optimized sizing (44pt minimum target)
- Supports icons and labels

## FicheroCommand Properties

```python
FicheroCommand(
    id: str,                    # Unique ID (e.g., "output.rotate_left")
    label: str,                 # Human-readable label
    action: Callable,           # Function to execute
    shortcut: Optional[Any],    # toga.Key combination (desktop only)
    icon: Optional[str],        # Icon path
    toolbar_text: Optional[str], # Custom toolbar text (if different from label)
    toolbar_position: str,      # "left", "center", "right"
    show_in_menu: bool,         # Show in native menu (desktop only)
    show_in_toolbar: bool,      # Show in custom toolbar (both platforms)
    mobile_only: bool,          # Only show on mobile
    desktop_only: bool,         # Only show on desktop
    enabled: bool,              # Whether command is enabled
    description: Optional[str], # Longer description for tooltips
    group: Optional[toga.Group] # Menu group (EDIT, VIEW, WINDOW, etc.)
)
```

## Advanced Patterns

### Context-Specific Commands

Different commands for normal vs. edit mode:

```python
def define_commands(self):
    """Define commands with context awareness"""
    self.commands = {
        # Normal mode commands
        'view_zoom_in': FicheroCommand(
            id=f'{self.view_id}.zoom_in',
            label='Zoom In',
            action=self._zoom_in,
            shortcut=toga.Key.MOD_1 + '+',
            show_in_menu=True,
            show_in_toolbar=True,
            toolbar_position='right'
        ),

        # Edit mode commands (only shown in edit context)
        'edit_rotate': FicheroCommand(
            id=f'{self.view_id}.rotate',
            label='Rotate',
            action=self._rotate,
            show_in_menu=False,  # Not in menu
            show_in_toolbar=True,
            toolbar_position='center'
        )
    }

# Then populate toolbars with different contexts
self.populate_toolbar_with_commands(self.top_toolbar, context="normal")
self.populate_toolbar_with_commands(self.edit_toolbar, context="edit")
```

### Dynamic Command State

Enable/disable commands dynamically:

```python
# Disable a command
self.disable_command('rotate_left')

# Enable a command
self.enable_command('rotate_left')

# Or directly via command
command = self.get_command('rotate_left')
command.disable()
```

### Manual Command Retrieval

Access commands directly from registry:

```python
from fichero.shared.commands import CommandRegistry

registry = CommandRegistry.get_instance()
command = registry.get('output.rotate_left')
if command:
    command.execute()
```

### Native Toga Toolbar (Desktop Only)

For desktop-only native toolbars:

```python
from fichero.shared.commands import CommandManager

command_manager = CommandManager.get_instance(self.app)
command_manager.build_native_toolbar(
    self.window,
    command_ids=['output.rotate_left', 'output.rotate_right', 'output.crop']
)
```

## Command Naming Convention

Use hierarchical IDs with dots:

```
{view_id}.{category}.{action}
```

Examples:
- `output.edit.rotate_left`
- `output.view.zoom_in`
- `library.collection.add`
- `library.collection.delete`

## Testing Commands

```python
# Unit test example
def test_rotate_left_command():
    view = OutputView(app, is_mobile=False)

    # Get command
    cmd = view.get_command('rotate_left')
    assert cmd is not None

    # Verify properties
    assert cmd.label == 'Rotate Left'
    assert cmd.show_in_menu == True
    assert cmd.show_in_toolbar == True

    # Test execution
    result = cmd.execute(widget=None)
    # Assert expected result
```

## Migration Guide

### Old Pattern (Manual)

```python
# OLD: Manual toolbar button creation
def _setup_toolbar(self):
    self.toolbar = TopToolbar(app, title="Output")

    # Manually create each button
    self.toolbar.add_button_left(
        text="Rotate Left",
        icon="rotate_left.png",
        on_press=self._rotate_left
    )

    # Manually add to menu (desktop only)
    if not self.is_mobile:
        menu_item = toga.Command(
            action=self._rotate_left,
            text="Rotate Left",
            shortcut=toga.Key.MOD_1 + 'l',
            group=toga.Group.EDIT
        )
        self.app.commands.add(menu_item)
```

### New Pattern (Unified)

```python
# NEW: Define once, works everywhere
def define_commands(self):
    self.commands = {
        'rotate_left': FicheroCommand(
            id='output.rotate_left',
            label='Rotate Left',
            action=self._rotate_left,
            shortcut=toga.Key.MOD_1 + 'l',
            icon='rotate_left.png',
            show_in_menu=True,
            show_in_toolbar=True
        )
    }

def _setup_toolbar(self):
    self.register_commands()  # Registers with system
    self.populate_toolbar_with_commands(self.toolbar)  # Auto-populates
```

## Benefits

✅ **Single Source of Truth**: Commands defined once
✅ **Platform Agnostic**: No platform checks in view code
✅ **Automatic Routing**: Commands go to menus/toolbars automatically
✅ **Keyboard Shortcuts**: Desktop shortcuts work automatically
✅ **Easy Testing**: Commands are isolated and testable
✅ **Maintainable**: Change command properties in one place
✅ **Scalable**: Add new commands without modifying toolbar code

## Troubleshooting

### Commands Not Appearing in Menu (Desktop)

- Check `show_in_menu=True`
- Verify `CommandManager.get_instance(app)` called in app initialization
- Ensure `register_commands()` called after `define_commands()`

### Commands Not Appearing in Toolbar

- Check `show_in_toolbar=True`
- Verify `populate_toolbar_with_commands()` called
- Check `toolbar_position` property

### Keyboard Shortcuts Not Working

- Desktop only feature
- Check `shortcut` property is set
- Verify `show_in_menu=True` (shortcuts require menu registration)
- Check for shortcut conflicts

### Platform-Specific Issues

- Use `mobile_only=True` or `desktop_only=True` for platform-specific commands
- Check `is_mobile` detection in your app

## API Reference

See individual module documentation:
- `command.py` - FicheroCommand class
- `registry.py` - CommandRegistry singleton
- `command_manager.py` - CommandManager orchestrator
- `view_mixin.py` - ViewCommandMixin helper
