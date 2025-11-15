# Phase 6: Universal Navigation System - Architecture Plan

## Overview

Phase 6 refactors Fichero's UI architecture to provide consistent, platform-adaptive navigation across desktop and mobile platforms using DRY principles.

## Current Status: Phase 1 - Platform Widget Abstraction Layer

### Completed:
- ✅ ResizableCanvas (drag handles for pane resizing)
- ✅ Existing toolbar system reviewed (BaseToolbar, ToolbarCoordinator)

### In Progress:
- 🔄 ListWidget (platform-adaptive list/table/tree abstraction)

---

## Phase 1: Platform Widget Abstraction Layer

### 1.1 ListWidget - Platform-Adaptive List Component ✅ IN PROGRESS

**Purpose**: Unified list abstraction that uses the best Toga widget for each platform while maintaining DRY principles and allowing future extensibility.

**Architecture**:
```
ListWidget
├── Platform Detection (respects FORCE_MOBILE_UI)
├── Native Renderer (uses Toga Sources)
│   ├── Desktop (macOS/Linux): toga.Table + ListSource
│   ├── Desktop (Windows): toga.Table + ListSource
│   ├── Mobile (iOS/Android): toga.DetailedList + ListSource
│   └── Hierarchical (optional): toga.Tree + TreeSource
└── Future: Pluggable Renderer System
    ├── HTMLRenderer (WebView + templates)
    ├── CardRenderer (custom Toga layouts)
    └── CustomRenderer (user-defined)
```

**Widget Capabilities Matrix**:
| Feature | Table | DetailedList | Tree |
|---------|-------|--------------|------|
| Platform | Desktop | Mobile | Desktop |
| Data Type | Flat/Multi-column | Flat/Single-item | Hierarchical |
| Source | ListSource | ListSource | TreeSource |
| on_select | ✅ | ✅ | ✅ |
| on_activate | ✅ | ❌ | ✅ |
| multiple_select | ✅ | ❌ | ✅ |
| on_primary_action | ❌ | ✅ (swipe-left) | ❌ |
| on_secondary_action | ❌ | ✅ (swipe-right) | ❌ |
| on_refresh | ❌ | ✅ (pull-down) | ❌ |
| Columns | ✅ | ❌ | ✅ |
| Hierarchy | ❌ | ❌ | ✅ |

**API Design**:
```python
class ListWidget:
    """Platform-adaptive list widget with extensible renderer system."""

    def __init__(
        self,
        headings: List[str],
        data: Optional[List[Dict]] = None,

        # Common callbacks
        on_select: Optional[Callable] = None,

        # Desktop-specific (Table/Tree)
        on_activate: Optional[Callable] = None,
        multiple_select: bool = False,

        # Mobile-specific (DetailedList)
        on_primary_action: Optional[Callable] = None,
        on_secondary_action: Optional[Callable] = None,
        on_refresh: Optional[Callable] = None,

        # Hierarchical data
        hierarchical: bool = False,  # Use Tree instead of Table

        # Future: Renderer selection
        # renderer_type: str = 'native',  # 'native', 'html', 'card', 'custom'
        # renderer: Optional[ListRenderer] = None,

        style: Optional[Pack] = None,
    ):
        ...
```

**Key Decisions**:
1. **Use Toga Sources**: Leverage ListSource/TreeSource instead of manual data conversion
2. **Table for flat lists**: Collections are flat lists, use Table (not Tree) on desktop
3. **Capability exposure**: Provide properties to query platform-specific features
4. **Renderer pattern**: Prepare architecture for future HTML/card renderers

**Implementation Tasks**:
- [x] Rename `AbstractTreeList` → `ListWidget`
- [x] Rename `abstract_tree_list.py` → `list_widget.py`
- [x] Rename test file
- [ ] Update class name and docstrings
- [ ] Implement ListSource/TreeSource usage
- [ ] Remove manual data conversion methods
- [ ] Add capability query properties
- [ ] Update library_view to use flat data (no fake children)
- [ ] Update __init__.py exports
- [ ] Test desktop and mobile modes

