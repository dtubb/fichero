# Unified Command System - Quick Start

## TL;DR - The Pattern

```python
import toga
from fichero.shared.views.base_view import BaseView
from fichero.shared.commands import FicheroCommand, ViewCommandMixin

class MyView(BaseView, ViewCommandMixin):
    def __init__(self, app, is_mobile=False):
        self.view_id = "myview"  # REQUIRED: Set before super().__init__
        super().__init__(app, is_mobile)
        ViewCommandMixin.__init__(self)

        # 1. Define commands
        self.define_commands()

        # 2. Register with system
        self.register_commands()

        # 3. Auto-populate toolbars
        self._setup_toolbars()

    def define_commands(self):
        self.commands = {
            'action_name': FicheroCommand(
                id=f'{self.view_id}.action_name',
                label='Action Label',
                action=self._do_action,
                shortcut=toga.Key.MOD_1 + 'a',
                icon='resources/icons/icon.png',
                toolbar_position='center',  # left, center, right
                show_in_menu=True,          # Desktop: native menu
                show_in_toolbar=True        # Both: toolbar button
            )
        }

    def _setup_toolbars(self):
        self.top_toolbar = TopToolbar(self.app, is_mobile=self.is_mobile)
        self.populate_toolbar_with_commands(self.top_toolbar, context="normal")
        self.set_toolbars(self.top_toolbar)

    def _do_action(self, widget):
        # Your action implementation
        pass
```

## What This Gets You

✅ **Desktop**:
- Native menu item with keyboard shortcut (Cmd+A / Ctrl+A)
- Toolbar button with icon

✅ **Mobile**:
- Toolbar button with icon (no menu, shortcuts ignored)

✅ **Both**:
- One definition works everywhere
- No platform checks needed
- Automatic routing

## Key Properties

```python
FicheroCommand(
    id='view.action',           # Unique ID (hierarchical)
    label='Action',             # Menu text
    action=self._method,        # What to do
    shortcut=toga.Key.MOD_1+'a', # Desktop keyboard shortcut
    icon='path/to/icon.png',    # Toolbar icon
    toolbar_text='Custom\nText', # Multi-line toolbar text
    toolbar_position='center',  # left/center/right
    show_in_menu=True,          # Desktop: add to menu
    show_in_toolbar=True,       # Both: add to toolbar
    mobile_only=False,          # Only show on mobile
    desktop_only=False,         # Only show on desktop
    group=toga.Group.EDIT       # Menu group (optional)
)
```

## Common Patterns

### Edit Mode Commands

```python
# Normal mode toolbar
self.populate_toolbar_with_commands(self.top_toolbar, context="normal")

# Edit mode toolbar
self.populate_toolbar_with_commands(self.edit_toolbar, context="edit")
```

### Platform-Specific Commands

```python
# Mobile only (share button)
'share': FicheroCommand(
    id=f'{self.view_id}.share',
    label='Share',
    action=self._share,
    mobile_only=True
)

# Desktop only (export with dialog)
'export': FicheroCommand(
    id=f'{self.view_id}.export',
    label='Export...',
    action=self._export,
    desktop_only=True
)
```

### Dynamic State

```python
# Disable command
self.disable_command('rotate_left')

# Enable command
self.enable_command('rotate_left')

# Get command object
cmd = self.get_command('rotate_left')
```

## Files Created

- `command.py` - FicheroCommand class
- `registry.py` - CommandRegistry singleton
- `command_manager.py` - CommandManager (enhanced)
- `view_mixin.py` - ViewCommandMixin helper
- `example_view.py` - Complete working example
- `COMMAND_SYSTEM.md` - Full documentation
- `QUICK_START.md` - This file

## Next Steps

1. **Read**: `example_view.py` - complete working example
2. **Adapt**: Copy pattern to your view
3. **Test**: Run on desktop and mobile
4. **Refer**: `COMMAND_SYSTEM.md` for advanced usage

## Troubleshooting

**Commands not in menu?**
- Check `show_in_menu=True`
- Verify `register_commands()` called

**Commands not in toolbar?**
- Check `show_in_toolbar=True`
- Verify `populate_toolbar_with_commands()` called

**Shortcuts not working?**
- Desktop only feature
- Requires `show_in_menu=True`
- Check for conflicts with system shortcuts

## Migration from Old System

### Before (Manual)
```python
# Separate menu and toolbar setup
if not self.is_mobile:
    # Add to menu
    menu_item = toga.Command(...)
    self.app.commands.add(menu_item)

# Add to toolbar
self.toolbar.add_button(text="...", on_press=...)
```

### After (Unified)
```python
# Define once
self.commands = {
    'action': FicheroCommand(
        id='view.action',
        label='Action',
        action=self._action,
        show_in_menu=True,
        show_in_toolbar=True
    )
}
self.register_commands()
```

## Philosophy

**Define once, works everywhere.**

The command system eliminates boilerplate and platform checks.
Focus on your view logic, not UI plumbing.
