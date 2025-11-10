# Navigation Refactor Progress Tracker

**Last Updated**: 2025-11-10
**Current Step**: 1.1 - Platform Widget Abstraction Layer → Native Rendering Complete
**Status**: ✅ PHASE 1.1 COMPLETE - Ready for Phase 1.2

---

## Quick Status

| Step | Component | Status | Completion % |
|------|-----------|--------|--------------|
| **1.1** | **Platform Widget Abstraction** | ✅ COMPLETE | **100%** |
| 1.1.1 | ListWidget (renamed from AbstractTreeList) | ✅ COMPLETE | 100% |
| 1.1.2 | ResizableCanvas | ✅ COMPLETE | 100% |
| 1.1.3 | Toolbar System | ✅ REVIEWED | 100% |
| 1.1.4 | Use Toga Sources (ListSource/TreeSource) | ✅ COMPLETE | 100% |
| 1.1.5 | Renderer Architecture | ✅ COMPLETE | 100% |
| **1.2** | **Base View Interface** | ⏸️ NEXT | 0% |
| **1.3** | **Focus Border System** | ⏸️ PENDING | 0% |

---

## Current Session Work (2025-11-10)

### ✅ Completed Today:

1. **ListWidget Module Structure**
   - Converted single file to module: `src/fichero/shared/widgets/list_widget/`
   - Created `base.py` - Core ListWidget with source management
   - Created `renderers/__init__.py` - Renderer base class
   - Created `renderers/native.py` - Native Toga widgets (Table/Tree/DetailedList)
   - Created `renderers/card.py` - Card renderer (placeholder)
   - Created `renderers/html.py` - HTML renderer (placeholder)
   - Implemented source-based architecture with ListSource/TreeSource

2. **Native Rendering Implementation**
   - CollectionView: Converted to use ListWidget with native rendering
   - LibraryView: Converted to use ListWidget with native rendering
   - StepBrowser: Converted to use ListWidget with native rendering
   - Fixed widget update issue - Force recreation when data changes
   - All three views now use consistent native widget system

3. **Critical Bug Fix: Widget Data Updates**
   - **Problem**: Collection/library switching didn't update display
   - **Root Cause**: Toga widgets don't refresh when source data changes
   - **Solution**: Force complete widget recreation on data changes
     - Library view: Always call `_recreate_detailed_list()`
     - Collection view: Call `_create_content()` in `_update_items_list()`
   - Result: Collection switching now works correctly ✅

4. **Git Commits**
   - Commit 4c30ff3: "Fix collection/library view widget updates by forcing recreation"
   - Commit ef7bda2: "Convert StepBrowser to use ListWidget with native rendering"
   - Pushed to branch: `feature/phase6-universal-nav`

---

## Current Session Work (2025-11-09)

### ✅ Completed Today:

1. **ListWidget Refactor**
   - Renamed `AbstractTreeList` → `ListWidget`
   - Renamed files: `abstract_tree_list.py` → `list_widget.py`
   - Updated all imports across codebase
   - Updated exports in `__init__.py`
   - Updated test file and class names
   - All 11 tests passing ✅

2. **Architecture Documentation**
   - Created `LIST_WIDGET_ARCHITECTURE.md` with complete plan
   - Documented renderer pattern for future extensibility
   - Created migration guide
   - Documented platform capabilities matrix

3. **Code Organization**
   - Created `docs/architecture/navigation_refactor/` directory
   - Created `PROGRESS_TRACKER.md` (this file)
   - Organized all architecture docs in proper location
   - Updated CLAUDE.md with documentation references
   - Prepared for list_widget module structure

### 🔄 In Progress:

1. **ListWidget Module Structure**
   - Converting single file to module for extensibility
   - Will enable separate renderer files (native, HTML, card)

### 🔄 Current Issues (2025-11-09):

