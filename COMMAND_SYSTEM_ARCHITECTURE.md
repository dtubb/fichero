# Command System Architecture
**Date**: October 9, 2025

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FICHERO COMMAND SYSTEM                       │
└─────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  VIEW LAYER (LibraryView, CollectionView, OutputView)             │
│                                                                     │
│  1. View.__init__()                                                │
│     ├─> super().__init__(app, is_mobile)  [Sets self.app]         │
│     ├─> self.define_commands()            [Creates FicheroCommand] │
│     ├─> self.register_commands()          [Sends to CommandManager]│
│     └─> self._setup_toolbars()            [Creates UI buttons]    │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  COMMAND MANAGER (Singleton, Platform-Aware)                       │
│                                                                     │
│  register_command(command: FicheroCommand)                         │
│     ├─> CommandRegistry.register(command)  [Central storage]      │
│     │                                                              │
│     ├─> if show_in_menu + desktop:                                │
│     │      Create toga.Command → app.commands [Native menus]      │
│     │                                                              │
│     └─> if show_in_*_toolbar:                                     │
│            Command available for toolbar population                │
│                                                                     │
│  build_native_toolbar(window, view_id, context, mode='add')       │
│     └─> Populates window.toolbar with accumulated commands        │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  PLATFORM ROUTING                                                  │
│                                                                     │
│  DESKTOP (is_mobile=False)                                         │
│  ├─ Native Menus (app.commands)                                   │
│  │   └─ Commands with show_in_menu=True                           │
│  │      Grouped by: View, Edit, File, Window                      │
│  │                                                                 │
│  └─ Native Toolbar (window.toolbar)                               │
│      └─ Commands with show_in_bottom_toolbar=True                 │
│         Accumulated across views (add mode)                        │
│                                                                     │
│  MOBILE (is_mobile=True)                                           │
│  └─ Bottom Toolbar (custom widget)                                │
│      └─ Commands with show_in_bottom_toolbar=True                 │
│         Context-aware (normal/edit modes)                          │
└────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow: Command Registration

```
┌──────────────────────────────────────────────────────────────────┐
│  Step 1: View Defines Commands                                   │
└──────────────────────────────────────────────────────────────────┘

LibraryView.define_commands():
  self.commands = {
    'settings': FicheroCommand(
      id='library.settings',
      label='Settings',
      action=self._on_open_settings_window,
      group=toga.Group.WINDOW,        # ← Menu grouping
      show_in_menu=True,               # ← Desktop menu
      show_in_bottom_toolbar=True,     # ← Mobile toolbar
      mobile_only=False                # ← Both platforms
    ),
    ...
  }

         │
         ▼

┌──────────────────────────────────────────────────────────────────┐
│  Step 2: View Registers Commands                                 │
└──────────────────────────────────────────────────────────────────┘

LibraryView.register_commands():
  command_manager = CommandManager.get_instance(self.app)
  command_manager.register_view_commands(
    view_id='library',
    commands=self.commands
  )

         │
         ▼

┌──────────────────────────────────────────────────────────────────┐
│  Step 3: CommandManager Processes Each Command                   │
└──────────────────────────────────────────────────────────────────┘

CommandManager.register_command(command):

  # 1. Store in registry (always)
  CommandRegistry.register(command.id, command)

  # 2. Platform filtering
  if command.mobile_only and not self.is_mobile:
    return  # Skip mobile-only commands on desktop

  if command.desktop_only and self.is_mobile:
    return  # Skip desktop-only commands on mobile

  # 3. Create native menu item (desktop only)
  if command.show_in_menu and not self.is_mobile:
    toga_command = toga.Command(
      action=command.action,
      text=command.label,
      shortcut=command.shortcut,
      group=command.group,  # View/Edit/File/Window
      enabled=command.enabled
    )
    self.app.commands.add(toga_command)

  # 4. Command is now available for toolbars
  # (will be picked up by build_native_toolbar() or BottomToolbar)

         │
         ▼

┌──────────────────────────────────────────────────────────────────┐
│  Step 4: Toolbar Population (When View Shown)                    │
└──────────────────────────────────────────────────────────────────┘

MainWindow._update_toolbar_for_library_view():
  command_manager.build_native_toolbar(
    window=self.window,
    view_id='library',
    context='normal',
    mode='add'  # Accumulate commands
  )

CommandManager.build_native_toolbar():

  # Get commands for this view
  toolbar_commands = [
    cmd for cmd in CommandRegistry.get_all()
    if cmd.view_id == view_id
    and cmd.show_in_bottom_toolbar
    and cmd.context == context
  ]

  # Filter by platform
  toolbar_commands = [
    cmd for cmd in toolbar_commands
    if not (cmd.mobile_only and not is_mobile)
    and not (cmd.desktop_only and is_mobile)
  ]

  # Add to native toolbar (desktop accumulates)
  for cmd in toolbar_commands:
    if mode == 'add':
      if cmd.id not in existing_ids:
        window.toolbar.add(create_toga_command(cmd))
    elif mode == 'replace':
      window.toolbar.clear()
      window.toolbar.add(create_toga_command(cmd))
```

