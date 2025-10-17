# LibraryView Command System Migration

**Date**: October 8, 2025
**Status**: ✅ COMPLETE

## What Was Accomplished

### 1. Added Command System Support to LibraryView

**Changes Made**:
- Added `ViewCommandMixin` to LibraryView class inheritance
- Set `view_id = "library"` before `super().__init__()`
- Initialized `ViewCommandMixin` after `BaseView.__init__()`
- Called `define_commands()` and `register_commands()` in `__init__`

**Files Modified**:
- `/Users/dtubb/code/fichero_main/fichero/src/fichero/windows/main/views/library/library_view.py`

### 2. Defined All LibraryView Commands

**Top Toolbar Commands** (1 command):
- `edit` - Toggle edit mode (right-aligned button)

**Bottom Toolbar - Normal Mode** (6 commands):
- `settings` - Open settings window
- `processing` - Open processing window
- `about` - Open about window (icon on mobile only!)
- `activity` - Open activity monitor
- `prompts` - Open prompts window
- `plans` - Open plans window

**Bottom Toolbar - Edit Mode** (5 commands):
- `export` - Export selected collection
- `bulk_import` - Bulk import items
- `import_urls` - Import from URLs
- `import_files` - Import files (platform-specific)
- `import_folder` - Import folder (platform-specific)

**Total**: 12 commands defined

### 3. Enhanced FicheroCommand Class

**New Parameters Added**:
- `toolbar_position: Optional[str]` - Position in toolbar ('left', 'center', 'right')
- `context: str = 'normal'` - Context for command visibility ('normal', 'edit', etc.)

**Files Modified**:
- `/Users/dtubb/code/fichero_main/fichero/src/fichero/shared/commands/command.py`

## Platform-Specific Icon Handling

**Key Decision**: About button uses icon on mobile only:

```python
'about': FicheroCommand(
    id=f'{self.view_id}.about',
    label=_("About"),
    action=self._on_open_about_window,
    icon='resources/icons/toolbar/help.png' if self.is_mobile else None,  # Icon on mobile only!
    ...
)
```

This pattern applies to all bottom toolbar buttons:
- **Desktop**: Text-only buttons (no icons) for cleaner look
- **Mobile**: Icon buttons for touch-optimized UI

## Command Registration Flow

```
LibraryView.__init__()
    ↓
Set view_id = "library"
    ↓
super().__init__(app, is_mobile)
ViewCommandMixin.__init__(self)
    ↓
define_commands()  # Creates self.commands dict
    ↓
register_commands()  # Registers with CommandManager
    ↓
CommandManager routes commands:
    - Desktop: Native menus (if show_in_menu=True)
    - Desktop: Native toolbar (if show_in_toolbar=True)
    - Mobile: Custom toolbars only (show_in_menu ignored)
```

## Context-Aware Commands

Commands are tagged with `context` to control when they appear:

- **context='normal'**: Shown in normal mode (default)
  - Settings, Processing, About, Activity, Prompts, Plans

- **context='edit'**: Shown in edit mode only
  - Export, Bulk Import, Import URLs, Import Files, Import Folder

The toolbar system can filter commands by context:

```python
# Get commands for normal mode
normal_commands = command_manager.get_toolbar_commands(
    view_id="library",
    context="normal"
)

# Get commands for edit mode
edit_commands = command_manager.get_toolbar_commands(
    view_id="library",
    context="edit"
)
```

## Integration with Existing Toolbar System

LibraryView still uses the existing ToolbarCoordinator and custom toolbars:

```python
# Existing toolbar system (unchanged for now)
self.coordinator = ToolbarCoordinator(app, is_mobile=is_mobile)
self.top_toolbar = TopToolbar(...)
self.bottom_toolbar = BottomToolbar(...)

# New: Commands are also registered with CommandManager
# This enables future native toolbar integration
```

**Why Both Systems?**
1. **Gradual Migration**: Commands are defined and registered, but existing custom toolbars still work
2. **Future-Ready**: When MainWindow implements native toolbar routing, it can use the registered commands
3. **No Breaking Changes**: Current mobile UI continues to work with custom toolbars