**Selection Handling Complexity:**
- Tree widget returns Node objects with accessor attributes (e.g., `node.collections`)
- Table widget returns Row objects with accessor attributes (e.g., `row.text`, `row._item_id`)
- DetailedList returns dict objects
- This creates fragile selection handling code with many special cases

**Root Cause:**
- ListWidget currently passes raw data to each widget type
- Each widget converts data differently (Tree uses tuples, Table uses dicts with accessors, DetailedList uses dicts)
- Selection returns different object types depending on widget
- Wrapper code (`_on_tree_select`) becomes complex trying to handle all cases

**Proposed Solution - Use Toga Sources:**
1. ListWidget should manage its own data source (ListSource or TreeSource)
2. Data flows: Library → ListWidget → Source → Widget
3. ListWidget updates source when data changes
4. Selection handling becomes uniform (Row objects from source)
5. Simplifies adding new renderers (HTML, Card, etc.)

### 📋 Implementation Plan (READY TO IMPLEMENT):

#### Overview

Convert ListWidget from single file to module with source-based architecture and multiple renderer support.

#### Module Structure

```
src/fichero/shared/widgets/list_widget/
├── __init__.py              # Public API, exports ListWidget
├── base.py                  # Core ListWidget class with source management
├── renderers/
│   ├── __init__.py         # Renderer base class
│   ├── native.py           # Table/Tree/DetailedList (current implementation)
│   ├── html.py             # WebView with HTML templates
│   └── card.py             # Custom Toga layouts in card style
└── templates/
    ├── html/
    │   ├── list_default.html
    │   ├── list_compact.html
    │   ├── list_detailed.html
    │   └── styles/ (CSS files)
    └── card/ (Python card layout files)
```

#### Step-by-Step Implementation

**Step 1: Create Module Structure**

```bash
mkdir -p src/fichero/shared/widgets/list_widget/renderers
mkdir -p src/fichero/shared/widgets/list_widget/templates/html/styles
mkdir -p src/fichero/shared/widgets/list_widget/templates/card
```

**Step 2: Implement Source-Based ListWidget (base.py)**

Key changes from current list_widget.py:

```python
from toga.sources import ListSource, TreeSource

class ListWidget:
    def __init__(self, headings, data=None, on_select=None, renderer='native', renderer_style='default', ...):
        self.headings = headings
        self._source = None  # Will be ListSource or TreeSource
        self._renderer_type = renderer  # 'native', 'html', 'card'
        self._renderer_style = renderer_style  # 'default', 'compact', 'detailed'
        self._on_select_callback = on_select

        # Create renderer
        self.renderer = self._create_renderer()

        # Create widget via renderer
        self.widget = self.renderer.create_widget()

        if data:
            self.set_data(data)

    def set_data(self, data):
        """Update source with new data - widgets auto-update"""
        self._data = data

        # Convert to source format
        source_data = self.renderer.convert_to_source_format(data)

        # Create or update source
        if self._source is None:
            accessors = self.renderer.get_accessors(self.headings)
            self._source = ListSource(accessors=accessors, data=source_data)
            self.renderer.attach_source(self._source)
        else:
            self._source.clear()
            for item in source_data:
                self._source.append(item)

    def _handle_select(self, widget):
        """Unified selection handler - all renderers return Row objects"""
        if not self._on_select_callback:
            return

        selection = widget.selection
        # All renderers now return Row objects with consistent accessors!
        self._on_select_callback(selection)
```

**Step 3: Renderer Base Class (renderers/__init__.py)**

```python
from abc import ABC, abstractmethod

class Renderer(ABC):
    """Base class for all list renderers"""

    def __init__(self, headings, on_select=None, style='default'):
        self.headings = headings
        self.on_select = on_select
        self.style = style
        self.source = None

    @abstractmethod
    def create_widget(self):
        """Create and return the Toga widget"""
        pass

    @abstractmethod
    def get_accessors(self, headings):
        """Return list of accessor names for the source"""
        pass

    @abstractmethod
    def convert_to_source_format(self, data):
        """Convert app data to source-compatible format"""
        pass

    def attach_source(self, source):
        """Attach source to widget"""
        self.source = source
```

