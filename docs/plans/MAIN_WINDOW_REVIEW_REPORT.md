# Main Window Code Review Report

Systematic review of `/src/fichero/app/main_window/` for clarity, Pythonic patterns, and best practices.

## Summary

| File | Lines | Grade | Changes Made |
|------|-------|-------|--------------|
| window.py | 672 | A | Commands extracted, legacy removed, clean |
| commands.py | 224 | A | NEW - centralized menu/toolbar handlers |
| __init__.py | 19 | A | Simplified - just exports |
| sidebar.py | 746 | A | Already well-structured, db helpers exist |
| browser.py | 557 | A | Already clean |
| tabs.py | 458 | A | Used `dataclasses.replace()` |
| tab_controller.py | 582 | A | Uses isinstance(), SessionState persistence |
| editor.py | 285 | A | Rewritten - simple dispatch, no registry |
| inspector.py | 533 | B+ | Fixed isinstance() for type detection |
| menu.py | 302 | A | Frozen dataclasses, clean patterns |
| toolbar.py | 296 | A | Pattern matching, objc_property |
| editors/__init__.py | 51 | A | Simplified exports |
| editors/image_viewer.py | 306 | A | Rewritten - WKWebView + HTML viewer |
| editors/text_viewer.py | 130 | A | Removed registry |
| editors/table_viewer.py | 204 | A | Removed registry |
| **Total** | ~5,135 | | ~650 lines saved total |

## Changes Made

### 1. window.py (1109 → 672 lines, -437)

**Round 1 Removed:**
- Legacy window creation mode (`_create_window`, `_create_split_view`)
- Print statements → use logger
- User said no backwards compatibility

**Round 2 (Pythonic Review) Removed:**
- ~350 lines of menu handler methods → moved to commands.py
- Unused imports (`sys`, `webbrowser`, `NSOpenPanel`, `NSApplication`)
- Legacy fallback code in `toggle_pane` and `is_pane_visible`
- `_saved_widths` dict (pane widths managed by NSSplitView.autosaveName)
- `_on_resize` stub (NSSplitView handles this)
- Duplicate sidebar loading code (consolidated into `reload_sidebar()`)
- Unused `Workflow` import
- TODOs converted to empty implementations

**Result:**
- Clean separation: window manages layout, Commands handles actions
- No legacy fallbacks - single code path with NSSplitViewController
- 672 lines of tight, focused code

### 1b. commands.py (NEW - 224 lines)

Centralized command handlers for menu and toolbar:

```python
class Commands:
    def __init__(self, window: MainWindowController):
        self.window = window

    # View Menu - Pane Toggles
    def toggle_library(self):
        self.window.toggle_pane('sidebar')

    # View Menu - Zoom (forwarded to editor)
    def zoom_in(self):
        self.window.editor.zoom_in()
```

**Handlers included:**
- App Menu: about, settings, hide, quit
- File Menu: import_file, import_folder, close_window
- View Menu: toggle_* panes, zoom_*, rotate_*, magnifier_*
- Window Menu: minimize
- Help Menu: visit_homepage
- Toolbar: settings, process

### 1c. __init__.py (54 → 19 lines, -35)

Removed:
- Legacy `MainWindow` class wrapper
- `create_main_window()` factory function
- `USE_NATIVE_WINDOW` flag

Now just:
```python
from fichero.app.main_window.window import MainWindowController
__all__ = ["MainWindowController"]
```

### 2. editors/ - Registry Removal (~200 lines saved)

**Before:**
- EditorRegistry class (174 lines) - overengineered for 3 editors
- Each editor had `EditorRegistry.register(...)` calls
- EditorContainer queried registry

**After:**
- EditorType enum in `__init__.py`
- Direct imports: `from ... import ImageViewer, TextViewer, TableViewer`
- EditorContainer uses simple if/elif dispatch
- User requested: "we can hard code them for clarity"

### 3. ImageViewer - Rewritten with WKWebView

**Before:** NSImageView in NSScrollView - basic zoom/pan

**After:** WKWebView rendering interactive HTML template with:
- Smooth zoom (scroll wheel + Cmd, double-click)
- Pan/drag navigation
- Rotation (90-degree increments)
- Minimap overlay with draggable viewport
- Selection box (Shift+drag) with zoom-to-selection
- Magnifier panel (0.5x-20x zoom, resizable)
- User requested: "keep the magnifier and menu commands"

Uses `get_interactive_image_viewer()` from `fichero.library.renderers.html_templates`

### 4. tabs.py - Minor Fix

Used `dataclasses.replace()` for immutable updates:
```python
# Before (duplicated all fields):
def with_modified(self, modified: bool) -> Tab:
    return Tab(
        id=self.id,
        title=self.title,
        tab_type=self.tab_type,
        ...  # 7 fields
    )

# After (Pythonic):
def with_modified(self, modified: bool) -> Tab:
    from dataclasses import replace
    return replace(self, is_modified=modified)
```

