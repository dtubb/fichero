# Multi-Pane Editor System - Implementation Plan

**Date:** 2025-11-08
**Status:** Planning Phase
**Goal:** Implement VSCode-like multi-pane preview system with up to 4 split views, multi-window support, and workspace persistence

---

## Executive Summary

This plan outlines the implementation of a comprehensive multi-pane editor system for Fichero, inspired by VSCode's editor layout capabilities. The system will support:

1. **Split Pane Views** - Up to 4 preview panes (horizontal or vertical splits)
2. **Multi-Window Support** - Open OutputView in separate windows
3. **Workspace Persistence** - Save/restore window positions, pane states, and layouts
4. **Platform-Specific List Views** - Tree/Table/DetailedList abstraction layer
5. **Adjustable Pane Widths** - Settings for all pane widths (desktop only)
6. **Focus Management** - Track which pane has focus for navigation
7. **Inspector Following** - Inspector follows the focused window/pane

---

## Architecture Analysis

### Existing Systems (Strengths to Build Upon)

#### 1. **NavigationController Pattern** (`src/fichero/shared/navigation/navigation_controller.py`)
- **Event-based architecture** using `navigation_event_bus.py`
- **Modal management** for both desktop and mobile
- **State preservation** including edit mode state
- **View factory methods** for creating modal views
- **✅ REUSE:** This pattern is perfect for multi-window management

**Key Insight:** The NavigationController already creates views dynamically via factory methods (lines 782-965). We can extend this pattern to create multiple OutputView instances.

#### 2. **LayoutManager System** (`src/fichero/windows/main/views/output/layout_manager.py`)
- **Existing layout types:** SINGLE, DUAL, DUAL_COMPARE, TRIPLE, QUAD (lines 20-27)
- **OutputPane management** with creation, switching, and state sync
- **✅ LIMITATION:** Currently supports max 2 output panes (DUAL_COMPARE), needs extension to 4

**Key Insight:** The infrastructure for multiple panes already exists, just needs to be extended from 2 to 4 panes.

#### 3. **Box-Based Dynamic Layout** (`src/fichero/windows/main/main_window.py`)
- **Working pattern:** Library/Collection/Step pane show/hide using `Box.add()` and `Box.remove()` (lines 1150-1192)
- **✅ PROVEN:** This pattern works reliably for dynamic pane management

**Key Insight:** We successfully moved from SplitContainer to Box-based layout. This same pattern should be used for split panes.

#### 4. **Settings System** (`src/fichero/config/core/settings_manager.py`)
- **YAML-based** persistent settings
- **Encryption** for sensitive data (API keys)
- **User/default file fallback** pattern
- **✅ READY:** Can easily add pane width and workspace settings

**Key Insight:** Settings system is mature and ready to handle workspace persistence.

#### 5. **i18n System** (`src/fichero/ui/i18n.py`)
- **Gettext-based** translations
- **Runtime translation** via `_()` function
- **✅ READY:** Can easily add new menu labels for split operations

**Key Insight:** All new UI strings should use the existing `_()` function for translation.

### Current Layout Structure

```
MainWindow (Desktop)
├── main_horizontal_box (Box direction=ROW)
│   ├── left_pane (Library - 150px width, show/hide via add/remove)
│   └── content_area (Box direction=COLUMN, flex=1)
│       ├── center_right_box (Box direction=ROW)
│       │   ├── center_pane (Collection - 150px width, show/hide via add/remove)
│       │   └── right_pane (OutputView - flex=1)
│       │       ├── step_browser_container (150px width, show/hide via add/remove)
│       │       ├── content_area (Box direction=ROW, flex=1)
│       │       │   ├── layout_manager.container (Box direction=ROW)
│       │       │   │   └── [OutputPane(s) from LayoutManager]
│       │       │   └── inspector_panel (when visible)
│       │       └── toolbar
│       └── status_bar
```

---

## Implementation Plan

### Phase 1: Extend LayoutManager to Support 4 Panes

**Goal:** Extend existing LayoutManager to support up to 4 preview panes with horizontal/vertical splits