**Step 4: NativeRenderer (renderers/native.py)**

Move current Table/Tree/DetailedList logic here:

```python
import toga
from toga.sources import ListSource
from . import Renderer

class NativeRenderer(Renderer):
    """Renderer using native Toga widgets (Table/Tree/DetailedList)"""

    def __init__(self, headings, on_select=None, style='default', platform=None, widget_type=None):
        super().__init__(headings, on_select, style)
        self.platform = platform
        self.widget_type = widget_type  # 'table', 'tree', 'detailedlist'
        self.widget = None

    def create_widget(self):
        if self.widget_type == 'table':
            self.widget = toga.Table(
                headings=self.headings,
                on_select=self.on_select,
            )
        elif self.widget_type == 'tree':
            self.widget = toga.Tree(
                headings=self.headings,
                on_select=self.on_select,
            )
        elif self.widget_type == 'detailedlist':
            self.widget = toga.DetailedList(
                on_select=self.on_select,
            )
        return self.widget

    def get_accessors(self, headings):
        """Return accessor names"""
        base = [h.lower() for h in headings]  # 'Collections' → 'collections'
        custom = ['icon', '_collection_data', '_item_id']
        return base + custom

    def convert_to_source_format(self, data):
        """Convert app data to source dicts"""
        result = []
        accessor = self.headings[0].lower() if self.headings else 'text'

        for item in data:
            source_item = {
                accessor: item.get('text', 'Untitled'),
                'icon': item.get('icon'),
                '_collection_data': item.get('_collection_data'),
                '_item_id': item.get('_item_id'),
            }
            result.append(source_item)
        return result

    def attach_source(self, source):
        """Attach source to widget"""
        self.source = source
        if self.widget:
            self.widget.data = source
```

**Step 5: HTMLRenderer (renderers/html.py)**

```python
import toga
from . import Renderer

class HTMLRenderer(Renderer):
    """Renderer using WebView with HTML templates"""

    TEMPLATES = {
        'default': 'templates/html/list_default.html',
        'compact': 'templates/html/list_compact.html',
        'detailed': 'templates/html/list_detailed.html',
    }

    def create_widget(self):
        self.webview = toga.WebView(on_webview_load=self._on_load)
        return self.webview

    def get_accessors(self, headings):
        base = [h.lower() for h in headings]
        custom = ['icon', '_collection_data', '_item_id']
        return base + custom

    def convert_to_source_format(self, data):
        """Same as native - we use the source"""
        accessor = self.headings[0].lower() if self.headings else 'text'
        result = []
        for item in data:
            source_item = {
                accessor: item.get('text', 'Untitled'),
                'icon': item.get('icon'),
                '_collection_data': item.get('_collection_data'),
                '_item_id': item.get('_item_id'),
            }
            result.append(source_item)
        return result

    def attach_source(self, source):
        """Render HTML from source data"""
        self.source = source
        self._render_html()

    def _render_html(self):
        """Generate HTML from source and load into WebView"""
        template = self._load_template()
        html = self._populate_template(template, self.source)
        self.webview.set_content(f"file://{self.TEMPLATES[self.style]}", html)
```

**Step 6: CardRenderer (renderers/card.py)**