### 5. inspector.py - Type Detection Fix

Changed string-based type checking to `isinstance()`:
```python
# Before:
type_name = type(item).__name__
if type_name == "Document":
    return DOCUMENT_SECTIONS

# After (Pythonic):
from fichero.models import Document, Workflow
if isinstance(item, Document):
    return DOCUMENT_SECTIONS
```

## Architectural Patterns

### Good Patterns Found

1. **Frozen dataclasses** - menu.py, toolbar.py, tabs.py use `@dataclass(frozen=True)`
2. **objc_property** - toolbar.py correctly uses instance properties, not class variables
3. **isinstance()** - tab_controller.py already uses proper type checking
4. **SessionState persistence** - tab_controller.py has `to_dict()`/`from_dict()`
5. **Pattern matching** - toolbar.py uses Python 3.10+ `match/case`

### Data Flow (sidebar → browser → editor → inspector)

```
sidebar.on_select(item)
    ↓
window._on_sidebar_select(item)
    ↓
db.query(Document, parent_id=item.id)  # Get children
    ↓
browser.items = children
browser.on_select(docs)
    ↓
editor.load(docs[0])
inspector.load(docs[0])
```

## Completed: Mail-Style NSSplitViewController Layout

Implemented Mail/Finder-style layout using `NSSplitViewController`:

### Changes Made

1. **Window style**: Added `WINDOW_STYLE_FULL_SIZE_CONTENT` (1 << 15)
   - Content extends into title bar
   - `titlebarAppearsTransparent = True`
   - `titleVisibility = NSWindowTitleHidden`

2. **Split view controller**: Replaced manual `NSSplitView` with `NSSplitViewController`
   - Each pane wrapped in `NSViewController`
   - Controller set as `window.contentViewController`

3. **NSSplitViewItem behaviors**:
   - **Sidebar**: `NSSplitViewItem.sidebarWithViewController_()` - extends to title bar
   - **Browser**: `NSSplitViewItem.contentListWithViewController_()` - Mail-style content list
   - **Editor**: `NSSplitViewItem.alloc().initWithViewController_()` - main flexible area
   - **Inspector**: `NSSplitViewItem.inspectorWithViewController_()` - right sidebar

4. **Pane toggling**: Uses `item.animator().collapsed` for smooth animation

### Result

```
┌─ NSWindow with fullSizeContentView ────────────────────────────────────┐
│ [●●●] ╔═══SIDEBAR════╗ NSToolbar (search, actions)                     │
│       ║  Library     ║ ┌─────────────────────────────────────────────┐ │
│       ║  Searches    ║ │   BROWSER    │   EDITOR     │  INSPECTOR   │ │
│       ║  Workflows   ║ │ NSCollection │ ImageViewer  │ Context-     │ │
│       ║  Tools       ║ │              │ TextViewer   │ aware        │ │
│       ║              ║ │              │ TableViewer  │ sections     │ │
│       ╚══════════════╝ └─────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

## Remaining Work

### 2. Hook Up Sidebar to Full Data Model

Current sidebar sections:
- Collections (from `documents_to_sidebar_items()`)

Additional sections needed:
- Workflows
- Tools/Providers
- Smart Collections (saved searches)

### 3. Window State Persistence

macOS handles some via:
- `window.restorable = True`
- `window.setFrameAutosaveName_("FicheroMainWindow")`
- `split.autosaveName = "FicheroMainSplitView"`

But need to save/restore:
- Selected sidebar item
- Tab session state
- Inspector visibility

## File Structure

```
src/fichero/app/main_window/
├── __init__.py          # Package, exports MainWindowController
├── window.py            # MainWindowController - coordinates all
├── sidebar.py           # SourceList (NSOutlineView)
├── browser.py           # Browser (NSCollectionView grid)
├── editor.py            # EditorContainer (swaps viewers)
├── inspector.py         # Inspector (metadata pane)
├── tabs.py              # TabBar + Tab dataclass
├── tab_controller.py    # TabController + SessionState
├── menu.py              # AppMenu (NSMenu)
├── toolbar.py           # AppToolbar (NSToolbar)
└── editors/
    ├── __init__.py      # EditorType enum, exports
    ├── base.py          # EditorProtocol
    ├── image_viewer.py  # WKWebView + HTML
    ├── text_viewer.py   # NSTextView
    └── table_viewer.py  # NSTableView
```

## Recommendations

1. **Keep current patterns** - dataclasses, frozen immutables, isinstance()
2. **Continue using db helpers** - sidebar has `documents_to_sidebar_items()`
3. **Next priority** - Mail-style layout with NSSplitViewController
4. **Consider** - Moving menu handlers to separate file if window.py grows