**Files to Modify:**
- `src/fichero/windows/main/views/output/layout_manager.py`

**Changes:**

1. **Add new layout types** (extend existing LayoutType enum at lines 20-27):
```python
class LayoutType(Enum):
    # Existing
    SINGLE = "single"                    # [Output]
    DUAL = "dual"                        # [Output | Inspector]
    DUAL_COMPARE = "dual_compare"        # [Output | Output]
    TRIPLE = "triple"                    # [Output | Inspector | Output]
    QUAD = "quad"                        # [Output | Inspector | Output | Inspector]

    # NEW: 4-pane layouts
    QUAD_SPLIT_H = "quad_split_h"        # [Output | Output]
                                          # [Output | Output]
    QUAD_SPLIT_V = "quad_split_v"        # [Output | Output | Output | Output]
    TRIPLE_SPLIT_H = "triple_split_h"    # [Output | Output]
                                          # [Output]
    TRIPLE_SPLIT_V = "triple_split_v"    # [Output | Output | Output]
```

2. **Add layout creation methods** (follow pattern at lines 119-180):
```python
def _create_quad_split_h_layout(self):
    """Create quad horizontal split: 2x2 grid"""
    # Top row
    top_row = toga.Box(style=Pack(direction=ROW, flex=1))
    top_left = self._create_pane()
    top_right = self._create_pane()
    self.panes.extend([top_left, top_right])
    top_row.add(top_left.as_box())
    top_row.add(top_right.as_box())

    # Bottom row
    bottom_row = toga.Box(style=Pack(direction=ROW, flex=1))
    bottom_left = self._create_pane()
    bottom_right = self._create_pane()
    self.panes.extend([bottom_left, bottom_right])
    bottom_row.add(bottom_left.as_box())
    bottom_row.add(bottom_right.as_box())

    # Add to container
    self._container.style.direction = COLUMN
    self._container.add(top_row)
    self._container.add(bottom_row)
```

3. **Add split pane controls**:
   - Method: `split_pane_horizontal(pane_index: int)` - split a pane horizontally
   - Method: `split_pane_vertical(pane_index: int)` - split a pane vertically
   - Method: `close_pane(pane_index: int)` - close a specific pane

4. **Add focus tracking**:
```python
class LayoutManager:
    def __init__(self, ...):
        # ...existing code...
        self.focused_pane_index: int = 0  # Track which pane has focus

    def set_focused_pane(self, pane_index: int):
        """Set which pane has focus"""
        if 0 <= pane_index < len(self.panes):
            self.focused_pane_index = pane_index
            # Emit event for inspector to follow
            from fichero.shared.navigation.navigation_event_bus import emit_navigation_event
            emit_navigation_event("PANE_FOCUS_CHANGED", {
                'pane_index': pane_index,
                'pane': self.panes[pane_index]
            })

    def get_focused_pane(self) -> Optional[OutputPane]:
        """Get currently focused pane"""
        return self.panes[self.focused_pane_index] if 0 <= self.focused_pane_index < len(self.panes) else None
```

**DRY Principle:** Reuse existing `_create_pane()` method (line 181) and `OutputPane` class.

---

### Phase 2: Add Split Controls to Toolbar

**Goal:** Add VSCode-like split buttons to toolbar

**Files to Modify:**
- `src/fichero/shared/toolbars/desktop_toolbar.py` (or wherever preview toolbar is defined)

**Changes:**

1. **Add toolbar buttons**:
```python
# Split horizontal button
split_h_btn = toga.Button(
    text="⬌",  # Unicode horizontal split icon
    tooltip=_("Split Pane Horizontal"),
    on_press=self._on_split_horizontal
)

# Split vertical button
split_v_btn = toga.Button(
    text="⬍",  # Unicode vertical split icon
    tooltip=_("Split Pane Vertical"),
    on_press=self._on_split_vertical
)
```

