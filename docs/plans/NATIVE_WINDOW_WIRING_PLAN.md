# Native Window Wiring Plan

## Current State

### Old System (Toga-based)
- `gui.py` - FicheroApp creates MainWindow
- `app/main_window/__init__.py` - MainWindow using Toga SplitContainers
- Uses `LibraryManager` (old library system)
- Event-driven via NavigationController + NavigationEventBus
- Feature flag `USE_NATIVE_MENU_TOOLBAR = True` for native menu/toolbar

### New System (Native AppKit)
- `app/main_window/sidebar.py` - SourceList (NSOutlineView) ✅
- `app/main_window/browser.py` - Browser (NSCollectionView) ✅
- `app/main_window/editor.py` - EditorContainer (ImageViewer, TableViewer, TextViewer) ✅
- `app/main_window/inspector.py` - Inspector (metadata + info) ✅
- `app/main_window/window.py` - MainWindowController (4-pane NSSplitView) ✅
- `app/main_window/menu.py` - AppMenu (NSMenu) ✅
- `app/main_window/toolbar.py` - AppToolbar (NSToolbar) ✅

### Data Layer
- `db.py` - Database (DuckDB) ✅
- `models.py` - Pydantic models (Document, Artifact, etc.) ✅

## Architecture Clarification

```
┌──────────┬─────────────────────┬──────────────────┬──────────┐
│ SIDEBAR  │      BROWSER        │      EDITOR      │INSPECTOR │
│          │                     │                  │          │
│ Sections:│ Grid of thumbnails  │ Swappable:       │ Metadata │
│ - Library│ from current        │ - ImageViewer    │ + Info   │
│ - Workflows│ selection         │ - TableViewer    │ + AI out │
│ - Search │                     │ - TextViewer     │          │
│ - Tags   │                     │ - WorkflowEditor │          │
│          │                     │   (future)       │          │
└──────────┴─────────────────────┴──────────────────┴──────────┘
```

**Key insight**: Editor is JUST for viewing/editing content. Could be:
- Image viewer (with zoom/pan)
- Table view (for lists)
- Text viewer (for transcriptions)
- Workflow editor (future - for editing workflow steps)
- Preview + something else stacked (future)

## Wiring Strategy

### Phase 1: Feature Flag + Parallel Systems

Add feature flag in `app/main_window/__init__.py`:
```python
USE_NATIVE_WINDOW = False  # Set True to use new NSSplitView system
```

When `USE_NATIVE_WINDOW = True`:
- Create `MainWindowController` instead of Toga MainWindow
- Use new native components
- Wire to new `db.py` data layer

When `USE_NATIVE_WINDOW = False`:
- Existing Toga MainWindow (current behavior)
- Uses LibraryManager

### Phase 2: Data Source Wiring

**Sidebar → Database**
```python
# In MainWindowController.__init__
from fichero.models import Document, DocType
from fichero.db import db

# Load collections
collections = db.query(Document, doc_type=DocType.collection)
self.load_sidebar(collections)
```

**Sidebar Selection → Browser**
```python
def _on_sidebar_select(self, item):
    doc = item.data  # Document stored in SourceListItem.data
    if doc.doc_type == DocType.collection:
        # Load children into browser
        items = db.query(Document, parent_id=doc.id)
        self.browser.items = items
```

**Browser Selection → Editor + Inspector**
```python
def _on_browser_select(self, docs: list[Document]):
    if docs:
        doc = docs[0]
        self.editor.load(doc)      # Auto-selects ImageViewer/TableViewer
        self.inspector.load(doc)   # Shows metadata
```

### Phase 3: Menu/Toolbar Integration

The menu/toolbar handlers need to work with new components:

```python
# In menu.py or MainWindowController

def _on_new_collection(self):
    # Create new collection
    collection = Document(name="New Collection", doc_type=DocType.collection)
    db.save(collection)
    # Refresh sidebar
    self.reload_sidebar()

def _on_import_folder(self):
    # Show folder picker, create collection, import files
    pass
```

### Phase 4: Migration Path

1. **Start with feature flag OFF** - Old system works as before
2. **Turn ON for testing** - New native window appears
3. **Wire incrementally** - One pane at a time
4. **Test thoroughly** - Both systems should be functional
5. **Remove old code** - When new system is stable

## Implementation Order

1. **Add feature flag** to `app/main_window/__init__.py`
2. **Create MainWindowController factory** that returns old or new based on flag
3. **Wire sidebar** to db.query for collections
4. **Wire browser** to show documents when collection selected
5. **Wire editor** to show content when document selected
6. **Wire inspector** to show metadata
7. **Update menu handlers** to work with new system
8. **Test with real data**

## Integration Points

### From Old System (need to support both)
- `app.library_manager` - Old LibraryManager
- `app.director` - Processing pipeline
- `app.state_manager` - Session persistence
- `app.selection_manager` - Selection tracking

### For New System
- `db` - New DuckDB database
- `Document`, `Artifact` - Pydantic models
- Direct queries, no intermediate layer

### Bridging (temporary)
During transition, may need to sync between old LibraryManager and new db.py.
Could be done via:
- Import/export scripts
- Dual-write (write to both)
- One-way sync on startup

## File Changes Required

1. `app/main_window/__init__.py` - Add USE_NATIVE_WINDOW flag, factory function
2. `app/main_window/window.py` - Wire callbacks to db queries
3. `gui.py` - Use factory function instead of direct MainWindow import

## Testing Plan

1. Unit tests for each component (already done)
2. Integration test: sidebar → browser flow
3. Integration test: browser → editor flow
4. Manual test: full app with feature flag ON
5. Performance test: large collections
