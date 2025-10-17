# LibraryView Wireframes - Desktop vs Mobile

## Command Code Review Summary

### How Commands Execute (Current Implementation)

```
User clicks toolbar button
    ↓
base_toolbar.py:483 - logged_action(widget) wrapper
    ↓
command.execute(widget) - ALWAYS passes widget parameter
    ↓
command.py:134 - self.action(*args, **kwargs)
    ↓
Handler method receives widget parameter
```

### The Problem

**Inconsistent handler signatures:**

✅ **LibraryView handlers** (correct):
```python
def _on_add_collection(self, widget=None):      # Line 514
def _on_open_settings_window(self, widget=None): # Line 1642
def _on_open_processing_window(self, widget=None): # Line 1647
```

❌ **CollectionView handlers** (broken):
```python
def _on_add_folder(self):        # Line 289 - NO widget parameter!
def _on_add_file(self):          # Line 327 - NO widget parameter!
def _on_add_dialog_requested(self): # Line 1110 - NO widget parameter!
```

**Error Result:**
```
ERROR - ❌ Error executing command collection.add_folder:
CollectionView._on_add_folder() takes 1 positional argument but 2 were given
```

### The Fix

All command handlers must accept an optional `widget=None` parameter to be compatible with toolbar execution.

---

## LibraryView Layout - Desktop Mode