### 1.2 ResizableCanvas ✅ COMPLETE

Draggable resize handles for pane splitting.

- Status: Complete with 16 passing tests
- File: `src/fichero/shared/widgets/resizable_canvas.py`

### 1.3 FocusBorder System (Pending)

Generalize the focus border system from Phase 5.

---

## Phase 2: Base View Interface (Pending)

Create BaseViewInterface for consistent view management.

---

## Phase 3: Navigation State Management (Pending)

Unified navigation state tracking.

---

## Phase 4: View Transition System (Pending)

Smooth transitions between views.

---

## Phase 5: Mobile Optimization (Pending)

Mobile-specific navigation patterns.

---

## Future Extensions: Renderer System

### Design Philosophy:
- **Separation of Concerns**: Data (Sources) separate from Presentation (Renderers)
- **Progressive Enhancement**: Start with native widgets, add custom renderers as needed
- **Plugin Architecture**: Allow custom renderers without modifying core

### Renderer Types:

**1. NativeRenderer** (Current Implementation)
- Uses Toga's built-in widgets
- Platform-optimized
- Full accessibility support

**2. HTMLRenderer** (Future)
```python
collections_list = ListWidget(
    data=collections_data,
    renderer_type='html',
    html_template='<div class="card">{{name}}</div>',
    css_style='.card { border-radius: 8px; }',
)
```

**3. CardRenderer** (Future)
```python
collections_list = ListWidget(
    data=collections_data,
    renderer_type='card',
    layout='grid',  # or 'list'
)
```

**4. CustomRenderer** (Future)
```python
class FolderViewRenderer(ListRenderer):
    def render(self, data, container):
        # Custom implementation
        ...

collections_list = ListWidget(
    data=collections_data,
    renderer=FolderViewRenderer(),
)
```

---

## Testing Strategy

### Unit Tests:
- Platform detection (macOS, Windows, Linux, iOS, Android)
- FORCE_MOBILE_UI environment variable handling
- Data Source creation (ListSource, TreeSource)
- Capability queries
- Selection handling

### Integration Tests:
- Desktop mode (Table widget)
- Mobile mode (DetailedList widget)
- Hierarchical mode (Tree widget)
- Callback handling
- Data updates

---

## Migration Guide

### Before (AbstractTreeList):
```python
from fichero.shared.widgets import AbstractTreeList

tree_data = [
    {'icon': None, 'text': 'Item', 'children': []},  # Fake children!
]

list_widget = AbstractTreeList(
    headings=['Name'],
    data=tree_data,
    on_select=callback,
)
```

### After (ListWidget):
```python
from fichero.shared.widgets import ListWidget

flat_data = [
    {'icon': None, 'name': 'Item'},  # No children
]

list_widget = ListWidget(
    headings=['Name'],
    data=flat_data,
    on_select=callback,
    hierarchical=False,  # Explicit: this is a flat list
)
```

---

## Files Modified

### Created:
- `src/fichero/shared/widgets/list_widget.py` (renamed from abstract_tree_list.py)
- `tests/shared/widgets/test_list_widget.py` (renamed from test_abstract_tree_list.py)
- `PHASE_6_ARCHITECTURE.md` (this file)

### Modified:
- `src/fichero/shared/widgets/__init__.py` - Update exports
- `src/fichero/windows/main/views/library/library_view.py` - Use ListWidget

### Deleted:
- `src/fichero/shared/widgets/abstract_tree_list.py` (renamed)
- `tests/shared/widgets/test_abstract_tree_list.py` (renamed)

---

## Dependencies

- Toga 0.5.2
- Python 3.10+

## Notes

- This architecture prepares for future HTML/card renderers without requiring changes now
- The renderer pattern allows swapping presentation while keeping the same data layer
- Platform detection respects FORCE_MOBILE_UI for testing mobile UI on desktop