```python
import toga
from toga.style.pack import Pack, COLUMN, ROW
from . import Renderer

class CardRenderer(Renderer):
    """Renderer using custom Toga layouts in card style"""

    def create_widget(self):
        # ScrollContainer with cards
        self.scroll_container = toga.ScrollContainer(style=Pack(flex=1))
        self.card_container = toga.Box(style=Pack(direction=COLUMN, padding=8))
        self.scroll_container.content = self.card_container
        return self.scroll_container

    def get_accessors(self, headings):
        base = [h.lower() for h in headings]
        custom = ['icon', '_collection_data', '_item_id']
        return base + custom

    def convert_to_source_format(self, data):
        accessor = self.headings[0].lower() if self.headings else 'text'
        result = []
        for item in data:
            source_item = {
                accessor: item.get('text', 'Untitled'),
                'icon': item.get('icon'),
                '_collection_data': item.get('_collection_data'),
                '_item_id': item.get('_item_id'),
            }
            result.append(source_item)
        return result

    def attach_source(self, source):
        """Create cards from source data"""
        self.source = source
        self._render_cards()

    def _render_cards(self):
        """Generate card widgets from source"""
        self.card_container.clear()

        for row in self.source:
            accessor = self.headings[0].lower()
            text = getattr(row, accessor, '')
            item_id = getattr(row, '_item_id', '')

            card = self._create_card(text, item_id, row)
            self.card_container.add(card)

    def _create_card(self, text, item_id, row):
        """Create a card widget based on style"""
        if self.style == 'compact':
            return self._create_compact_card(text, item_id, row)
        elif self.style == 'detailed':
            return self._create_detailed_card(text, item_id, row)
        else:
            return self._create_default_card(text, item_id, row)
```

**Step 7: Update library_view.py**

Simplify selection handling since all renderers now return Row objects:

```python
# OLD complex wrapper:
def _on_tree_select(self, selection):
    # 50+ lines of Node vs Row vs dict handling...

# NEW simple handler:
def _on_collection_select(self, selection):
    """Handle selection - now uniform across all renderers"""
    if not selection:
        self._clear_selection()
        return

    # All renderers return Row objects with consistent accessors
    collection_data = selection._collection_data
    item_id = selection._item_id

    # Load collection view
    self._load_collection(collection_data)
```

**Step 8: Test All Renderers**

```python
# Test native renderer (default)
list_widget = ListWidget(headings=['Collections'], data=data)

# Test HTML renderer
list_widget = ListWidget(
    headings=['Collections'],
    data=data,
    renderer='html',
    renderer_style='compact'  # or 'default', 'detailed'
)

# Test card renderer
list_widget = ListWidget(
    headings=['Collections'],
    data=data,
    renderer='card',
    renderer_style='detailed'  # or 'default', 'compact'
)
```

#### Migration Checklist

- [ ] Create module structure
- [ ] Move list_widget.py to base.py
- [ ] Add source management to base.py
- [ ] Create Renderer base class
- [ ] Implement NativeRenderer
- [ ] Implement HTMLRenderer with templates
- [ ] Implement CardRenderer with styles
- [ ] Update __init__.py exports
- [ ] Update library_view.py selection handling
- [ ] Update tests
- [ ] Test all renderer types
- [ ] Remove old conversion methods
- [ ] Update documentation

#### Benefits

1. **Uniform Selection**: All renderers → Row objects with consistent accessors
2. **Extensible**: Easy to add new renderers (Grid, Timeline, etc.)
3. **Styleable**: Multiple styles per renderer type
4. **Maintainable**: Separated concerns (rendering vs data management)
5. **Source-Based**: Widgets auto-update when source changes

---

### 📋 Source-Based Architecture Details

#### Problem

The current ListWidget implementation has complex, fragile selection handling because different widget types return different object types:

```python
# Current behavior:
Tree widget      → Returns Node objects (e.g., node.collections)
Table widget     → Returns Row objects  (e.g., row.text, row._item_id)
DetailedList     → Returns dict objects (e.g., {'_collection_data': ...})
```

This requires wrapper code (`_on_tree_select` in library_view.py) with many special cases to normalize selection across widget types.

#### Root Cause

ListWidget currently passes raw data directly to widgets, which convert it differently:
- Tree expects nested tuples: `[({'collections': 'Name'}, children), ...]`
- Table expects dicts with accessor keys: `[{'icon': ..., 'text': ...}, ...]`
- DetailedList expects dicts: `[{'icon': ..., 'title': ..., 'subtitle': ...}, ...]`

