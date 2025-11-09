# Phase 6: Architecture Refactor - Universal Navigation & Window System

## Overview

This refactor transforms Fichero from a specialized multi-pane output system to a universal, DRY-compliant navigation and window management architecture.

**Current State:**
- Navigation controller handles mobile layout only
- Output view has custom split pane logic (Phase 5)
- Each view is tightly coupled to main window
- Platform-specific widgets hardcoded (DetailedList, etc.)
- Focus management is output-pane specific
- Inspector JSON rendering is one-off code

**Target State:**
- Navigation controller manages ALL layout/splitting (desktop + mobile)
- Every view can be standalone window OR pane in main window
- Platform-agnostic widget abstraction layer
- Universal focus tracking system
- Reusable JSON-to-UI rendering system
- Resizable panes with visual separators
- **Multiple main windows support** - Open preview/output views in separate main windows
- **Workspace management** - Save/load entire app state (windows, positions, context)
- **Sidebar concept** - Library view becomes sidebar with embedded activity view
- **Full state persistence** - Track and restore library/collection/item/step context

---

## Core Principles

1. **DRY (Don't Repeat Yourself)** - One navigation system for all platforms
2. **View Independence** - Every view works standalone or embedded
3. **Platform Abstraction** - Widgets adapt to macOS/Windows/Linux/mobile
4. **Universal Focus** - Single focus tracking system across all views
5. **Composability** - Views can be nested, split, or windowed freely

---

## Architecture Components

### 1. View System
- **Base View Interface** - All views implement common interface
- **View Types:**
  - **SidebarView** (renamed from LibraryView) - Can embed ActivityView at bottom
  - CollectionView (currently exists)
  - StepView (extracted from OutputView)
  - AdjustView (extracted from OutputView)
  - PreviewView (renamed from OutputView, plugin system only)
  - InspectorView (currently separate window)
  - ActivityView (currently separate window, embeddable in sidebar)
  - SettingsView (currently separate window)
  - PlansView (currently separate window)

### 2. Navigation Controller (Enhanced)
- **Universal Layout Manager** - Handles splits for ALL views
- **Window Manager** - Creates multiple main windows + utility windows
- **Focus Tracker** - Tracks focused view globally across all windows
- **State Manager** - Tracks library/collection/item/step context globally
- **Workspace Manager** - Save/load complete app state
- **Mobile/Desktop Modes** - Unified handling

### 3. Platform Widget Abstraction
- **AbstractTreeList** - Tree (mac/linux) → Table (windows) → DetailedList (mobile)
- **AbstractToolbar** - Size variants (full, compact, mini)
- **AbstractCanvas** - Resizable separators

### 4. Reusable UI Systems
- **JSON-to-UI Renderer** - Used by Inspector + Adjust views
- **Focus Border System** - Universal focus indicator
- **Resize Handles** - Canvas-based pane resizing

---

## Phase Breakdown

## PHASE 1: Foundation & Abstractions (Week 1)

### 1.1: Platform Widget Abstraction Layer
**Goal:** Create platform-agnostic widgets that adapt automatically

**Steps:**
1. Create `src/fichero/shared/widgets/abstract_tree_list.py`
   - Class: `AbstractTreeList(platform, data_source)`
   - Properties: `selected_item`, `selection_callback`, `data`
   - Methods: `refresh()`, `expand()`, `collapse()`, `select()`
   - Platform mapping:
     - macOS/Linux: `toga.Tree`
     - Windows: `toga.Table`
     - Mobile: `toga.DetailedList`

2. Create `src/fichero/shared/widgets/abstract_toolbar.py`
   - Class: `AbstractToolbar(size='full')`
   - Sizes: `full` (current), `compact` (reduced margins), `mini` (icon-only)
   - Auto-adjusts heights and spacing

3. Create `src/fichero/shared/widgets/resizable_canvas.py`
   - Class: `ResizableCanvas(orientation='vertical')`
   - Visual separator line (1px subtle gray)
   - Drag handlers for resize
   - Emits resize events

**Testing:**
- Unit test: Platform detection returns correct widget
- Visual test: Each widget type renders on each platform
- Integration test: Toolbar sizes adjust correctly

**Verification:**
```python
# Test platform widget selection
widget = AbstractTreeList(platform='macOS')
assert isinstance(widget._impl, toga.Tree)

widget = AbstractTreeList(platform='Windows')
assert isinstance(widget._impl, toga.Table)
```

---

### 1.2: Base View Interface
**Goal:** Standard interface all views must implement

**Steps:**
1. Create `src/fichero/shared/views/base_view_interface.py`
   ```python
   class BaseViewInterface:
       """Interface all views must implement"""

       # Properties
       @property
       def view_id(self) -> str:
           """Unique identifier for this view instance"""

       @property
       def view_type(self) -> ViewType:
           """Type of view (LIBRARY, COLLECTION, STEP, etc.)"""

       @property
       def container(self) -> toga.Box:
           """The root container widget"""

       @property
       def toolbar(self) -> Optional[AbstractToolbar]:
           """Toolbar for this view (if any)"""

       @property
       def is_focused(self) -> bool:
           """Whether this view currently has focus"""

       # Methods
       def set_focused(self, focused: bool):
           """Update focus state and visual indicator"""

       def get_state(self) -> Dict[str, Any]:
           """Return current state for persistence"""

       def restore_state(self, state: Dict[str, Any]):
           """Restore from saved state"""

       def can_close(self) -> bool:
           """Whether view can be closed (check for unsaved changes)"""

       def on_close(self):
           """Cleanup when view is closed"""
   ```

2. Create `src/fichero/shared/views/view_types.py`
   ```python
   from enum import Enum

   class ViewType(Enum):
       LIBRARY = "library"
       COLLECTION = "collection"
       STEP = "step"
       ADJUST = "adjust"
       PREVIEW = "preview"
       INSPECTOR = "inspector"
       ACTIVITY = "activity"
       SETTINGS = "settings"
       PLANS = "plans"
   ```

**Testing:**
- Unit test: Each view type enum is unique
- Integration test: Mock view implements all required methods

---

### 1.3: Focus Border System
**Goal:** Universal focus indicator for all views

**Steps:**
1. Create `src/fichero/shared/focus/focus_border.py`
   ```python
   class FocusBorder:
       """Manages focus border for any view"""

       def __init__(self, container: toga.Box):
           self.container = container
           self._focused = False

       def set_focused(self, focused: bool):
           """Show/hide focus border"""
           if focused:
               self.container.style.background_color = rgb(0, 122, 204)
               self.container.style.margin = 2
           else:
               if hasattr(self.container.style, 'background_color'):
                   del self.container.style.background_color
               self.container.style.margin = 0
   ```

2. Update `BaseViewInterface` to use `FocusBorder`

**Testing:**
- Visual test: Focus border appears/disappears correctly
- Unit test: Margin and background color set correctly

---

## PHASE 2: View Extraction & Refactor (Week 2)

### 2.1: Extract StepView from OutputView
**Goal:** Separate step browser into standalone view

**Current:** Step browser is embedded in OutputView
**Target:** Independent StepView that can be windowed or embedded

**Steps:**
1. Create `src/fichero/windows/main/views/step/step_view.py`
   - Move step browser logic from OutputView
   - Implements `BaseViewInterface`
   - Properties: `current_item_id`, `current_step_index`
   - Methods: `set_item()`, `next_step()`, `prev_step()`
   - Emits events: `step_changed`, `item_changed`

2. Create `src/fichero/windows/main/views/step/__init__.py`

3. Update OutputView to use StepView as component
   - Remove embedded step browser code
   - Listen to StepView events
   - Pass step changes to PreviewView

**Testing:**
- Unit test: StepView can navigate steps independently
- Integration test: StepView events trigger correctly
- Visual test: StepView works standalone and embedded

**Verification:**
```python
# StepView works independently
step_view = StepView(app, item_id="test_item")
step_view.set_item("test_item")
assert step_view.current_step_index == 0

step_view.next_step()
assert step_view.current_step_index == 1
```

---

### 2.2: Extract AdjustView from OutputView
**Goal:** Separate adjustment panel into standalone view

**Steps:**
1. Create `src/fichero/windows/main/views/adjust/adjust_view.py`
   - Move adjustment panel from OutputView
   - Implements `BaseViewInterface`
   - Uses JSON-to-UI renderer (created in Phase 3)
   - Properties: `current_settings`, `tool_name`
   - Methods: `load_tool_settings()`, `apply_changes()`

2. Update OutputView to use AdjustView

**Testing:**
- Unit test: AdjustView loads/saves settings correctly
- Integration test: Changes propagate to preview
- Visual test: Works standalone and embedded

---

### 2.3: Rename OutputView to PreviewView
**Goal:** Clarify that this view is just the preview pane

**Steps:**
1. Rename files:
   - `output_view.py` → `preview_view.py`
   - `output_pane.py` → `preview_pane.py`
   - Update all imports

2. Update directory structure:
   - `views/output/` → `views/preview/`

3. Update class names:
   - `OutputView` → `PreviewView`
   - `OutputPane` → `PreviewPane`

4. Update references throughout codebase

**Testing:**
- Regression test: All existing functionality still works
- Import test: All imports resolve correctly

---

## PHASE 3: Universal Navigation Controller (Week 3)

### 3.1: Enhanced Navigation Controller
**Goal:** Navigation controller manages ALL view layout/splitting

**Current State:**
- `NavigationController` only handles mobile view switching
- `LayoutManager` handles output pane splitting (Phase 5)
- Each is separate, duplicated logic

**Target State:**
- Single `NavigationController` handles:
  - Mobile view stack navigation
  - Desktop multi-pane layout
  - Window management
  - Focus tracking
  - State persistence

**Steps:**
1. Create `src/fichero/shared/navigation/layout_manager.py`
   ```python
   class UniversalLayoutManager:
       """Manages layout of any views in columns/rows"""

       def __init__(self, platform: str):
           self.platform = platform
           self.columns: List[ColumnContainer] = []
           self.focused_view: Optional[BaseViewInterface] = None

       def add_view(self, view: BaseViewInterface,
                    position: str = 'right') -> str:
           """Add view to layout. Returns view_id."""

       def remove_view(self, view_id: str):
           """Remove view from layout"""

       def split_horizontal(self, view_id: str) -> str:
           """Split horizontally from view. Returns new view_id."""

       def split_vertical(self, view_id: str) -> str:
           """Split vertically from view. Returns new view_id."""

       def focus_view(self, view_id: str):
           """Set focus to specific view"""

       def get_layout_state(self) -> Dict:
           """Get current layout for persistence"""

       def restore_layout(self, state: Dict):
           """Restore saved layout"""
   ```

2. Update `NavigationController` to use `UniversalLayoutManager`
   - Mobile: Uses single-column layout with view stack
   - Desktop: Uses multi-column layout with splits

3. Move Phase 5 split logic from OutputView to NavigationController
   - Generalize column/pane system for any view type
   - Maintain backward compatibility

**Testing:**
- Unit test: Layout operations work correctly
- Integration test: Mobile and desktop modes both work
- State test: Layout persists and restores correctly

---

### 3.2: Window Manager Integration
**Goal:** Any view can become a standalone window

**Steps:**
1. Create `src/fichero/shared/navigation/window_manager.py`
   ```python
   class WindowManager:
       """Manages standalone windows for views"""

       def __init__(self, app: toga.App):
           self.app = app
           self.windows: Dict[str, toga.Window] = {}

       def create_window(self, view: BaseViewInterface,
                        title: str = None) -> toga.Window:
           """Create standalone window for view"""

       def close_window(self, view_id: str):
           """Close window and cleanup"""

       def get_window(self, view_id: str) -> Optional[toga.Window]:
           """Get window for view if exists"""
   ```

2. Update NavigationController to integrate WindowManager
   - Track which views are windowed vs embedded
   - Handle view transitions (embed → window, window → embed)

3. Add menu commands for windowing views
   - "Open in New Window"
   - "Move to Main Window"

**Testing:**
- Integration test: View opens in new window
- Integration test: View moves between window and main
- State test: Window positions persist

---

### 3.3: Global Focus Tracking
**Goal:** Track current focused view across entire app

**Steps:**
1. Create `src/fichero/shared/focus/focus_tracker.py`
   ```python
   class FocusTracker:
       """Global focus tracking for all views"""

       def __init__(self):
           self.focused_view: Optional[BaseViewInterface] = None
           self.focus_history: List[str] = []
           self.listeners: List[Callable] = []

       def set_focus(self, view: BaseViewInterface):
           """Set focused view and notify listeners"""

       def get_focused(self) -> Optional[BaseViewInterface]:
           """Get currently focused view"""

       def subscribe(self, callback: Callable):
           """Subscribe to focus changes"""
   ```

2. Integrate FocusTracker with NavigationController
   - Update on view clicks
   - Update on window focus changes
   - Emit focus events

3. Update MainWindow to track context from focused view
   - Current library_id
   - Current collection_id
   - Current item_id
   - Current step_index

**Testing:**
- Unit test: Focus changes tracked correctly
- Integration test: Focus events fire correctly
- UI test: Visual focus indicator updates

---

### 3.4: Multiple Main Windows Support
**Goal:** Support multiple main windows, each with independent layouts

**Current:** Single main window with embedded views
**Target:** Multiple main windows, each can have full layout system

**Steps:**
1. Create `src/fichero/shared/navigation/main_window_manager.py`
   ```python
   class MainWindowManager:
       """Manages multiple main windows"""

       def __init__(self, app: toga.App):
           self.app = app
           self.main_windows: Dict[str, 'MainWindow'] = {}
           self.primary_window_id: str = None

       def create_main_window(self, title: str = "Fichero") -> str:
           """Create new main window. Returns window_id."""

       def close_main_window(self, window_id: str):
           """Close main window and cleanup"""

       def get_primary_window(self) -> 'MainWindow':
           """Get the primary/first main window"""

       def get_all_windows(self) -> List['MainWindow']:
           """Get all main windows"""
   ```

2. Update `MainWindow` class
   - Add `window_id` property
   - Each main window has own `UniversalLayoutManager`
   - Independent view layouts per window
   - Can transfer views between windows (drag & drop later)

3. Add menu commands
   - "New Main Window" (Cmd+Shift+N)
   - "Open Preview in New Window"
   - "Merge Windows" (move all views to single window)

**Testing:**
- Integration test: Multiple windows can be created
- Integration test: Each window has independent layout
- State test: All window states persist

---

### 3.5: Workspace Management System
**Goal:** Save and restore complete app state including all windows

**Steps:**
1. Create `src/fichero/shared/workspace/workspace_manager.py`
   ```python
   class WorkspaceManager:
       """Manages workspace save/load"""

       def __init__(self, app: toga.App):
           self.app = app
           self.workspace_dir = app.paths.data / "workspaces"
           self.current_workspace: Optional[str] = None

       def save_workspace(self, name: str = None) -> Path:
           """Save current workspace state. Returns path to workspace file."""

       def load_workspace(self, name: str) -> bool:
           """Load workspace from file. Returns success."""

       def get_workspace_list(self) -> List[str]:
           """Get list of saved workspaces"""

       def delete_workspace(self, name: str):
           """Delete saved workspace"""

       def get_current_state(self) -> Dict:
           """Get complete app state for saving"""

       def restore_state(self, state: Dict):
           """Restore app from saved state"""
   ```

2. Define workspace state schema:
   ```python
   {
       "version": "1.0",
       "timestamp": "2025-11-09T12:00:00",
       "windows": [
           {
               "window_id": "main_1",
               "type": "main",  # or "utility"
               "title": "Fichero",
               "position": {"x": 100, "y": 100},
               "size": {"width": 1200, "height": 800},
               "layout": {
                   "columns": [
                       {
                           "views": [
                               {
                                   "view_type": "sidebar",
                                   "view_id": "sidebar_1",
                                   "state": {...},
                                   "embedded_views": [
                                       {"view_type": "activity", "position": "bottom"}
                                   ]
                               }
                           ]
                       },
                       {
                           "views": [
                               {"view_type": "collection", ...},
                               {"view_type": "step", ...}
                           ]
                       },
                       {
                           "views": [
                               {"view_type": "preview", ...}
                           ]
                       }
                   ]
               }
           }
       ],
       "global_context": {
           "library_id": "lib_123",
           "collection_id": "coll_456",
           "item_id": "item_789",
           "step_index": 3
       },
       "focused_view": {
           "window_id": "main_1",
           "view_id": "preview_1"
       }
   }
   ```

3. Implement state collection:
   - Each view implements `get_state()` method
   - WindowManager tracks window positions/sizes
   - FocusTracker provides current focus
   - Global context from StateManager

4. Implement state restoration:
   - Create windows in saved positions
   - Recreate layout structure
   - Instantiate views with saved states
   - Restore global context
   - Set focus to saved view

5. Add menu commands:
   - "Save Workspace..." (Cmd+S prompts for name)
   - "Save Workspace As..." (always prompts)
   - "Load Workspace..." (shows list)
   - "Workspace" menu with recent workspaces
   - Auto-save current workspace on quit

**Testing:**
- Unit test: State serialization/deserialization
- Integration test: Save workspace preserves all data
- Integration test: Load workspace recreates exact state
- UI test: Windows appear in correct positions

---

### 3.6: Global State Manager
**Goal:** Track global application context (library/collection/item/step)

**Steps:**
1. Create `src/fichero/shared/state/state_manager.py`
   ```python
   class StateManager:
       """Global application state tracking"""

       def __init__(self):
           self.library_id: Optional[str] = None
           self.collection_id: Optional[str] = None
           self.item_id: Optional[str] = None  # file, folder, or URL
           self.step_index: Optional[int] = None
           self.listeners: List[Callable] = []

       def set_library(self, library_id: str):
           """Set current library and notify listeners"""

       def set_collection(self, collection_id: str):
           """Set current collection"""

       def set_item(self, item_id: str):
           """Set current item (file/folder/URL)"""

       def set_step(self, step_index: int):
           """Set current step"""

       def get_context(self) -> Dict[str, Any]:
           """Get complete current context"""

       def restore_context(self, context: Dict[str, Any]):
           """Restore context from saved state"""

       def subscribe(self, callback: Callable):
           """Subscribe to state changes"""
   ```

2. Integrate with views:
   - Views update StateManager when their context changes
   - Example: LibraryView selection → updates library_id
   - Example: StepView navigation → updates step_index

3. Link to FocusTracker:
   - When focus changes, context comes from focused view
   - StateManager reflects the "current" context for the app

**Testing:**
- Unit test: State updates fire events correctly
- Integration test: View changes update global state
- Integration test: State persists in workspace

---

## PHASE 4: JSON-to-UI Renderer (Week 4)

### 4.1: Reusable JSON Renderer
**Goal:** DRY principle for Inspector + AdjustView JSON rendering

**Current:** Inspector has custom JSON rendering code
**Target:** Shared renderer used by both Inspector and AdjustView

**Steps:**
1. Create `src/fichero/shared/ui/json_renderer.py`
   ```python
   class JSONRenderer:
       """Renders JSON to editable UI components"""

       def __init__(self, editable: bool = True):
           self.editable = editable

       def render(self, data: Dict, schema: Dict = None) -> toga.Box:
           """Render JSON data to UI widgets"""

       def get_values(self) -> Dict:
           """Extract current values from UI"""

       def set_values(self, data: Dict):
           """Update UI with new values"""

       # Field type renderers
       def render_string(self, key, value, schema)
       def render_number(self, key, value, schema)
       def render_boolean(self, key, value, schema)
       def render_array(self, key, value, schema)
       def render_object(self, key, value, schema)
   ```

2. Extract Inspector's JSON rendering to use JSONRenderer

3. Implement AdjustView using JSONRenderer
   - Load tool settings JSON
   - Render with JSONRenderer
   - Apply changes on save

**Testing:**
- Unit test: Each field type renders correctly
- Integration test: Values extract correctly
- Visual test: Editable and read-only modes work

**Verification:**
```python
renderer = JSONRenderer(editable=True)
data = {"name": "test", "value": 42, "enabled": True}
ui = renderer.render(data)

# User edits in UI
values = renderer.get_values()
assert values["name"] == "test"
```

---

## PHASE 5: View Refactoring (Week 5)

### 5.1: Create SidebarView (Rename + Enhance LibraryView)
**Goal:** Transform LibraryView into SidebarView with embedded view support

**Current:** LibraryView shows library list only
**Target:** SidebarView can embed other views (e.g., ActivityView at bottom)

**Steps:**
1. Rename `LibraryView` to `SidebarView`
   - Update all imports and references
   - Keep library functionality as primary content

2. Implement `BaseViewInterface`
   - Add required properties/methods
   - Add FocusBorder support

3. Replace `DetailedList` with `AbstractTreeList`
   - Tree view on macOS/Linux
   - Table on Windows
   - DetailedList on mobile

4. Add embedded view support:
   ```python
   class SidebarView(BaseViewInterface):
       def __init__(self, app, is_mobile):
           ...
           self.embedded_views: List[Tuple[BaseViewInterface, str]] = []
           # List of (view, position) where position = 'top' | 'bottom'

       def embed_view(self, view: BaseViewInterface, position: str = 'bottom'):
           """Embed another view in sidebar (e.g., ActivityView)"""

       def remove_embedded_view(self, view_id: str):
           """Remove embedded view"""

       def _rebuild_layout(self):
           """Rebuild container with main + embedded views"""
   ```

5. Default configuration:
   - Desktop: Sidebar with optional ActivityView at bottom (collapsible)
   - Mobile: Sidebar only (ActivityView in separate view)

**Testing:**
- Platform test: Correct widget on each platform
- Integration test: ActivityView embeds correctly
- Layout test: Resizable split between library and activity
- Window test: Opens in standalone window

---

### 5.2: Refactor CollectionView
**Goal:** Use AbstractTreeList, implement BaseViewInterface

**Steps:**
1. Update `CollectionView` to implement `BaseViewInterface`

2. Replace `DetailedList` with `AbstractTreeList`

3. Add standalone window support

**Testing:**
- Same as LibraryView

---

### 5.3: Refactor InspectorView
**Goal:** Use JSONRenderer, implement BaseViewInterface

**Steps:**
1. Update `InspectorView` to implement `BaseViewInterface`

2. Replace custom JSON rendering with `JSONRenderer`

3. Already supports windowing, integrate with WindowManager

**Testing:**
- Regression test: All existing functionality works
- Integration test: Works with new JSONRenderer

---

### 5.4: Refactor ActivityView
**Goal:** Use AbstractTreeList, implement BaseViewInterface

**Steps:**
1. Update `ActivityView` to implement `BaseViewInterface`

2. Replace `Tree` with `AbstractTreeList`
   - Works on mobile now (as DetailedList)

3. Integrate with WindowManager

**Testing:**
- Platform test: Works on all platforms including mobile
- Window test: Window management works

---

## PHASE 6: Resize Handles (Week 6)

### 6.1: Resizable Pane Separators
**Goal:** Drag separators to resize panes

**Steps:**
1. Implement `ResizableCanvas` from Phase 1.1
   - Visual separator line
   - Mouse drag detection
   - Resize events

2. Update `UniversalLayoutManager` to use `ResizableCanvas`
   - Insert between columns
   - Insert between rows
   - Handle resize events to adjust pane sizes

3. Add constraints
   - Minimum pane width/height
   - Maximum pane width/height
   - Snap to edges

**Testing:**
- Visual test: Separator renders correctly
- Interaction test: Dragging resizes panes
- Constraint test: Min/max respected

---

## PHASE 7: Integration & Polish (Week 7)

### 7.1: Update MainWindow
**Goal:** Use new NavigationController for all layout

**Steps:**
1. Refactor `MainWindow._create_layout()`
   - Use `UniversalLayoutManager` instead of custom boxes
   - Add views via `layout_manager.add_view()`
   - Support splits and resizing

2. Update state persistence
   - Save layout state
   - Save view states
   - Save window positions
   - Restore on startup

3. Update menu commands
   - Split view commands work on any view
   - Window commands work on any view

**Testing:**
- Integration test: All views work in new system
- State test: Layout persists correctly
- Regression test: Existing workflows still work

---

### 7.2: Mobile Compatibility
**Goal:** Ensure mobile still works with new architecture

**Steps:**
1. Test mobile navigation flow
   - View stack navigation
   - Toolbars positioned correctly
   - No desktop-only features exposed

2. Test platform widgets on mobile
   - AbstractTreeList → DetailedList
   - Toolbars scale correctly

**Testing:**
- Mobile test: All views work on mobile
- Navigation test: View stack works
- Visual test: UI elements render correctly

---

### 7.3: Documentation & Examples
**Goal:** Document new architecture

**Steps:**
1. Create architecture documentation
   - Component diagram
   - Flow diagrams
   - API reference

2. Create examples
   - How to create a new view
   - How to add view to layout
   - How to create standalone window

3. Update existing documentation

---

## Testing Strategy

### Unit Tests
- Each abstraction layer component
- Each view implements interface correctly
- Platform widget selection logic
- JSON renderer field types

### Integration Tests
- Views work in main window
- Views work in standalone windows
- Focus tracking across views
- State persistence and restoration
- Navigation controller layout operations

### Visual/Manual Tests
- Platform-specific widget rendering
- Focus borders on all views
- Resize handles work smoothly
- Layout persists correctly
- Mobile navigation flows

### Regression Tests
- Existing workflows still work
- No performance degradation
- Mobile compatibility maintained

---

## Migration Strategy

### Backward Compatibility
1. Keep old OutputView working during transition
2. Feature flag for new architecture
3. Parallel implementations until verified
4. Gradual cutover

### Data Migration
1. Layout state format may change
2. Provide migration function for old layouts
3. Graceful fallback if migration fails

---

## Risk Mitigation

### High-Risk Areas
1. **Navigation Controller Refactor** - Core component, affects everything
   - Mitigation: Feature flag, extensive testing, rollback plan

2. **View Extraction** - Breaking up OutputView
   - Mitigation: Keep old code, test thoroughly, gradual migration

3. **Platform Widget Abstraction** - Platform-specific behavior
   - Mitigation: Test on all platforms before each merge

### Rollback Plan
1. Feature flags allow disabling new system
2. Git tags at each phase completion
3. Old code preserved until full verification

---

## Success Criteria

### Phase 1-2 (Weeks 1-2)
- [ ] Platform widgets work on all platforms
- [ ] BaseViewInterface defined and tested
- [ ] StepView and AdjustView extracted
- [ ] PreviewView renamed, all tests pass

### Phase 3 (Weeks 3-4) - Extended for workspace features
- [ ] UniversalLayoutManager handles all layouts
- [ ] WindowManager creates standalone windows
- [ ] FocusTracker works globally
- [ ] **Multiple main windows support**
- [ ] **Workspace save/load system**
- [ ] **Global state manager**

### Phase 4 (Week 5)
- [ ] JSONRenderer works for Inspector
- [ ] AdjustView uses JSONRenderer
- [ ] Both views render correctly

### Phase 5 (Week 6)
- [ ] **SidebarView created with embedded view support**
- [ ] All views implement BaseViewInterface
- [ ] All list views use AbstractTreeList
- [ ] **ActivityView embeds in sidebar**
- [ ] All views support windowing

### Phase 6 (Week 7)
- [ ] Resize handles work smoothly
- [ ] Constraints respected
- [ ] Layout persists after resize

### Phase 7 (Week 8)
- [ ] MainWindow uses new architecture
- [ ] Mobile works correctly
- [ ] All tests pass
- [ ] Documentation complete

---

## Timeline

| Phase | Duration | Completion | Notes |
|-------|----------|------------|-------|
| Phase 1: Foundation | 1 week | Week 1 | Platform widgets, base interface |
| Phase 2: View Extraction | 1 week | Week 2 | StepView, AdjustView, PreviewView |
| Phase 3: Navigation | **2 weeks** | Week 3-4 | **Extended: +workspace, +multi-window** |
| Phase 4: JSON Renderer | 1 week | Week 5 | Reusable JSON-to-UI |
| Phase 5: View Refactor | 1 week | Week 6 | **SidebarView with embedded views** |
| Phase 6: Resize Handles | 1 week | Week 7 | Canvas-based resizing |
| Phase 7: Integration | 1 week | Week 8 | Final integration & polish |
| **Total** | **8 weeks** | | **+1 week for workspace features** |

---

## Next Steps

1. Review and approve this plan
2. Set up feature branch: `feature/phase6-universal-nav`
3. Begin Phase 1.1: Platform Widget Abstraction Layer
4. Create initial unit tests
5. Implement and verify each component

---

## Notes

- This is a significant architectural refactor
- Proceed carefully with extensive testing
- Each phase should be completable independently
- Can pause/adjust plan based on findings
- Keep main branch stable throughout