2. **Add menu items** (in main_window.py menu setup):
```python
view_menu.add_item(
    toga.Command(
        lambda w: self._split_pane_horizontal(),
        text=_("Split Pane Horizontal"),
        shortcut=toga.Key.MOD_1 + toga.Key.BACKSLASH  # Cmd+\ like VSCode
    )
)
view_menu.add_item(
    toga.Command(
        lambda w: self._split_pane_vertical(),
        text=_("Split Pane Vertical"),
        shortcut=toga.Key.MOD_1 + toga.Key.MOD_2 + toga.Key.BACKSLASH
    )
)
```

3. **Wire to LayoutManager**:
```python
def _split_pane_horizontal(self):
    """Split currently focused pane horizontally"""
    if self.cached_output_view:
        layout_manager = self.cached_output_view.layout_manager
        focused_pane_index = layout_manager.focused_pane_index
        layout_manager.split_pane_horizontal(focused_pane_index)

def _split_pane_vertical(self):
    """Split currently focused pane vertically"""
    if self.cached_output_view:
        layout_manager = self.cached_output_view.layout_manager
        focused_pane_index = layout_manager.focused_pane_index
        layout_manager.split_pane_vertical(focused_pane_index)
```

**i18n:** Use existing `_()` function for all new strings.

---

### Phase 3: Multi-Window Support

**Goal:** Allow opening OutputView in new windows

**Files to Modify:**
- `src/fichero/windows/main/main_window.py`
- Create: `src/fichero/windows/output/output_window.py` (new file)

**New File:** `output_window.py`
```python
"""
OutputWindow - Standalone window for OutputView

Similar to InspectorWindow pattern, but for output views.
"""

import toga
from toga.style import Pack
from fichero.windows.main.views.output.output_view import OutputView

class OutputWindow:
    def __init__(self, app, library_manager, renderer_registry):
        self.app = app
        self.library_manager = library_manager
        self.renderer_registry = renderer_registry

        # Create window
        self.window = toga.Window(
            title=_("Preview"),
            size=(800, 600)
        )

        # Create OutputView
        self.output_view = OutputView(
            app=app,
            is_mobile=False,
            library_manager=library_manager
        )

        # Set window content
        self.window.content = self.output_view.get_container()

        # Register window with app
        self.app.windows.add(self.window)

    def show(self):
        """Show the window"""
        self.window.show()

    def close(self):
        """Close the window"""
        self.window.close()

    async def set_step(self, item_id: str, step_index: int):
        """Display a specific step"""
        primary_pane = self.output_view.layout_manager.get_primary_pane()
        if primary_pane:
            await primary_pane.set_step(item_id, step_index)
```

**Menu Integration:**
```python
# In main_window.py menu setup
view_menu.add_item(
    toga.Command(
        lambda w: self._open_output_in_new_window(),
        text=_("Open Preview in New Window"),
        shortcut=toga.Key.MOD_1 + toga.Key.N
    )
)

def _open_output_in_new_window(self):
    """Open a new output window"""
    from fichero.windows.output.output_window import OutputWindow

    output_window = OutputWindow(
        app=self.app,
        library_manager=self.library_manager,
        renderer_registry=self.renderer_registry
    )
    output_window.show()

    # Track windows for cleanup
    if not hasattr(self, '_output_windows'):
        self._output_windows = []
    self._output_windows.append(output_window)
```

**Window Management:** Store list of OutputWindow instances in main_window for:
- Focus tracking
- Cleanup on app exit
- Workspace persistence

**DRY Principle:** Reuse existing OutputView class, just wrap it in a new window.

---

### Phase 4: Workspace Persistence

**Goal:** Save and restore window positions, pane states, and split configurations

**Files to Modify:**
- `src/fichero/config/core/settings_manager.py` (extend existing settings)
- `src/fichero/windows/main/main_window.py` (save/restore on show/hide)

**Settings Schema Extension:**
```yaml
# In settings.yml
workspaces:
  last_session:
    main_window:
      position: [100, 100]
      size: [1200, 800]
      panes:
        library: visible: true, width: 150
        collection: visible: true, width: 150
        step: visible: true, width: 150
        adjust: visible: false, width: 200
    output_windows:
      - id: "output_1"
        position: [1400, 100]
        size: [800, 600]
        layout_type: "dual_compare"
        panes:
          - item_id: "doc_123", step_index: 0
          - item_id: "doc_123", step_index: 1
```