---

## Command Flow by Platform

### Desktop Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         DESKTOP (macOS)                          │
└─────────────────────────────────────────────────────────────────┘

View Registration
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│  Command with show_in_menu=True                                 │
│  ├─> Creates toga.Command                                       │
│  └─> Added to app.commands                                      │
│      └─> Appears in native menu bar                             │
│          Group.VIEW → "View" menu                               │
│          Group.EDIT → "Edit" menu                               │
│          Group.FILE → "File" menu                               │
│          Group.WINDOW → "Window" menu                           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Command with show_in_bottom_toolbar=True                       │
│  └─> Available for window.toolbar                               │
│      └─> build_native_toolbar() adds to window.toolbar          │
│          Accumulated across views (LibraryView + CollectionView)│
└─────────────────────────────────────────────────────────────────┘

Example: Settings Command
  show_in_menu=True + group=Window → "Window > Settings" menu item
  show_in_bottom_toolbar=True + mobile_only=False → NOT in desktop toolbar
  (Window navigation via menu, not toolbar, follows macOS HIG)
```

### Mobile Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    MOBILE (iOS/Android)                         │
└─────────────────────────────────────────────────────────────────┘

View Registration
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│  Command with show_in_menu=True                                 │
│  └─> IGNORED (mobile doesn't use native menus)                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Command with show_in_bottom_toolbar=True                       │
│  └─> Added to BottomToolbar (custom widget)                     │
│      └─> toolbar.populate_from_commands(view_id, context)       │
│          Context-aware: normal vs edit modes                    │
│          Per-view (not accumulated)                             │
└─────────────────────────────────────────────────────────────────┘

Example: Settings Command
  show_in_menu=True → Ignored (no native menus)
  show_in_bottom_toolbar=True + mobile_only=False → Button in bottom toolbar
  (Window navigation via toolbar buttons, follows mobile UX patterns)
```

---

## Command Lifecycle by View

### LibraryView Commands (14 total)

```
┌─────────────────────────────────────────────────────────────────┐
│  DESKTOP TOOLBAR (window.toolbar)                               │
│  ─────────────────────────────────────────────────────────────  │
│  [Add File] [Add Folder] [Add URL]                             │
│                                                                  │
│  Group: View (3 commands)                                       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  DESKTOP WINDOW MENU                                            │
│  ─────────────────────────────────────────────────────────────  │
│  Window                                                          │
│  ├─ Settings                                                    │
│  ├─ Processing                                                  │
│  ├─ About                                                       │
│  ├─ Activity                                                    │
│  ├─ Prompts                                                     │
│  └─ Plans                                                       │
│                                                                  │
│  (6 commands in Window menu)                                    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  MOBILE BOTTOM TOOLBAR (normal mode)                            │
│  ─────────────────────────────────────────────────────────────  │
│  [Add File] [Add Folder] [Add URL]                             │
│  [Settings] [Processing] [About] [Activity] [Prompts] [Plans]  │
│                                                                  │
│  (9 buttons in normal mode)                                     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  MOBILE BOTTOM TOOLBAR (edit mode)                              │
│  ─────────────────────────────────────────────────────────────  │
│  [Export] [Bulk Import] [Import URLs] [Import Files] [Folder]  │
│                                                                  │
│  (5 buttons in edit mode - mobile_only)                         │
└─────────────────────────────────────────────────────────────────┘
```

### CollectionView Commands

```
┌─────────────────────────────────────────────────────────────────┐
│  DESKTOP TOOLBAR (accumulated with LibraryView)                 │
│  ─────────────────────────────────────────────────────────────  │
│  [Add File] [Add Folder] [Add URL] [Process] [Add File] [Folder]│
│                                                                  │
│  LibraryView: 3 + CollectionView: 3 = 6 total                  │
│  Group: View (3) + Edit (3)                                     │
└─────────────────────────────────────────────────────────────────┘
```

### OutputView Commands (15 total)