### Window Structure (Three-Pane Layout)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Fichero - Library                                        ⊗ ⊖ ⊕          │
├─────────────────────────────────────────────────────────────────────────┤
│ File    Edit    View    Window                                          │
│ ┌─────────────────┐  ┌────────────────┐  ┌──────────────┐  ┌─────────┐ │
│ │ + Collection    │  │ Import File    │  │ Import Folder│  │ Import  │ │
│ └─────────────────┘  └────────────────┘  └──────────────┘  └─────────┘ │
├────────────────┬──────────────────────────────────────────┬─────────────┤
│                │                                          │             │
│  COLLECTIONS   │       COLLECTION DETAILS                 │   PREVIEW   │
│                │                                          │             │
│  📚 Documents  │  Collection: Documents                   │             │
│     (25)       │  Type: Local                             │   [Image/   │
│                │  Items: 25                               │    Text     │
│  📚 Photos     │                                          │   Preview]  │
│     (102)      │  ┌────────────────────────────┐          │             │
│                │  │ 📄 Document 1              │          │             │
│  📚 Archives   │  ├────────────────────────────┤          │             │
│     (8)        │  │ 📄 Document 2              │          │             │
│                │  ├────────────────────────────┤          │             │
│  + New         │  │ 📄 Document 3              │          │             │
│                │  └────────────────────────────┘          │             │
│                │                                          │             │
│                │  [Process] [Export] [Properties]         │             │
│                │                                          │             │
└────────────────┴──────────────────────────────────────────┴─────────────┘
```

### Desktop Command Placement

#### Native Menu Bar (app.commands):

**File Menu (GROUP.FILE):**
- New Collection (⌘N)
- Import File (⌘O)
- Import Folder (⌘⇧O)
- Import from URL (⌘U)
- Export Collection (⌘E)

**Edit Menu (GROUP.EDIT):**
- [Edit mode commands appear here when item selected]
- Delete Item (⌘⌫)
- Rename Item (⌘R)
- Edit Metadata (⌘I)

**View Menu (GROUP.VIEW):**
- Refresh View (⌘R)
- Toggle Preview (⌘P)

**Window Menu (GROUP.WINDOW):**
- Settings (⌘,)
- Activity Monitor (⌘⇧A)
- Processing Queue (⌘⇧P)
- Prompts Manager (⌘⇧M)
- Plans Manager (⌘⇧L)
- About (⌘⇧?)

#### Native Toolbar (top of window):
- **Position: Left**
  - + Collection
- **Position: Center**
  - Import File
  - Import Folder
  - Import URL
- **Position: Right**
  - [Context-specific actions]

---

## LibraryView Layout - Mobile Mode

### Window Structure (Single-Pane Layout with Bottom Toolbar)

```
┌─────────────────────────────────────────┐
│ ← Library                          ≡    │
├─────────────────────────────────────────┤
│                                         │
│  COLLECTIONS LIST                       │
│  (Full screen, swipeable)               │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │ 📚 Documents            (25) >   │  │
│  ├───────────────────────────────────┤  │
│  │ 📚 Photos               (102) >  │  │
│  ├───────────────────────────────────┤  │
│  │ 📚 Archives             (8) >    │  │
│  ├───────────────────────────────────┤  │
│  │                                   │  │
│  │                                   │  │
│  │                                   │  │
│  │                                   │  │
│  │                                   │  │
│  └───────────────────────────────────┘  │
│                                         │
│                                         │
├─────────────────────────────────────────┤
│ [+] [📁] [📄] [🔗]  [⚙️] [📊] [🔔] [?] │
│ Add File Fold URL  Set Act Proc About  │
└─────────────────────────────────────────┘
```

### Mobile Command Placement

#### NO Native Menu Bar
(Mobile platforms don't have native menus)

#### Bottom Toolbar (9 buttons):

**Position: Left**
- ➕ Add Collection (`show_in_bottom_toolbar=True`)

**Position: Center**
- 📄 Import File (`show_in_bottom_toolbar=True`)
- 📁 Import Folder (`show_in_bottom_toolbar=True`)
- 🔗 Import URL (`show_in_bottom_toolbar=True`)

**Position: Right**
- ⚙️ Settings (`show_in_bottom_toolbar=True`)
- 📊 Activity Monitor (`show_in_bottom_toolbar=True`)
- 🔔 Processing Queue (`show_in_bottom_toolbar=True`)
- ℹ️ About (`show_in_bottom_toolbar=True`)

#### Edit Mode (when item selected):
Bottom toolbar transforms to show edit commands:
```
┌─────────────────────────────────────────┐
│ ← Back                      Cancel      │
├─────────────────────────────────────────┤
│                                         │
│  ITEM DETAIL VIEW                       │
│  (Selected item expanded)               │
│                                         │
│  📄 Document 1                          │
│                                         │
│  Preview:                               │
│  [Image/Text Preview]                   │
│                                         │
│  Properties:                            │
│  Type: PDF                              │
│  Size: 2.5 MB                           │
│  Modified: Oct 9, 2025                  │
│                                         │
├─────────────────────────────────────────┤
│ [🗑️] [✏️] [ℹ️]    [⚙️] [📊] [🔔] [?] │
│ Del Edit Info     Set Act Proc About   │
└─────────────────────────────────────────┘
```

**Edit Mode Commands (context="edit"):**
- 🗑️ Delete Item
- ✏️ Rename Item
- ℹ️ Edit Metadata

**Persistent Commands (always visible):**
- ⚙️ Settings
- 📊 Activity Monitor
- 🔔 Processing Queue
- ℹ️ About

---

## Key Architectural Differences

### Desktop
- **Three-pane layout**: Collections | Details | Preview
- **Native menu bar**: Commands organized into File/Edit/View/Window menus
- **Native toolbar**: Top toolbar with 3-4 most common actions
- **Context menus**: Right-click for additional actions
- **Keyboard shortcuts**: All commands have shortcuts

### Mobile
- **Single-pane layout**: One view at a time, navigation stack
- **Bottom toolbar**: 9 buttons for primary actions
- **Mode switching**: Normal mode → Edit mode changes toolbar
- **Touch gestures**: Swipe to navigate, long-press for context
- **No keyboard shortcuts**: Touch-only interface

---

## Command Registration Pattern

### Desktop Commands
```python
FicheroCommand(
    id='library.add_collection',
    label=_("Add Collection"),
    action=self._on_add_collection,
    group=toga.Group.FILE,           # Shows in File menu
    show_in_menu=True,                # ✅ Appear in native menu
    show_in_toolbar=True,             # ✅ Appear in top toolbar
    show_in_bottom_toolbar=False,     # ❌ Not on mobile toolbar
    toolbar_position='left',
    mobile_only=False,                # Available on all platforms
)
```

### Mobile Commands
```python
FicheroCommand(
    id='library.settings',
    label=_("Settings"),
    action=self._on_open_settings_window,
    group=toga.Group.WINDOW,          # Would be in Window menu on desktop
    show_in_menu=True,                # Would show in menu if platform had menus
    show_in_toolbar=False,            # ❌ Not in desktop toolbar
    show_in_bottom_toolbar=True,      # ✅ Show in mobile bottom toolbar
    toolbar_position='right',
    mobile_only=False,                # Available on all platforms
)
```

### Edit Mode Commands
```python
FicheroCommand(
    id='collection.delete_item',
    label=_("Delete"),
    action=self._on_delete_item,
    context='edit',                   # ✅ Only in edit mode
    group=toga.Group.EDIT,
    show_in_menu=True,
    show_in_bottom_toolbar=True,      # Shows when edit mode active
    toolbar_position='left',
)
```

---

## Navigation Flows

### Desktop Navigation
```
Library View (always visible)
    ├─ Select collection → Details pane updates
    ├─ Select item → Preview pane updates
    └─ Open window command → New window opens (Settings, Activity, etc.)
```

### Mobile Navigation
```
Library View (Collections List)
    ↓ Tap collection
Collection Detail View (Items List)
    ↓ Tap item
Item Detail View (Preview + Properties)
    ↓ Tap Edit
Edit Mode (Transform toolbar to show edit commands)
    ↓ Back button
Return to previous view
```

### Mobile Navigation Issue (CURRENT BUG)
```
Library View
    ↓ Tap "Import File" button
ERROR: 'NavigationController' object has no attribute 'push_view'
    ❌ Navigation fails
```

**Expected behavior:**
```python
# CollectionView is trying to navigate:
self.navigation_controller.push_view(file_import_view)  # ❌ Wrong method

# Should be:
self.app.navigation.push(file_import_view)  # ✅ Correct method
```

---

## Next Steps

1. **Fix handler signatures**: Add `widget=None` to all CollectionView handlers
2. **Fix navigation**: Replace `push_view` with correct navigation API
3. **Test desktop mode**: Verify commands in menus and toolbar
4. **Test mobile mode**: Verify bottom toolbar and edit mode switching
5. **Test edit mode**: Verify toolbar transforms correctly when selecting items