Each widget type creates different internal representations, leading to inconsistent selection objects.

#### Proposed Solution: Source-Based Architecture

**Data Flow:**

```
Application Data (dicts)
    ↓
ListWidget.set_data()
    ↓
ListSource or TreeSource (managed by ListWidget)
    ↓
Toga Widget (Table/Tree/DetailedList)
    ↓
on_select callback → Uniform Row objects
```

**Key Principles:**

1. **ListWidget owns the source** - Creates and manages ListSource or TreeSource
2. **Single source of truth** - Widget reads from source, not raw data
3. **Uniform selection** - All widgets return Row objects from the source
4. **Clean accessors** - Custom fields like `_collection_data`, `_item_id` become row attributes

**Benefits:**

1. **Simplified Selection Handling**:
```python
# Before (complex):
if isinstance(selected_item, Node):
    # Extract from node.collections
    collection_name = getattr(selected_item, accessor)
    # Lookup in map...
elif isinstance(selected_item, Row):
    # Try _collection_data attribute
    # Try _item_id lookup
    # Try text match
elif isinstance(selected_item, dict):
    # Use dict keys

# After (simple):
def _on_collection_selected(self, row):
    # Row objects have uniform accessors
    collection_data = row._collection_data
    item_id = row._item_id
```

2. **Easy to Add Renderers**: HTML, Card, or custom renderers just need to implement `convert_to_source_format()` for their specific format

3. **Source Updates**: When data changes, just update the source - widgets automatically reflect changes

4. **Type Safety**: Row objects have predictable attributes defined by accessors

#### Migration Path

1. **Phase 1**: Implement source-based architecture in ListWidget
   - Add `_source` property
   - Implement `set_data()` with source updates
   - Keep existing `_convert_*` methods for compatibility

2. **Phase 2**: Update library_view.py
   - Simplify `_on_tree_select()` to expect Row objects
   - Remove Node/Row/dict special cases
   - Test with all widget types

3. **Phase 3**: Clean up
   - Remove old conversion methods
   - Remove `force_widget_type` (testing only)
   - Document new patterns

#### References

- Toga ListSource: https://toga.beeware.org/en/stable/reference/api/resources/sources/list_source.html
- Toga TreeSource: https://toga.beeware.org/en/stable/reference/api/resources/sources/tree_source.html
- Toga Table: https://toga.beeware.org/en/stable/reference/api/widgets/table.html

#### Status

- ⏸️ Not yet implemented
- ✅ Tree widget works (with complex wrapper code)
- ❌ Table widget fails (Row object not handled correctly)
- ❓ DetailedList untested since refactor

**Next Step**: Implement source-based architecture to simplify all widget types uniformly.

---

## Detailed Progress by Step

### Step 1.1: Platform Widget Abstraction Layer

#### Component: ListWidget ✅ 60% Complete

**What it is**: Platform-adaptive list widget that uses Table/DetailedList/Tree based on platform

**Status**: Core renamed and working, needs Toga Sources implementation

**Completed**:
- [x] Renamed from AbstractTreeList to ListWidget
- [x] Updated all imports and references
- [x] FORCE_MOBILE_UI environment variable support
- [x] Platform detection (macOS, Windows, Linux, iOS, Android)
- [x] Docstrings updated for new architecture
- [x] All 11 unit tests passing
- [x] Documented renderer pattern for future

**In Progress**:
- [ ] Convert to module structure (`list_widget/`)
  - `__init__.py` - Public API
  - `base.py` - ListWidget class
  - `native_renderer.py` - Current implementation
  - `html_renderer.py` - Future
  - `card_renderer.py` - Future

