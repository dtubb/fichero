# Phase 4 Design: OutputView Refactoring

## Goal
Refactor the monolithic 3,039-line OutputView into a clean, modular system using Phase 2 renderers and Phase 3 components.

## Target
- **Before:** `output_view.py` = 3,039 lines (everything mixed together)
- **After:** `output_view.py` = ~300 lines (orchestrator only)
- **New Components:**
  - `step_manager.py` (~200 lines) - UI state management
  - `layout_manager.py` (~300 lines) - Split view system
  - `output_pane.py` (~400 lines) - Reusable output display

## Problem Analysis

### Current OutputView Issues (from reading output_view.py:1-250)

1. **Massive command definitions** (lines 105-250+)
   - Dozens of commands defined inline
   - Zoom, rotate, crop, navigation, etc.
   - Should be factored out to managers

2. **Complex state management**
   - `current_item_id`, `current_step_index`, `current_file_index`
   - `left_step_index`, `right_step_index`, `split_mode`
   - `source_files`, `source_item_ids`
   - All mixed together with no clear owner

3. **Mixed concerns**
   - Toolbar setup mixed with rendering
   - Navigation mixed with layout
   - State mixed with presentation

4. **No reusability**
   - Can't create multiple output views
   - Can't detach windows
   - Can't reuse output display logic

## Architecture

### Layer Separation

```
┌─────────────────────────────────────────────────────────────┐
│                     OutputView (300 lines)                  │
│                     - Orchestrator only                      │
│                     - Creates managers                       │
│                     - Delegates everything                   │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
┌──────────────────┐ ┌─────────────┐ ┌────────────────┐
│  StepManager     │ │ LayoutMgr   │ │   OutputPane   │
│  (200 lines)     │ │ (300 lines) │ │   (400 lines)  │
│                  │ │             │ │                │
│  State:          │ │ Layouts:    │ │ Display:       │
│  - Current step  │ │ - Single    │ │ - Uses         │
│  - Current file  │ │ - Two pane  │ │   renderers    │
│  - Navigation    │ │ - Three     │ │ - WebView      │
│                  │ │ - Four      │ │ - Zoom/rotate  │
│  Methods:        │ │             │ │                │
│  - next_step()   │ │ Methods:    │ │ Methods:       │
│  - prev_step()   │ │ - set_layout│ │ - set_step()   │
│  - next_file()   │ │ - add_pane  │ │ - render()     │
│  - prev_file()   │ │ - detach    │ │ - zoom()       │
└──────────────────┘ └─────────────┘ └────────────────┘
         │                              │
         │                              │
         ▼                              ▼
┌──────────────────┐         ┌────────────────────┐
│  LibraryManager  │         │  RendererRegistry  │
│  (Data source)   │         │  (Phase 2)         │
└──────────────────┘         └────────────────────┘
```

### Data Flow

```
User Action → StepManager updates state
           → StepManager emits event
           → OutputView receives event
           → OutputView tells OutputPane(s) to render
           → OutputPane gets renderer from registry
           → OutputPane renders content
```

## Component Design

### 1. StepManager (State Management)

**File:** `src/fichero/windows/main/views/output/step_manager.py`

**Responsibilities:**
- Track current step index, file index
- Handle navigation (next/prev step/file)
- Manage item_id list for file navigation
- Emit events when state changes
- NO rendering, NO UI creation, NO HTML generation

**API:**

