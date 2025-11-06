# Phase 3 Design: Reusable UI Components

## Overview

Phase 3 creates reusable Toga UI components that will be used in the OutputView refactoring. These components follow the inspector pattern and can be embedded anywhere in the application.

## Components to Build

### 1. JsonEditor Component (`src/fichero/shared/components/json_editor.py`)

**Purpose**: Reusable JSON editor with syntax highlighting, validation, and edit capabilities.

**Key Features**:
- Displays JSON in a MultilineTextInput with monospace font
- Validates JSON on blur/save
- Shows validation errors inline
- Provides save/cancel actions
- Emits events when JSON is modified
- Can be in read-only mode

**API Design**:
```python
class JsonEditor:
    """Reusable JSON editor component inspired by inspector pattern"""

    def __init__(self, on_save=None, on_cancel=None, read_only=False):
        """
        Args:
            on_save: Callback when user saves (receives validated dict)
            on_cancel: Callback when user cancels
            read_only: If True, display only (no editing)
        """

    def set_data(self, data: Dict[str, Any]):
        """Load JSON data into editor"""

    def get_data(self) -> Optional[Dict[str, Any]]:
        """Get current JSON as dict (None if invalid)"""

    def validate(self) -> Tuple[bool, Optional[str]]:
        """Validate current JSON, returns (is_valid, error_message)"""

    def as_box(self) -> toga.Box:
        """Return the component as a Toga Box"""
```

**Layout**:
```
┌─────────────────────────────────────┐
│ JSON Editor                         │
├─────────────────────────────────────┤
│ {                                   │
│   "key": "value",                   │
│   "nested": {                       │
│     "data": 123                     │
│   }                                 │
│ }                                   │
│                                     │
│                                     │
├─────────────────────────────────────┤
│ ⚠ Error: Invalid JSON at line 5    │  (if error)
├─────────────────────────────────────┤
│ [Cancel] [Validate] [Save]          │  (if not read-only)
└─────────────────────────────────────┘
```

**Integration with Renderers**:
- JsonRenderer calls `renderer.get_editable_json()` to get dict
- JsonEditor loads the dict and displays it
- When user saves, JsonRenderer calls `renderer.apply_json_edits()` with new dict
- StepEditor writes changes back to files

---

### 2. MetadataViewer Component (`src/fichero/shared/components/metadata_viewer.py`)

**Purpose**: Reusable metadata display using key-value pairs, similar to inspector window.

**Key Features**:
- Displays metadata as formatted key-value pairs
- Supports nested dictionaries
- Handles different data types (strings, numbers, lists, dicts)
- Optional copy-to-clipboard for values
- Collapsible sections for nested data

**API Design**:
```python
class MetadataViewer:
    """Reusable metadata viewer component inspired by inspector pattern"""

    def __init__(self, title: str = "Metadata"):
        """
        Args:
            title: Title displayed at top of viewer
        """

    def set_metadata(self, metadata: Dict[str, Any]):
        """Load metadata to display"""

    def clear(self):
        """Clear all metadata"""

    def as_box(self) -> toga.Box:
        """Return the component as a Toga Box"""
```

**Layout**:
```
┌─────────────────────────────────────┐
│ Metadata                            │
├─────────────────────────────────────┤
│ General                             │
│   Step Name: prepare_images         │
│   File Type: image                  │
│   File Path: /path/to/file.jpg      │
│                                     │
│ Processing Details                  │
│   Processing Time: 1.23s            │
│   Status: completed                 │
│   Tool Version: 2.1.0               │
│                                     │
│ File Information                    │
│   Size: 2.4 MB                      │
│   Dimensions: 1920x1080             │
│   Format: JPEG                      │
└─────────────────────────────────────┘
```

**Integration with Renderers**:
- Renderers provide metadata via `RenderContext.manifest_entry`
- MetadataViewer formats and displays the metadata
- Can be used in OutputView sidebar (like inspector)
- Can be used in step detail views

---

## Code Sharing with Inspector

Both components follow the inspector pattern:

1. **Update Pattern**: Components have `set_data()`/`set_metadata()` methods that update content without recreating widgets
2. **Composition**: Components return `toga.Box` that can be embedded anywhere
3. **Event-Driven**: Components use callbacks for user actions
4. **Reusable**: Components are self-contained and can be used in multiple places