**Pending**:
- [ ] Use `toga.sources.ListSource` for Table/DetailedList
- [ ] Use `toga.sources.TreeSource` for Tree widget
- [ ] Remove `_convert_to_tree_data()` (use TreeSource instead)
- [ ] Remove `_flatten_tree_data()` (use ListSource instead)
- [ ] Remove `_convert_to_detailed_list_data()` (use ListSource with accessors)
- [ ] Add capability query properties:
  - `supports_multiple_select`
  - `supports_activation`
  - `supports_actions`
  - `supports_hierarchy`
- [ ] Fix library_view collections display (no fake children)

**Files Modified**:
- `src/fichero/shared/widgets/list_widget.py` (renamed)
- `src/fichero/shared/widgets/__init__.py`
- `src/fichero/windows/main/views/library/library_view.py`
- `tests/shared/widgets/test_list_widget.py` (renamed)

---

#### Component: ResizableCanvas ✅ COMPLETE

**Status**: Complete with 16 passing tests

**Files**:
- `src/fichero/shared/widgets/resizable_canvas.py`
- `tests/shared/widgets/test_resizable_canvas.py`

---

#### Component: Toolbar System ✅ REVIEWED

**Status**: Existing system reviewed, no duplicate needed

**Files**:
- `src/fichero/shared/toolbars/` (existing)

---

### Step 1.2: Base View Interface ⏸️ PENDING

Not started. See main architecture doc for details.

---

### Step 1.3: Focus Border System ⏸️ PENDING

Not started. Generalize from previous output pane focus borders implementation.

---

## Key Decisions Made

1. **Name Change**: `AbstractTreeList` → `ListWidget`
   - Rationale: "ListWidget" is clearer and more accurate
   - Collections are lists, not trees
   - Prepares for renderer pattern

2. **Module Structure** (Planned):
   - Single file OK for now
   - Will convert to module when adding renderers
   - Keeps code organized and files manageable

3. **Desktop Widget Choice**: Table (not Tree) for flat lists
   - Collections don't have hierarchy
   - Table is correct widget for multi-column flat data
   - Tree only when `hierarchical=True`

4. **Renderer Pattern**: Documented but not implemented yet
   - Architecture prepared for HTML/card renderers
   - Won't implement until needed
   - Keeps current code simple

---

## Integration Notes

### Files That Import ListWidget:
- `src/fichero/windows/main/views/library/library_view.py`
  - Uses for collections display
  - Currently has fake "children" structure (needs fix)
  - Selection handling via `.get_selection()`

### Breaking Changes:
- None yet - backward compatible rename
- Future: Data format when switching to Toga Sources

---

## Testing Status

### Unit Tests: ✅ 27/27 Passing
- ListWidget: 11/11 passing
- ResizableCanvas: 16/16 passing

### Integration Tests: ⏸️ Not yet created
- Will create when implementing Toga Sources

### Manual Tests Needed:
- [ ] Desktop mode with collections
- [ ] Mobile mode with collections
- [ ] Selection behavior
- [ ] Platform detection

---

## Next Session Tasks

1. **Convert list_widget to module structure**
   - Create `src/fichero/shared/widgets/list_widget/` folder
   - Move current code to `base.py` and `native_renderer.py`
   - Create `__init__.py` with public API

2. **Implement Toga Sources**
   - Study ListSource and TreeSource APIs
   - Replace manual conversion with Sources
   - Update tests

3. **Fix collections display**
   - Remove `children: []` from collections data
   - Use flat ListSource
   - Test desktop and mobile modes

---

## Reference Documents

- **Main Plan**: `docs/architecture/NAVIGATION_REFACTOR_PLAN.md` - Complete 8-week refactor plan
- **List Widget Architecture**: `docs/architecture/LIST_WIDGET_ARCHITECTURE.md` - Platform-adaptive widget with renderer system
- **This Tracker**: `docs/architecture/navigation_refactor/PROGRESS_TRACKER.md` - Session-by-session progress

---

## Notes

- Keep this file updated after each session
- Mark completion percentages realistically
- Document decisions and rationale
- Link to relevant commits/PRs when available