```python
from typing import Optional, List, Callable
from dataclasses import dataclass

@dataclass
class StepState:
    """Current state of step navigation"""
    item_id: str
    step_index: int
    total_steps: int
    file_index: int
    total_files: int
    can_go_prev_step: bool
    can_go_next_step: bool
    can_go_prev_file: bool
    can_go_next_file: bool


class StepManager:
    """
    Manages navigation state for OutputView.

    Pure state management - no UI, no rendering.
    Emits events when state changes.

    Example:
        manager = StepManager(library_manager)
        manager.on_state_changed = lambda state: print(f"Now at step {state.step_index}")

        await manager.load_item("item-123")
        manager.next_step()  # Emits event
        manager.prev_file()  # Emits event
    """

    def __init__(self, library_manager):
        """Initialize with library manager for data access"""
        self.library_manager = library_manager
        self.current_item_id: Optional[str] = None
        self.current_step_index: int = 0
        self.current_file_index: int = 0
        self.item_ids: List[str] = []
        self.on_state_changed: Optional[Callable[[StepState], None]] = None

    async def load_item(self, item_id: str) -> bool:
        """Load an item and its steps"""
        ...

    async def load_item_list(self, item_ids: List[str], initial_index: int = 0):
        """Load a list of items for navigation"""
        ...

    def get_state(self) -> StepState:
        """Get current navigation state"""
        ...

    def next_step(self) -> bool:
        """Move to next step (returns False if can't)"""
        ...

    def prev_step(self) -> bool:
        """Move to previous step"""
        ...

    def next_file(self) -> bool:
        """Move to next file in list"""
        ...

    def prev_file(self) -> bool:
        """Move to previous file in list"""
        ...

    def go_to_step(self, step_index: int) -> bool:
        """Jump to specific step"""
        ...

    def go_to_file(self, file_index: int) -> bool:
        """Jump to specific file"""
        ...

    async def get_current_step_data(self) -> dict:
        """Get current step's data from library"""
        ...

    def _emit_state_change(self):
        """Emit state changed event"""
        if self.on_state_changed:
            self.on_state_changed(self.get_state())
```

### 2. LayoutManager (Split Views)

**File:** `src/fichero/windows/main/views/output/layout_manager.py`

**Responsibilities:**
- Manage split view configurations
- Create and arrange OutputPane instances
- Handle layout switching (single → dual → triple)
- Support detached windows (Phase 5)

**API:**

```python
from typing import List, Optional
from enum import Enum
import toga
from toga.style import Pack

class LayoutType(Enum):
    """Supported layout types"""
    SINGLE = "single"           # [Output]
    DUAL = "dual"               # [Output | Inspector]
    DUAL_COMPARE = "dual_compare"  # [Output | Output]
    TRIPLE = "triple"           # [Output | Inspector | Output]
    QUAD = "quad"               # [Output | Inspector | Output | Inspector]


class LayoutManager:
    """
    Manages split view layouts for OutputView.

    Creates and arranges OutputPane instances.
    Handles layout switching and pane synchronization.

    Example:
        manager = LayoutManager()

        # Single pane
        manager.set_layout(LayoutType.SINGLE)
        manager.get_primary_pane().set_step(item_id, step_index)

        # Dual pane comparison
        manager.set_layout(LayoutType.DUAL_COMPARE)
        manager.get_pane(0).set_step(item_id, step_index=0)
        manager.get_pane(1).set_step(item_id, step_index=1)
    """

    def __init__(self, library_manager, renderer_registry):
        """Initialize with library and renderer dependencies"""
        self.library_manager = library_manager
        self.renderer_registry = renderer_registry
        self.current_layout: LayoutType = LayoutType.SINGLE
        self.panes: List[OutputPane] = []
        self._container = None
        self._build_ui()

    def _build_ui(self):
        """Build container for panes"""
        self._container = toga.Box(
            style=Pack(direction='row', flex=1)
        )

    def set_layout(self, layout_type: LayoutType):
        """
        Switch to a different layout.

        Creates/removes panes as needed.
        """
        ...

    def get_container(self) -> toga.Box:
        """Get the layout container for embedding"""
        return self._container

    def get_primary_pane(self) -> 'OutputPane':
        """Get the main/primary output pane"""
        return self.panes[0] if self.panes else None

    def get_pane(self, index: int) -> Optional['OutputPane']:
        """Get pane by index"""
        return self.panes[index] if index < len(self.panes) else None

    def get_all_panes(self) -> List['OutputPane']:
        """Get all active panes"""
        return self.panes.copy()

    def sync_pane_state(self, source_pane: 'OutputPane'):
        """
        Sync viewer state (zoom, rotation) across all panes.

        Used when user wants same zoom level in multiple views.
        """
        ...

    def _create_pane(self) -> 'OutputPane':
        """Create a new output pane"""
        return OutputPane(self.library_manager, self.renderer_registry)

    def _arrange_panes(self):
        """Arrange panes based on current layout"""
        ...
```

### 3. OutputPane (Reusable Display)

**File:** `src/fichero/windows/main/views/output/output_pane.py`