```
┌─────────────────────────────────────────────────────────────────┐
│  DESKTOP TOOLBAR (accumulated)                                  │
│  ─────────────────────────────────────────────────────────────  │
│  [Previous commands...] [Rotate L] [Rotate R] [Crop] [Reset]   │
│                                                                  │
│  Group: File (4 edit mode commands)                             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  DESKTOP EDIT MENU                                              │
│  ─────────────────────────────────────────────────────────────  │
│  Edit                                                            │
│  ├─ Rotate Left     (Cmd+L)                                    │
│  ├─ Rotate Right    (Cmd+R)                                    │
│  ├─ Crop Image      (Cmd+K)                                    │
│  └─ Reset Original  (Cmd+0)                                    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  DESKTOP VIEW MENU                                              │
│  ─────────────────────────────────────────────────────────────  │
│  View                                                            │
│  ├─ Zoom In         (Cmd++)                                    │
│  ├─ Zoom Out        (Cmd+-)                                    │
│  ├─ Zoom to Fit     (Cmd+9)                                    │
│  ├─ Actual Size     (Cmd+0)                                    │
│  ├─ Fit Width       (Cmd+Shift+0)                              │
│  ├─ Fit Height      (Cmd+Shift+9)                              │
│  └─ Zoom Selection  (Cmd+Shift+8)                              │
│                                                                  │
│  (7 zoom commands in View menu)                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  DESKTOP WINDOW MENU                                            │
│  ─────────────────────────────────────────────────────────────  │
│  Window                                                          │
│  ├─ Previous File   (Cmd+↑)                                    │
│  ├─ Next File       (Cmd+↓)                                    │
│  ├─ Previous Step   (Cmd+←)                                    │
│  └─ Next Step       (Cmd+→)                                    │
│                                                                  │
│  (4 navigation commands in Window menu)                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Current vs Should Work

### ✅ CURRENT STATE (After Fixes)

```
DESKTOP
├─ Window Menu
│  ├─ Settings ✅
│  ├─ Processing ✅
│  ├─ About ✅
│  ├─ Activity ✅
│  ├─ Prompts ✅
│  └─ Plans ✅
│
├─ View Menu
│  └─ LibraryView: Add File, Add Folder, Add URL (3 items)
│
├─ Edit Menu
│  └─ OutputView: Rotate L/R, Crop, Reset (4 items)
│
└─ Native Toolbar
   └─ Accumulated commands from all views

MOBILE
└─ Bottom Toolbar
   ├─ Normal mode: 9 buttons (Add + Window nav)
   └─ Edit mode: 5 buttons (Import options)
```

### ❌ PREVIOUS STATE (Before Fixes)

```
DESKTOP
├─ Window Menu
│  └─ (empty - no navigation commands!) ❌
│
├─ OutputView
│  └─ Crashed on initialization ❌
│
└─ Window navigation
   └─ No way to access Settings/Processing/etc! ❌
```

---

## Platform Filtering Logic

```python
def should_show_command(command, is_mobile):
    """Determine if command should be shown on current platform"""

    # Filter mobile-only commands on desktop
    if command.mobile_only and not is_mobile:
        return False

    # Filter desktop-only commands on mobile
    if command.desktop_only and is_mobile:
        return False

    # Command is platform-compatible
    return True

def get_toolbar_commands(view_id, context, is_mobile):
    """Get commands for toolbar population"""

    all_commands = CommandRegistry.get_all()

    # Filter by view and context
    commands = [
        cmd for cmd in all_commands
        if cmd.view_id == view_id
        and cmd.context == context
        and cmd.show_in_bottom_toolbar
    ]

    # Filter by platform
    commands = [
        cmd for cmd in commands
        if should_show_command(cmd, is_mobile)
    ]

    return commands

def create_menu_items(is_mobile):
    """Create native menu items (desktop only)"""

    if is_mobile:
        return []  # Mobile doesn't use native menus

    all_commands = CommandRegistry.get_all()

    # Filter commands that should be in menus
    menu_commands = [
        cmd for cmd in all_commands
        if cmd.show_in_menu
        and should_show_command(cmd, is_mobile)
    ]

    # Group by toga.Group
    grouped = {}
    for cmd in menu_commands:
        group = cmd.group or toga.Group.VIEW
        if group not in grouped:
            grouped[group] = []
        grouped[group].append(cmd)

    return grouped
```

---

## Testing Matrix

| View | Platform | Mode | Expected Commands | Location |
|------|----------|------|-------------------|----------|
| Library | Desktop | Normal | Add File, Folder, URL | Toolbar (3) |
| Library | Desktop | Normal | Settings, Processing, etc | Window Menu (6) |
| Library | Mobile | Normal | Add + Window nav | Bottom Toolbar (9) |
| Library | Mobile | Edit | Export, Bulk, URLs, etc | Bottom Toolbar (5) |
| Collection | Desktop | Normal | Previous + Process, Add | Toolbar (6 accumulated) |
| Output | Desktop | Normal | Previous + Edit commands | Toolbar (10 accumulated) |
| Output | Desktop | Normal | Zoom commands | View Menu (7) |
| Output | Desktop | Normal | Edit commands | Edit Menu (4) |
| Output | Desktop | Normal | Navigation | Window Menu (4) |

---

**Status**: Architecture matches implementation after fixes ✅
**Next**: Unit tests to verify all command flows work correctly