## Next Steps

### Immediate (Next Task)
1. **Implement native Toga toolbar for desktop**:
   - Update MainWindow to use `window.toolbar` on desktop
   - Route toolbar commands through CommandManager
   - Keep custom toolbars for mobile

2. **Update toolbar display logic**:
   - Normal mode: Show normal-context commands
   - Edit mode: Show edit-context commands
   - Use CommandManager to filter by context

### Testing Requirements

**Desktop Testing**:
- [ ] Verify Edit button appears in top-right of library view
- [ ] Verify bottom toolbar buttons show as text-only (no icons)
- [ ] Verify About button has NO icon on desktop
- [ ] Verify edit mode switches to edit commands (Export, Import, etc.)
- [ ] Verify native toolbar integration (when implemented)

**Mobile Testing**:
- [ ] Verify Edit button appears in top toolbar
- [ ] Verify bottom toolbar buttons show with icons
- [ ] Verify About button HAS icon on mobile
- [ ] Verify edit mode switches to edit commands
- [ ] Verify custom toolbars continue to work

## Code Pattern for Other Views

Other views (CollectionView, etc.) can follow this pattern:

```python
from fichero.shared.commands import FicheroCommand, ViewCommandMixin

class MyView(BaseView, ViewCommandMixin):
    def __init__(self, app, is_mobile=False):
        # Set view_id BEFORE super().__init__
        self.view_id = "myview"

        super().__init__(app, is_mobile)
        ViewCommandMixin.__init__(self)

        # Define and register commands
        self.define_commands()
        self.register_commands()

        # Rest of initialization...

    def define_commands(self):
        """Define all commands for this view"""
        from fichero.i18n import _

        self.commands = {
            'action': FicheroCommand(
                id=f'{self.view_id}.action',
                label=_("Action"),
                action=self._on_action,
                icon='icon.png' if self.is_mobile else None,
                show_in_menu=True,      # Desktop menu
                show_in_toolbar=True,   # Both platforms
                toolbar_position='center',
                context='normal'
            ),
            # ... more commands
        }
```

## Benefits of This Approach

✅ **Single Source of Truth**: Commands defined once in `define_commands()`
✅ **Platform-Adaptive**: Automatic icon handling for mobile vs desktop
✅ **Context-Aware**: Commands filtered by context (normal/edit)
✅ **Future-Proof**: Ready for native toolbar integration
✅ **Non-Breaking**: Existing custom toolbars continue to work
✅ **Testable**: Commands are isolated and can be tested independently
✅ **Maintainable**: Change command properties in one place

## Command System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ LibraryView                                                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  define_commands()                                           │
│    ├─ Creates FicheroCommand objects                        │
│    ├─ Sets platform-specific icons                          │
│    └─ Tags with context (normal/edit)                       │
│                                                              │
│  register_commands()                                         │
│    └─ Calls CommandManager.register_view_commands()         │
│                                                              │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ CommandManager                                               │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  register_view_commands(view_id, commands)                  │
│    ├─ Stores in CommandRegistry                             │
│    ├─ Desktop: Creates toga.Command for menus               │
│    └─ Desktop: Prepares for native toolbar                  │
│                                                              │
│  get_toolbar_commands(view_id, context)                     │
│    └─ Filters commands by context                           │
│                                                              │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ├─────────────────┬──────────────────┐
                       ▼                 ▼                  ▼
              ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
              │ Desktop Menu  │  │ Native       │  │ Custom       │
              │ (if enabled)  │  │ Toolbar      │  │ Toolbars     │
              │               │  │ (future)     │  │ (mobile)     │
              └──────────────┘  └──────────────┘  └──────────────┘
```

## Summary

✅ **LibraryView now fully integrated with unified command system**
- All 12 toolbar buttons defined as FicheroCommand objects
- Commands registered with CommandManager
- Platform-specific icon handling implemented
- Context-aware command filtering enabled

🎯 **Ready for next step**: Implement native Toga toolbar for desktop in MainWindow

📝 **Documentation**: This file serves as reference for future view migrations