**Responsibilities:**
- Display a single step's output
- Use renderers from Phase 2
- Handle zoom, rotation, scrolling
- Support both WebView (HTML) and native widgets
- Reusable - can be embedded anywhere

**API:**

```python
from typing import Optional, Dict, Any
import toga
from toga.style import Pack
from fichero.library.renderers import RendererRegistry

class OutputPane:
    """
    Reusable output display pane.

    Uses renderer system to display any step's output.
    Supports zoom, rotation, and scrolling.
    Can be embedded anywhere (OutputView, detached window, etc.)

    Example:
        pane = OutputPane(library_manager, renderer_registry)
        await pane.set_step("item-123", step_index=2)

        # Zoom controls
        pane.zoom_in()
        pane.zoom_fit()

        # Get container for embedding
        container.add(pane.as_box())
    """

    def __init__(self, library_manager, renderer_registry: RendererRegistry):
        """Initialize with dependencies"""
        self.library_manager = library_manager
        self.renderer_registry = renderer_registry

        # Current state
        self.current_item_id: Optional[str] = None
        self.current_step_index: Optional[int] = None

        # Viewer state
        self.scale: float = 1.0
        self.rotation: int = 0  # 0, 90, 180, 270
        self.scroll_x: int = 0
        self.scroll_y: int = 0

        # UI components
        self._container = None
        self._webview = None
        self._error_label = None
        self._loading_label = None

        self._build_ui()

    def _build_ui(self):
        """Build UI components"""
        # Main container
        self._container = toga.Box(
            style=Pack(direction='column', flex=1)
        )

        # Loading state
        self._loading_label = toga.Label(
            "Loading...",
            style=Pack(
                text_align='center',
                margin=20,
                font_size=14
            )
        )

        # Error state
        self._error_label = toga.Label(
            "",
            style=Pack(
                text_align='center',
                margin=20,
                color='#CC0000',
                font_size=12
            )
        )

        # WebView for HTML rendering
        self._webview = toga.WebView(
            style=Pack(flex=1)
        )

        # Initially show loading
        self._show_loading()

    async def set_step(self, item_id: str, step_index: int):
        """
        Load and display a step's output.

        Uses renderer system to generate appropriate display.
        """
        self.current_item_id = item_id
        self.current_step_index = step_index

        try:
            self._show_loading()

            # Get step data from library
            step_data = await self.library_manager.get_step_data(item_id, step_index)

            # Get renderer for this step
            renderer = self.renderer_registry.get_renderer(step_data['tool_name'])

            # Render to HTML
            rendered = await renderer.render_html(step_data)

            # Display in WebView
            self._webview.set_content(
                root_url=str(step_data['output_path']),
                content=rendered.html
            )

            self._show_content()

        except Exception as e:
            logger.error(f"Error rendering step: {e}")
            self._show_error(str(e))

    def as_box(self) -> toga.Box:
        """Get container for embedding"""
        return self._container

    # Zoom methods
    def zoom_in(self):
        """Zoom in by 10%"""
        self.scale = min(self.scale + 0.1, 5.0)
        self._apply_viewer_state()

    def zoom_out(self):
        """Zoom out by 10%"""
        self.scale = max(self.scale - 0.1, 0.1)
        self._apply_viewer_state()

    def zoom_fit(self):
        """Fit to window"""
        # Calculate appropriate scale
        self.scale = 1.0  # Simplified
        self._apply_viewer_state()

    def zoom_100(self):
        """Reset to 100%"""
        self.scale = 1.0
        self._apply_viewer_state()

    # Rotation methods
    def rotate_left(self):
        """Rotate 90° counter-clockwise"""
        self.rotation = (self.rotation - 90) % 360
        self._apply_viewer_state()

    def rotate_right(self):
        """Rotate 90° clockwise"""
        self.rotation = (self.rotation + 90) % 360
        self._apply_viewer_state()

    def reset_rotation(self):
        """Reset rotation to 0°"""
        self.rotation = 0
        self._apply_viewer_state()

    def get_viewer_state(self) -> Dict[str, Any]:
        """Get current viewer state for syncing"""
        return {
            'scale': self.scale,
            'rotation': self.rotation,
            'scroll_x': self.scroll_x,
            'scroll_y': self.scroll_y
        }

    def set_viewer_state(self, state: Dict[str, Any]):
        """Set viewer state (for syncing across panes)"""
        self.scale = state.get('scale', 1.0)
        self.rotation = state.get('rotation', 0)
        self.scroll_x = state.get('scroll_x', 0)
        self.scroll_y = state.get('scroll_y', 0)
        self._apply_viewer_state()

    def _apply_viewer_state(self):
        """Apply current zoom/rotation/scroll to WebView"""
        # Execute JavaScript to apply transform
        js = f"""
        document.body.style.transform =
            'scale({self.scale}) rotate({self.rotation}deg)';
        window.scrollTo({self.scroll_x}, {self.scroll_y});
        """
        self._webview.evaluate_javascript(js)

    def _show_loading(self):
        """Show loading state"""
        self._container.clear()
        self._container.add(self._loading_label)

    def _show_error(self, error: str):
        """Show error state"""
        self._error_label.text = f"Error: {error}"
        self._container.clear()
        self._container.add(self._error_label)

    def _show_content(self):
        """Show content (WebView)"""
        self._container.clear()
        self._container.add(self._webview)
```

