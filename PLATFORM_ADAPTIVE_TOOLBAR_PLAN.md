# Platform-Adaptive Toolbar Implementation Plan

## Goal

Views define commands once, and the toolbar system automatically routes them to the appropriate UI:
- **Desktop**: Native Toga toolbar (`window.toolbar`) + menus
- **Mobile**: Custom bottom toolbar

Views should NOT know or care about platform differences.

## Current Flow (What We Have)

```
LibraryView
    ├─ define_commands() ✅
    │   └─ Creates FicheroCommand objects
    ├─ register_commands() ✅
    │   └─ Calls CommandManager.register_view_commands()
    └─ _add_library_bottom_toolbar_buttons() ⚠️
        └─ Manually adds buttons to BottomToolbar
```

**Problem**: Views are manually adding buttons to BottomToolbar, which renders on both platforms.

## Desired Flow (What We Want)

```
LibraryView
    ├─ define_commands() ✅
    │   └─ Creates FicheroCommand objects
    └─ register_commands() ✅
        └─ CommandManager.register_view_commands()
            └─ CommandManager routes based on platform:
                ├─ Desktop: Adds to window.toolbar (native Toga toolbar)
                └─ Mobile: Adds to BottomToolbar (custom widgets)
```

Views only define commands. No manual button creation.

## Implementation Steps

### Step 1: Enhance BaseToolbar with `populate_from_commands()` ✅ (Already Exists)

BaseToolbar already has this method (from the audit):
```python
def populate_from_commands(self, view_id: str, context: str = "normal"):
    """Auto-populate toolbar with view's commands from CommandManager"""
    command_manager = CommandManager.get_instance(self.app)
    commands = command_manager.get_toolbar_commands(view_id=view_id, context=context)

    for command in commands:
        self.add_button_from_command(command)
```

### Step 2: Add `add_button_from_command()` to BaseToolbar

This method creates appropriate button from a FicheroCommand:

```python
def add_button_from_command(self, command: FicheroCommand):
    """Create button from FicheroCommand and add to toolbar"""
    try:
        # Determine position from command
        position = command.toolbar_position or 'center'

        # Create button using existing system
        self.add_regular_button(
            button_id=command.id,
            position=position,
            text=command.toolbar_text or command.label,
            icon=command.icon,  # Will be None on desktop if set that way
            on_press=lambda widget: command.execute(widget),
            tooltip=command.description
        )

        logger.debug(f"Added button for command: {command.id}")

    except Exception as e:
        logger.error(f"Failed to add button from command {command.id}: {e}")
```

### Step 3: Modify BaseView to Conditionally Render Bottom Toolbar

In BaseView.set_toolbars(), add platform check:

```python
def set_toolbars(self, top_toolbar=None, bottom_toolbar=None):
    """Set toolbars for this view"""
    try:
        # ... existing top toolbar logic ...

        # Bottom toolbar: Only on mobile
        if bottom_toolbar:
            if self.is_mobile:
                # Mobile: Populate bottom toolbar from commands
                if hasattr(self, 'view_id'):
                    bottom_toolbar.populate_from_commands(
                        view_id=self.view_id,
                        context='normal'  # Will update on mode change
                    )

                # Add to container
                toolbar_container = toga.Box(...)
                toolbar_container.add(bottom_toolbar.container)
                self.bottom_toolbar_container = toolbar_container
                self.container.add(self.bottom_toolbar_container)

            else:
                # Desktop: Don't render bottom toolbar
                logger.debug("Skipping bottom toolbar on desktop - using native toolbar")
                self.bottom_toolbar_container = None

    except Exception as e:
        logger.error(f"Failed to set toolbars: {e}")
```

### Step 4: Update LibraryView to Use Command-Based Approach

Remove `_add_library_bottom_toolbar_buttons()` entirely. Commands are already defined.