**Implementation:**

1. **Save workspace on window close/hide**:
```python
# In main_window.py
def _on_close(self):
    """Save workspace before closing"""
    self._save_workspace()
    # ...existing close logic...

def _save_workspace(self):
    """Save current workspace state to settings"""
    workspace = {
        'main_window': {
            'position': list(self.window.position) if hasattr(self.window, 'position') else [0, 0],
            'size': list(self.window.size),
            'panes': {
                'library': {
                    'visible': self.pane_visibility['library'],
                    'width': self.pane_widths['library']
                },
                'collection': {
                    'visible': self.pane_visibility['collection'],
                    'width': self.pane_widths['collection']
                },
                'step': {
                    'visible': self.step_browser_visible,
                    'width': self.pane_widths.get('step', 150)
                },
                'adjust': {
                    'visible': self.cached_output_view.inspector_visible if self.cached_output_view else False,
                    'width': self.pane_widths.get('adjust', 200)
                }
            }
        },
        'output_windows': []
    }

    # Save output windows
    if hasattr(self, '_output_windows'):
        for i, win in enumerate(self._output_windows):
            workspace['output_windows'].append({
                'id': f"output_{i}",
                'position': list(win.window.position) if hasattr(win.window, 'position') else [0, 0],
                'size': list(win.window.size),
                'layout_type': win.output_view.layout_manager.get_layout_type().value,
                # Could also save pane states here if needed
            })

    # Save to settings
    settings = self.app.settings_manager.load_settings()
    if 'workspaces' not in settings:
        settings['workspaces'] = {}
    settings['workspaces']['last_session'] = workspace
    self.app.settings_manager.save_settings(settings)
```

2. **Restore workspace on app startup**:
```python
# In main_window.py startup()
def startup(self):
    # ...existing startup code...

    # Restore workspace at the end
    self._restore_workspace()

def _restore_workspace(self):
    """Restore workspace from settings"""
    settings = self.app.settings_manager.load_settings()
    workspace = settings.get('workspaces', {}).get('last_session', {})

    # Restore main window
    main_win = workspace.get('main_window', {})
    if main_win:
        # Restore position and size
        pos = main_win.get('position', [100, 100])
        size = main_win.get('size', [1200, 800])
        self.window.position = tuple(pos)
        self.window.size = tuple(size)

        # Restore pane visibility
        panes = main_win.get('panes', {})
        self.pane_visibility['library'] = panes.get('library', {}).get('visible', True)
        self.pane_visibility['collection'] = panes.get('collection', {}).get('visible', True)
        # ...etc...

        self._update_pane_layout()

    # Restore output windows
    output_wins = workspace.get('output_windows', [])
    for win_data in output_wins:
        self._restore_output_window(win_data)

def _restore_output_window(self, win_data):
    """Restore a single output window"""
    # Create window
    output_window = OutputWindow(...)

    # Restore position and size
    output_window.window.position = tuple(win_data.get('position', [0, 0]))
    output_window.window.size = tuple(win_data.get('size', [800, 600]))

    # Restore layout type
    layout_type = LayoutType[win_data.get('layout_type', 'SINGLE')]
    output_window.output_view.layout_manager.set_layout(layout_type)

    output_window.show()
```