### 4. Refactored OutputView

**File:** `src/fichero/windows/main/views/output/output_view.py` (300 lines, down from 3,039)

**What it does:**
- Creates StepManager, LayoutManager
- Registers commands (using managers for implementation)
- Sets up toolbars
- Delegates everything to managers

**What it DOESN'T do:**
- ❌ HTML generation (renderers do this)
- ❌ State tracking (StepManager does this)
- ❌ Layout management (LayoutManager does this)
- ❌ Rendering (OutputPane does this)

**Simplified structure:**

```python
class OutputView(BaseView, ViewCommandMixin):
    """
    Output view orchestrator (REFACTORED from 3,039 lines to ~300).

    Delegates to:
    - StepManager: State and navigation
    - LayoutManager: Layout and panes
    - Renderers: Content generation
    - Phase 3 components: Inspector sidebar
    """

    def __init__(self, app, is_mobile=False, library_manager=None):
        """Initialize with dependencies"""
        self.library_manager = library_manager

        # Create managers
        self.step_manager = StepManager(library_manager)
        self.step_manager.on_state_changed = self._on_step_state_changed

        self.layout_manager = LayoutManager(
            library_manager,
            app.renderer_registry
        )

        # Create inspector sidebar (Phase 3)
        self.inspector = self._create_inspector()

        # Create main layout
        self._build_ui()

        # Setup toolbars
        self._setup_toolbars()

    def _build_ui(self):
        """Build main layout"""
        # Main split: [Output | Inspector]
        self.main_container = toga.Box(style=Pack(direction='row', flex=1))

        # Add layout manager's container (handles panes)
        self.main_container.add(self.layout_manager.get_container())

        # Add inspector sidebar (initially hidden)
        self.main_container.add(self.inspector.as_box())

    def _on_step_state_changed(self, state: StepState):
        """Handle step state changes"""
        # Update primary pane
        pane = self.layout_manager.get_primary_pane()
        await pane.set_step(state.item_id, state.step_index)

        # Update inspector
        step_data = await self.step_manager.get_current_step_data()
        self.inspector.set_metadata(step_data['metadata'])

    # Command handlers delegate to managers
    def _on_next_step(self, widget):
        """Next step command"""
        self.step_manager.next_step()

    def _on_prev_step(self, widget):
        """Previous step command"""
        self.step_manager.prev_step()

    def _on_zoom_in(self, widget):
        """Zoom in command"""
        pane = self.layout_manager.get_primary_pane()
        pane.zoom_in()

    # ... other command handlers (all delegate)

    async def load_output(self, item_id: str):
        """Load an item's output (main entry point)"""
        await self.step_manager.load_item(item_id)

    def _create_inspector(self):
        """Create inspector sidebar using Phase 3 components"""
        from fichero.shared.components import MetadataViewer, JsonEditor

        # Create inspector box
        inspector_box = toga.Box(
            style=Pack(direction='column', width=300)
        )

        # Add metadata viewer
        self.metadata_viewer = MetadataViewer("Step Information")
        inspector_box.add(self.metadata_viewer.as_box())

        # Add JSON editor (initially hidden)
        self.json_editor = JsonEditor(
            on_save=self._on_inspector_save,
            read_only=True
        )
        inspector_box.add(self.json_editor.as_box())

        return inspector_box
```