```python
class LibraryView(BaseView, ViewCommandMixin):
    def __init__(self, app, is_mobile=False):
        ...
        # Define and register commands
        self.define_commands()  # ✅ Already does this
        self.register_commands()  # ✅ Already does this

        # Create toolbars
        self.bottom_toolbar = BottomToolbar(app, is_mobile, coordinator)

        # NO MANUAL BUTTON ADDING!
        # self._add_library_bottom_toolbar_buttons()  ❌ Remove this

        # Set toolbars - BaseView handles platform routing
        self.set_toolbars(self.top_toolbar, self.bottom_toolbar)  # ✅ Automatic routing
```

### Step 5: MainWindow Updates Native Toolbar from Commands

MainWindow already does this (after our fixes):

```python
def _show_initial_view(self):
    library_view = self._get_or_create_library_view()

    # Desktop: Update native toolbar
    if not self.is_mobile:
        self._update_toolbar_for_library_view(context='normal')

    # Show view (BaseView handles bottom toolbar)
    self._show_view_desktop("library", library_view, "left")
```

## Platform Routing Logic

### Desktop Flow
```
LibraryView.define_commands()
    ↓
CommandManager.register_view_commands()
    ↓
MainWindow._update_toolbar_for_library_view()
    ↓
CommandManager.build_native_toolbar()
    ↓
window.toolbar.add(toga.Command(...))
    ↓
✅ Native macOS/Windows toolbar with menu items
```

### Mobile Flow
```
LibraryView.define_commands()
    ↓
CommandManager.register_view_commands()
    ↓
BaseView.set_toolbars(bottom_toolbar)
    ↓
bottom_toolbar.populate_from_commands(view_id='library')
    ↓
CommandManager.get_toolbar_commands(view_id='library', context='normal')
    ↓
bottom_toolbar.add_button_from_command(command)
    ↓
✅ Custom bottom toolbar with icon buttons
```

## Benefits

✅ **Single Definition**: Views only call `define_commands()` and `register_commands()`
✅ **Platform Agnostic**: Views don't know about desktop vs mobile
✅ **Automatic Routing**: CommandManager + BaseView handle platform differences
✅ **Context-Aware**: Commands filtered by context ('normal' vs 'edit')
✅ **Icon Handling**: Commands specify icons conditionally (`if is_mobile`)
✅ **No Manual Button Creation**: Buttons created automatically from commands

## Files to Modify

1. ✅ **LibraryView** - Remove `_add_library_bottom_toolbar_buttons()`
2. ⚠️ **BaseToolbar** - Add `add_button_from_command()` method
3. ⚠️ **BaseView** - Update `set_toolbars()` to conditionally render bottom toolbar
4. ✅ **MainWindow** - Already updates native toolbar (fixed earlier)
5. ✅ **CommandManager** - Already supports `build_native_toolbar()` and `get_toolbar_commands()`

## Implementation Order

1. Add `add_button_from_command()` to BaseToolbar
2. Update BaseView.set_toolbars() to:
   - Mobile: Call `bottom_toolbar.populate_from_commands()`
   - Desktop: Skip bottom toolbar entirely
3. Remove `_add_library_bottom_toolbar_buttons()` from LibraryView
4. Test on both platforms

## Expected Result

**Desktop**:
- Native window toolbar shows: Settings, Processing, About, Activity, Prompts, Plans
- Menu items work with keyboard shortcuts (if defined)
- NO bottom toolbar widget
- Edit mode switches toolbar to: Export, Bulk Import, Import URLs, etc.

**Mobile**:
- Custom bottom toolbar shows: Settings, Processing, About, Activity, Prompts, Plans (with icons)
- Tappable icon buttons
- NO native toolbar (platform limitation)
- Edit mode switches to: Export, Bulk Import, Import URLs, etc.

## Summary

The key insight is that **views should only define commands**, and the **platform-adaptive routing happens automatically** in:
1. `CommandManager` (for desktop native toolbar)
2. `BaseView.set_toolbars()` (for mobile custom toolbar)

Views become completely platform-agnostic! 🎉