Example from Inspector:
```python
# Inspector pattern we're following
def update_metadata(self, metadata, selection_type: str = None):
    self.current_metadata = metadata
    if self.is_visible:
        self.refresh()
```

Similar in our components:
```python
# Our components follow same pattern
def set_data(self, data: Dict[str, Any]):
    self._data = data
    self._refresh_display()
```

---

## Usage in OutputView (Phase 4)

Once built, these components will be used in the refactored OutputView:

### Scenario 1: Viewing JSON Step Output
```python
# In OutputPane (Phase 4)
metadata_viewer = MetadataViewer("Step Information")
metadata_viewer.set_metadata(render_context.manifest_entry)

json_editor = JsonEditor(read_only=True)  # View mode
json_editor.set_data(render_context.file_content)

# Layout side by side or in split view
output_container.add(metadata_viewer.as_box())
output_container.add(json_editor.as_box())
```

### Scenario 2: Editing JSON Step Output
```python
# In OutputPane (Phase 4) - Edit mode
json_editor = JsonEditor(
    on_save=self._handle_json_save,
    on_cancel=self._handle_json_cancel,
    read_only=False
)
json_editor.set_data(step_data.file_content)

# When user clicks save
def _handle_json_save(self, new_data: Dict):
    # Use StepEditor to save changes
    await step_editor.save_step_json(item_id, step_index, new_data)
    # Update renderer with new data
    self.refresh()
```

### Scenario 3: Inspector Sidebar in OutputView
```python
# In OutputView (Phase 4) - Inspector sidebar
class OutputView:
    def __init__(self):
        self.metadata_viewer = MetadataViewer("Current Step")

    def on_step_selected(self, step_data):
        # Update sidebar with step metadata
        self.metadata_viewer.set_metadata({
            'Step Name': step_data.step_name,
            'File Type': step_data.file_type,
            'File Path': str(step_data.file_path),
            **step_data.manifest_entry
        })
```

---

## Testing Strategy

### JsonEditor Tests
- Test JSON loading and display
- Test validation (valid and invalid JSON)
- Test save/cancel callbacks
- Test read-only mode
- Test error display

### MetadataViewer Tests
- Test metadata loading
- Test nested dict display
- Test different data types
- Test empty metadata
- Test clear functionality

---

## Implementation Order

1. **MetadataViewer first** (simpler, read-only)
   - Build basic key-value display
   - Add nested dict support
   - Add styling

2. **JsonEditor second** (more complex, editing)
   - Build basic text editor
   - Add JSON validation
   - Add save/cancel actions
   - Add error display
   - Add read-only mode

3. **Integration testing**
   - Test in isolated window first
   - Test with real renderer data
   - Test in OutputView mockup

---

## Files to Create

```
src/fichero/shared/components/
├── __init__.py (update to export new components)
├── json_editor.py (~300-400 lines)
└── metadata_viewer.py (~200-300 lines)

tests/
├── test_json_editor.py (~150 lines)
└── test_metadata_viewer.py (~100 lines)
```

---

## Dependencies

**From Phase 2 (Already Complete)**:
- `RenderContext` dataclass
- `RenderedOutput` dataclass
- `JsonRenderer.get_editable_json()` method
- `JsonRenderer.apply_json_edits()` method
- `StepEditor.save_step_json()` method

**For Phase 3**:
- Toga widgets (Box, Label, MultilineTextInput, Button)
- JSON validation (built-in `json` module)
- Callback pattern (Python functions)

---

## Success Criteria

Phase 3 is complete when:
- ✅ JsonEditor component can display and edit JSON data
- ✅ JsonEditor validates JSON and shows errors
- ✅ JsonEditor supports read-only mode
- ✅ MetadataViewer can display nested metadata
- ✅ Both components can be embedded as `toga.Box`
- ✅ Both components have unit tests
- ✅ Components can be imported from `fichero.shared.components`

---

## Next: Phase 4

Once Phase 3 is complete, Phase 4 will use these components to refactor OutputView:
- Create StepManager (UI state management)
- Create LayoutManager (split view configurations)
- Create OutputPane (reusable output display using our components)
- Refactor main OutputView file (3,039 → ~300 lines)
- Integrate inspector sidebar (using MetadataViewer)

The components built in Phase 3 become the building blocks for Phase 4's modular OutputView architecture.