## Integration with Phase 2 & 3

### Phase 2 Renderers

OutputPane uses the renderer system:

```python
# In OutputPane.set_step()
renderer = self.renderer_registry.get_renderer(step_data['tool_name'])
rendered = await renderer.render_html(step_data)
self._webview.set_content(rendered.html)
```

### Phase 3 Components

OutputView embeds Phase 3 components:

```python
# In OutputView._create_inspector()
from fichero.shared.components import MetadataViewer, JsonEditor

self.metadata_viewer = MetadataViewer("Step Information")
self.json_editor = JsonEditor(on_save=self._on_inspector_save)
```

## Implementation Order

### Step 1: Create StepManager (Simplest)
- Pure state management
- No UI dependencies
- Easy to unit test
- **Estimated:** 200 lines

### Step 2: Create OutputPane (Core Display)
- Uses renderers from Phase 2
- Self-contained rendering logic
- Can be tested with sample data
- **Estimated:** 400 lines

### Step 3: Create LayoutManager (Composition)
- Creates and arranges OutputPanes
- Handles split views
- **Estimated:** 300 lines

### Step 4: Refactor OutputView (Orchestration)
- Replace inline logic with manager calls
- Clean up command definitions
- Remove HTML generation
- **Estimated:** 300 lines (down from 3,039)

## Testing Strategy

### Unit Tests

**StepManager Tests** (`test_step_manager.py`):
```python
- test_create_step_manager()
- test_load_item()
- test_next_prev_step()
- test_next_prev_file()
- test_state_change_events()
- test_navigation_boundaries()
- test_go_to_step()
```

**OutputPane Tests** (`test_output_pane.py`):
```python
- test_create_output_pane()
- test_set_step()
- test_zoom_in_out()
- test_zoom_fit()
- test_rotate_left_right()
- test_viewer_state_sync()
- test_error_handling()
- test_loading_state()
```

**LayoutManager Tests** (`test_layout_manager.py`):
```python
- test_create_layout_manager()
- test_set_layout_single()
- test_set_layout_dual()
- test_set_layout_triple()
- test_get_panes()
- test_sync_pane_state()
```

### Integration Tests

**OutputView Integration** (`test_output_view_integration.py`):
```python
- test_load_output()
- test_step_navigation()
- test_file_navigation()
- test_zoom_commands()
- test_inspector_integration()
- test_layout_switching()
```

## Success Criteria

### Code Quality
- ✅ No file over 500 lines
- ✅ Clear separation of concerns
- ✅ Each component has single responsibility
- ✅ All components reusable

### Functionality
- ✅ All current features preserved
- ✅ Step navigation works
- ✅ File navigation works
- ✅ Zoom/rotate works
- ✅ Inspector sidebar works
- ✅ Split views work

### Testing
- ✅ 20+ unit tests (all components)
- ✅ 6+ integration tests
- ✅ All tests passing

### Maintainability
- ✅ Easy to find code
- ✅ Easy to add features
- ✅ Easy to debug
- ✅ Well documented

## Migration Notes

### For Developers

**Old way (3,039 lines):**
```python
# Everything in OutputView
output_view.current_step_index = 2
output_view._render_html(step_data)
output_view._update_toolbar()
```

**New way (modular):**
```python
# Managers handle their concerns
output_view.step_manager.go_to_step(2)
# Step manager emits event
# Event handler updates pane
# Pane uses renderer
```

### Breaking Changes

None - this is an internal refactoring. Public API remains the same:
- `OutputView.load_output(item_id)` still works
- Commands still work
- Toolbar still works

## Timeline

- **Day 1**: Create StepManager + tests
- **Day 2**: Create OutputPane + tests
- **Day 3**: Create LayoutManager + tests
- **Day 4**: Refactor OutputView + integration tests
- **Day 5**: Testing, cleanup, documentation

## Next Phase

**Phase 5** will add:
- Multiple view support (side-by-side step comparisons)
- Detached window support (pop out views)
- Edit-save-reprocess workflow (using Phase 3 JsonEditor)

These features are easy to add once Phase 4 is complete because:
- OutputPane is reusable (can create multiple)
- LayoutManager is extensible (can add new layouts)
- StepManager is decoupled (can have multiple instances)