**Storage Location:** Use `app.paths.data` (Toga's data directory) as identified in settings_manager.py lines 219-226.

**DRY Principle:** Reuse existing settings save/load infrastructure.

---

### Phase 5: Adjustable Pane Widths in Settings

**Goal:** Add settings UI for adjusting pane widths (desktop only)

**Files to Modify:**
- `src/fichero/windows/settings/settings_window.py` (or desktop settings view)

**Settings Schema:**
```yaml
# In settings.yml
preferences:
  pane_widths:  # Desktop only
    library: 150
    collection: 150
    step: 150
    adjust: 200
```

**UI Implementation:**
```python
# In SettingsWindow
def _build_pane_width_section(self):
    """Build pane width settings (desktop only)"""
    if self.is_mobile:
        return None

    section = toga.Box(style=Pack(direction=COLUMN, margin=10))

    # Header
    header = toga.Label(
        text=_("Pane Widths (pixels)"),
        style=Pack(font_weight='bold', margin_bottom=10)
    )
    section.add(header)

    # Library width
    lib_row = self._create_number_input_row(
        label=_("Library Width:"),
        value=self.settings.get('preferences', {}).get('pane_widths', {}).get('library', 150),
        min_value=100,
        max_value=400,
        on_change=lambda widget: self._on_pane_width_changed('library', widget.value)
    )
    section.add(lib_row)

    # Collection width
    coll_row = self._create_number_input_row(
        label=_("Collection Width:"),
        value=self.settings.get('preferences', {}).get('pane_widths', {}).get('collection', 150),
        min_value=100,
        max_value=400,
        on_change=lambda widget: self._on_pane_width_changed('collection', widget.value)
    )
    section.add(coll_row)

    # Step width
    step_row = self._create_number_input_row(
        label=_("Step Width:"),
        value=self.settings.get('preferences', {}).get('pane_widths', {}).get('step', 150),
        min_value=100,
        max_value=400,
        on_change=lambda widget: self._on_pane_width_changed('step', widget.value)
    )
    section.add(step_row)

    # Inspector width
    insp_row = self._create_number_input_row(
        label=_("Inspector Width:"),
        value=self.settings.get('preferences', {}).get('pane_widths', {}).get('adjust', 200),
        min_value=150,
        max_value=500,
        on_change=lambda widget: self._on_pane_width_changed('adjust', widget.value)
    )
    section.add(insp_row)

    return section
```

**Apply on Save:**
```python
def _on_pane_width_changed(self, pane_name: str, new_width: int):
    """Update pane width setting"""
    if 'preferences' not in self.settings:
        self.settings['preferences'] = {}
    if 'pane_widths' not in self.settings['preferences']:
        self.settings['preferences']['pane_widths'] = {}

    self.settings['preferences']['pane_widths'][pane_name] = new_width

    # Apply immediately to main window if it exists
    if hasattr(self.app, 'main_window') and self.app.main_window:
        self.app.main_window.set_pane_width(pane_name, new_width)
```

**Main Window Integration:**
```python
# In main_window.py
def set_pane_width(self, pane_name: str, width: int):
    """Dynamically update pane width"""
    self.pane_widths[pane_name] = width

    if pane_name == 'library' and self.left_pane:
        self.left_pane.style.width = width
    elif pane_name == 'collection' and self.center_pane:
        self.center_pane.style.width = width
    elif pane_name == 'step' and hasattr(self, 'step_browser_container'):
        self.step_browser_container.style.width = width
    elif pane_name == 'adjust' and self.cached_output_view:
        if hasattr(self.cached_output_view, 'inspector_panel'):
            self.cached_output_view.inspector_panel.style.width = width
```

---

### Phase 6: Platform-Specific List Abstraction

**Goal:** Create abstraction layer for Tree/Table/DetailedList across platforms

**Files to Create:**
- `src/fichero/ui/widgets/platform_list.py` (new file)

**Implementation:**

```python
"""
PlatformList - Cross-platform list/tree/table abstraction

Automatically selects the appropriate widget based on platform:
- Tree widget on Mac/Linux
- Table widget on Windows
- DetailedList on Android/iOS
"""

import toga
from toga.style import Pack
import platform
import logging

logger = logging.getLogger(__name__)


class PlatformList:
    """
    Platform-aware list widget that adapts to the best UI pattern for each platform.

    Usage:
        list_widget = PlatformList(
            headings=['Name', 'Modified', 'Size'],
            data=[
                ('doc1.pdf', '2025-11-08', '1.2 MB'),
                ('doc2.pdf', '2025-11-07', '800 KB'),
            ],
            on_select=self._on_item_selected
        )
        container.add(list_widget.widget)
    """

    def __init__(self, headings: list, data: list = None, on_select=None, is_mobile: bool = False):
        self.headings = headings
        self.data = data or []
        self.on_select = on_select
        self.is_mobile = is_mobile

        # Detect platform and create appropriate widget
        self.platform_type = self._detect_platform()
        self.widget = self._create_widget()

        # Populate data
        if self.data:
            self.set_data(self.data)

    def _detect_platform(self) -> str:
        """Detect which platform we're on"""
        if self.is_mobile:
            return 'mobile'

        system = platform.system()
        if system == 'Darwin':
            return 'macos'
        elif system == 'Windows':
            return 'windows'
        elif system == 'Linux':
            return 'linux'
        else:
            return 'other'

    def _create_widget(self):
        """Create platform-appropriate widget"""
        if self.platform_type in ['macos', 'linux']:
            # Use Tree widget
            logger.debug(f"Creating Tree widget for {self.platform_type}")
            return self._create_tree_widget()
        elif self.platform_type == 'windows':
            # Use Table widget
            logger.debug("Creating Table widget for Windows")
            return self._create_table_widget()
        elif self.platform_type == 'mobile':
            # Use DetailedList widget
            logger.debug("Creating DetailedList widget for mobile")
            return self._create_detailed_list_widget()
        else:
            # Fallback to Table
            logger.debug(f"Creating Table widget (fallback for {self.platform_type})")
            return self._create_table_widget()

    def _create_tree_widget(self):
        """Create Tree widget (Mac/Linux)"""
        tree = toga.Tree(
            headings=self.headings,
            on_select=self._on_widget_select,
            style=Pack(flex=1)
        )
        return tree

    def _create_table_widget(self):
        """Create Table widget (Windows)"""
        table = toga.Table(
            headings=self.headings,
            on_select=self._on_widget_select,
            style=Pack(flex=1)
        )
        return table

    def _create_detailed_list_widget(self):
        """Create DetailedList widget (Mobile)"""
        detailed_list = toga.DetailedList(
            on_select=self._on_widget_select,
            style=Pack(flex=1)
        )
        return detailed_list

    def _on_widget_select(self, widget, row=None, **kwargs):
        """Internal select handler that normalizes across platforms"""
        if self.on_select:
            # Normalize row data across platforms
            if self.platform_type == 'mobile':
                # DetailedList passes the row object
                selected_data = row
            else:
                # Tree/Table pass row object
                selected_data = row

            self.on_select(selected_data)

    def set_data(self, data: list):
        """Set widget data (abstracts across platforms)"""
        self.data = data

        if self.platform_type in ['macos', 'linux']:
            # Tree widget
            self.widget.data.clear()
            for row in data:
                self.widget.data.append(*row)  # Unpack row tuple
        elif self.platform_type == 'windows':
            # Table widget
            self.widget.data.clear()
            for row in data:
                self.widget.data.append(*row)
        elif self.platform_type == 'mobile':
            # DetailedList widget
            self.widget.data.clear()
            for row in data:
                # Convert row tuple to DetailedList format
                # (title, subtitle, icon)
                if len(row) >= 2:
                    self.widget.data.append(
                        title=str(row[0]),
                        subtitle=str(row[1]) if len(row) > 1 else ''
                    )
                else:
                    self.widget.data.append(title=str(row[0]))

    def clear(self):
        """Clear all data"""
        self.data = []
        self.widget.data.clear()

    def get_selected(self):
        """Get selected row (normalized across platforms)"""
        if hasattr(self.widget, 'selection'):
            return self.widget.selection
        return None
```

**Usage Example:**
```python
# In LibraryView or CollectionView
from fichero.ui.widgets.platform_list import PlatformList

class LibraryView:
    def _build_ui(self):
        # Use PlatformList instead of hardcoded Tree/Table
        self.collection_list = PlatformList(
            headings=['Name', 'Items', 'Modified'],
            on_select=self._on_collection_selected,
            is_mobile=self.is_mobile
        )

        self.container.add(self.collection_list.widget)

    def refresh_collections(self):
        # Set data - platform abstraction handles the rest
        collections_data = [
            (coll.name, coll.item_count, coll.modified_date)
            for coll in self.collections
        ]
        self.collection_list.set_data(collections_data)
```

**DRY Principle:** Single implementation that adapts to all platforms.

---

### Phase 7: Navigation Integration

**Goal:** Wire next/previous buttons to focused pane

**Files to Modify:**
- `src/fichero/windows/main/main_window.py` (toolbar handlers)
- `src/fichero/windows/main/views/output/output_view.py` (navigation methods)

**Implementation:**

```python
# In main_window.py toolbar handlers
def _on_next_file(self, widget):
    """Navigate to next file in currently focused pane"""
    focused_pane = self._get_focused_output_pane()
    if focused_pane:
        focused_pane.navigate_next_file()

def _on_previous_file(self, widget):
    """Navigate to previous file in currently focused pane"""
    focused_pane = self._get_focused_output_pane()
    if focused_pane:
        focused_pane.navigate_previous_file()

def _on_next_step(self, widget):
    """Navigate to next step in currently focused pane"""
    focused_pane = self._get_focused_output_pane()
    if focused_pane:
        focused_pane.navigate_next_step()

def _on_previous_step(self, widget):
    """Navigate to previous step in currently focused pane"""
    focused_pane = self._get_focused_output_pane()
    if focused_pane:
        focused_pane.navigate_previous_step()

def _get_focused_output_pane(self):
    """Get the currently focused output pane (from main window or focused output window)"""
    # Check if an output window has focus
    if hasattr(self, '_output_windows'):
        for win in self._output_windows:
            if win.window.focused:
                return win.output_view.layout_manager.get_focused_pane()

    # Otherwise use main window's output view
    if self.cached_output_view:
        return self.cached_output_view.layout_manager.get_focused_pane()

    return None
```

**OutputPane Navigation Methods:**
```python
# In output_pane.py
class OutputPane:
    def navigate_next_file(self):
        """Navigate to next file in collection"""
        # Get current file from collection
        # Load next file
        # Update display
        pass

    def navigate_previous_file(self):
        """Navigate to previous file in collection"""
        pass

    def navigate_next_step(self):
        """Navigate to next step in current file"""
        # Increment step_index
        # Update display
        pass

    def navigate_previous_step(self):
        """Navigate to previous step in current file"""
        # Decrement step_index
        # Update display
        pass
```

---

### Phase 8: Inspector Following Focused Window

**Goal:** Inspector follows the focused window/pane

**Files to Modify:**
- `src/fichero/windows/main/views/output/output_view.py` (inspector update logic)

**Implementation:**

```python
# Subscribe to pane focus change events
from fichero.shared.navigation.navigation_event_bus import subscribe_to_navigation

class OutputView:
    def __init__(self, ...):
        # ...existing code...

        # Subscribe to pane focus events
        subscribe_to_navigation("PANE_FOCUS_CHANGED", self._on_pane_focus_changed)

    def _on_pane_focus_changed(self, event):
        """Update inspector when pane focus changes"""
        pane_index = event.get('pane_index')
        pane = event.get('pane')

        if pane:
            # Get current item/step from focused pane
            item_id = pane.current_item_id
            step_index = pane.current_step_index

            # Update inspector with focused pane's content
            if self.inspector_panel:
                self.inspector_panel.update_for_item(item_id, step_index)
```

**DRY Principle:** Reuse existing event bus infrastructure from NavigationController.

---

## Implementation Order

### Week 1: Core Split Pane System
1. ✅ Day 1-2: Extend LayoutManager with 4-pane layouts (Phase 1)
2. ✅ Day 3-4: Add split controls to toolbar (Phase 2)
3. ✅ Day 5: Testing and bug fixes

### Week 2: Multi-Window Support
4. ✅ Day 1-2: Create OutputWindow class (Phase 3)
5. ✅ Day 3-4: Add menu integration and window tracking
6. ✅ Day 5: Testing and bug fixes

### Week 3: Persistence and Settings
7. ✅ Day 1-2: Implement workspace persistence (Phase 4)
8. ✅ Day 3-4: Add pane width settings UI (Phase 5)
9. ✅ Day 5: Testing and bug fixes

### Week 4: Platform Abstraction and Polish
10. ✅ Day 1-2: Create PlatformList abstraction (Phase 6)
11. ✅ Day 3: Integrate navigation with focus (Phase 7)
12. ✅ Day 4: Inspector following (Phase 8)
13. ✅ Day 5: Final testing and documentation

---

## Risk Mitigation

### Risk 1: Toga Window Position API Not Available
**Likelihood:** Medium
**Impact:** High (affects workspace persistence)
**Mitigation:**
- Test `window.position` and `window.size` properties early
- If not available, save only size and use OS default positioning
- Document limitation for future Toga versions

### Risk 2: Mobile UI Breaks
**Likelihood:** Low
**Impact:** High
**Mitigation:**
- All new features gated by `if not is_mobile:` checks
- PlatformList handles mobile separately with DetailedList
- No changes to mobile navigation or layout
- Test on iOS simulator regularly

### Risk 3: Performance with 4 Panes
**Likelihood:** Medium
**Impact:** Medium
**Mitigation:**
- Lazy loading of pane content (only load visible content)
- Reuse existing OutputPane rendering infrastructure
- Profile with large documents before release

### Risk 4: Window Management Complexity
**Likelihood:** Medium
**Impact:** Medium
**Mitigation:**
- Keep window list simple (just array of OutputWindow instances)
- Use Toga's built-in window management where possible
- Clear API for cleanup on app exit

---

## Testing Strategy

### Unit Tests
- `test_layout_manager_extended.py` - Test 4-pane layouts
- `test_platform_list.py` - Test platform detection and widget creation
- `test_workspace_persistence.py` - Test save/restore logic

### Integration Tests
- Test split operations with real OutputPane instances
- Test multi-window creation and cleanup
- Test workspace persistence across app restarts

### Manual Testing Checklist
- [ ] Split pane horizontal works
- [ ] Split pane vertical works
- [ ] Close pane works
- [ ] Open preview in new window works
- [ ] Window positions persist across restart
- [ ] Pane widths persist across restart
- [ ] Navigation buttons work with focused pane
- [ ] Inspector follows focused window
- [ ] Mobile UI still works (no regressions)
- [ ] Platform list shows correct widget on each platform

---

## Success Criteria

1. ✅ Can split preview pane up to 4 times (horizontal or vertical)
2. ✅ Can open preview in new window via menu or shortcut
3. ✅ Window positions and pane states persist across app restarts
4. ✅ Pane widths are configurable in settings (desktop only)
5. ✅ Navigation buttons work with focused pane
6. ✅ Inspector follows focused window
7. ✅ Mobile UI still works (no regressions)
8. ✅ Platform list works on Mac, Windows, Linux, iOS, Android

---

## Future Enhancements (Post-MVP)

1. **Drag-and-drop pane reordering** - Allow dragging panes to rearrange
2. **Named workspaces** - Save/load multiple workspace configurations
3. **Pane synchronization** - Sync zoom/rotation across panes
4. **Keyboard shortcuts for pane switching** - Cmd+1, Cmd+2, etc.
5. **Pane restore on collection change** - Remember which panes were open for each collection

---

## Notes

- This plan follows the DRY principle by reusing existing patterns (NavigationController, LayoutManager, Box-based layout)
- All new features are desktop-only unless explicitly mobile-compatible
- Existing i18n and settings systems are leveraged throughout
- Event bus architecture from NavigationController is extended for pane focus tracking
- Box-based layout pattern (proven working for Library/Collection/Step panes) is applied consistently

---

## Next Steps

1. Review this plan with user
2. Get approval on approach
3. Commit this plan to GitHub
4. Begin implementation starting with Phase 1 (LayoutManager extension)
