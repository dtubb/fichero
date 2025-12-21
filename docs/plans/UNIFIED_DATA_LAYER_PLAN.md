# Fichero Unified Data Layer Plan

## Executive Summary

Fichero is a **macOS-only** app built with **Django-inspired patterns** and **native AppKit**:

- **Pydantic models** with Django-style managers (`Document.objects.filter()`)
- **DuckDB + LanceDB** for storage and vector search
- **Native Cocoa views** via Rubicon (no Toga)
- **NSSplitView** for resizable panes with state persistence
- **NSWindowRestoration** for window state (size, position, selection)
- **Declarative inspectors** (Django Forms-inspired auto-rendering)

## Design Principles

1. **One source of truth** - Pydantic models, persisted to DuckDB
2. **Django patterns** - `Model.objects.filter()`, `model.save()`, `ModelInspector`
3. **Native AppKit** - NSSplitView, NSOutlineView, NSCollectionView
4. **Simple callbacks** - No KVC/KVO, just Python functions
5. **Declarative UI** - Inspector fields auto-render from model definitions
6. **AppKit window management** - Native state restoration, pane visibility

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      STORAGE                                 │
│  DuckDB (structured) + LanceDB (vectors) + Parquet (export) │
└─────────────────────────────────────────────────────────────┘
                              ↑
                         db.save() / db.query()
                              ↑
┌─────────────────────────────────────────────────────────────┐
│                      MODELS                                  │
│  Document.objects.filter(parent_id=x)   ← Django-style API  │
│  Workflow.objects.get(id=y)                                 │
│  model.save() / model.delete()                              │
└─────────────────────────────────────────────────────────────┘
                              ↑
                    Python callbacks (simple)
                              ↑
┌─────────────────────────────────────────────────────────────┐
│                      VIEWS                                   │
│  Sidebar (NSOutlineView) → on_select callback               │
│  Browser (NSCollectionView) → on_select callback            │
│  Editor (swappable NSView) → loaded from selection          │
│  Inspector (ModelInspector) → auto-renders from model       │
└─────────────────────────────────────────────────────────────┘
                              ↑
                    NSSplitView (resizable panes)
                              ↑
┌─────────────────────────────────────────────────────────────┐
│                    WINDOW                                    │
│  MainWindow - manages layout, state restoration, pane       │
│  visibility, menu/toolbar integration                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Four-Pane Layout (NSSplitView)

```
┌──────────┬─────────────────────┬──────────────────┬──────────┐
│ SIDEBAR  │      BROWSER        │      EDITOR      │INSPECTOR │
│          │                     │                  │          │
│ Library  │  Grid/List of       │  Preview image   │ Metadata │
│ - Docs   │  items from         │  (top half)      │ Tags     │
│ - Folders│  selected node      │                  │ Status   │
│          │                     │  Metadata form   │ Actions  │
│ Workflows│  + Search bar       │  (bottom half)   │ History  │
│ Searches │                     │                  │          │
│          │                     │  OR              │          │
│          │                     │  Workflow editor │          │
│          │                     │  Search results  │          │
└──────────┴─────────────────────┴──────────────────┴──────────┘
     ↑              ↑                    ↑              ↑
     └──────────────┴────────────────────┴──────────────┘
                    NSSplitView (horizontal)
```

### Pane Structure

```
NSSplitView (horizontal, 4 panes)
├── Sidebar (NSOutlineView in NSScrollView)
├── Browser (NSCollectionView in NSScrollView + search bar)
├── Editor (swappable content view)
│   └── For documents: NSSplitView (vertical)
│       ├── Preview (image/PDF viewer)
│       └── Metadata (form fields from Inspector)
└── Inspector (ModelInspector - contextual)
```

### Selection Flow

```
Sidebar.on_select(node)
    ↓
Browser.load(Document.objects.filter(parent_id=node.id))
    ↓
Browser.on_select(items)
    ↓
Editor.load(items[0])
Inspector.load(items[0])  ← auto-renders fields
```

---

## NSSplitView Pane Management

### Pane Visibility Controller

```python
class PaneController:
    """Manages pane visibility and NSSplitView state."""

    def __init__(self, split_view: NSSplitView):
        self.split_view = split_view
        self._pane_visible = {
            'sidebar': True,
            'browser': True,
            'editor': True,
            'inspector': True,
        }

    def toggle_pane(self, name: str):
        """Toggle pane visibility with animation."""
        visible = not self._pane_visible[name]
        self._pane_visible[name] = visible
        index = ['sidebar', 'browser', 'editor', 'inspector'].index(name)

        if visible:
            self.split_view.setPosition_ofDividerAtIndex_(
                self._saved_widths[name], index
            )
        else:
            self._saved_widths[name] = self._get_pane_width(index)
            self.split_view.setPosition_ofDividerAtIndex_(0, index)

    def set_pane_width(self, name: str, width: float):
        """Set pane width."""
        index = ['sidebar', 'browser', 'editor', 'inspector'].index(name)
        self.split_view.setPosition_ofDividerAtIndex_(width, index)
```

### Menu Integration

```python
# View menu items
Item("Toggle Sidebar", "toggle_sidebar", "[", OPT | CMD),
Item("Toggle Browser", "toggle_browser", "]", OPT | CMD),
Item("Toggle Inspector", "toggle_inspector", "i", OPT | CMD),
```

---

## Window State Restoration (NSWindowRestoration)

### What Gets Saved

- Window frame (position, size)
- NSSplitView divider positions
- Pane visibility states
- Sidebar selection
- Browser selection
- Scroll positions

### Implementation

```python
class MainWindow(NSWindow):
    """Main window with state restoration."""

    # NSWindowRestoration protocol
    @objc_method
    def encodeRestorableStateWithCoder_(self, coder):
        """Save window state."""
        super().encodeRestorableStateWithCoder_(coder)
        coder.encodeObject_forKey_(self._get_state_dict(), "ficheroState")

    @objc_method
    def restoreStateWithCoder_(self, coder):
        """Restore window state."""
        super().restoreStateWithCoder_(coder)
        state = coder.decodeObjectForKey_("ficheroState")
        if state:
            self._apply_state_dict(state)

    def _get_state_dict(self) -> dict:
        return {
            'sidebar_width': self.panes.get_width('sidebar'),
            'browser_width': self.panes.get_width('browser'),
            'inspector_width': self.panes.get_width('inspector'),
            'sidebar_visible': self.panes.is_visible('sidebar'),
            'inspector_visible': self.panes.is_visible('inspector'),
            'sidebar_selection': self.sidebar.selected_id,
            'browser_selection': self.browser.selected_ids,
        }
```

---

## Database Access (Simple and Explicit)

No manager abstraction - just use `db` directly:

```python
from fichero.models import Document, DocType
from fichero.db import db

# Query
collections = db.query(Document, doc_type=DocType.collection)
doc = db.get(Document, "abc123")
all_docs = db.all(Document)
count = db.count(Document, status=Status.pending)

# Create and save
doc = Document(name="letter.jpg", path="/path/letter.jpg")
db.save(doc)

# Update
doc.name = "renamed.jpg"
db.save(doc)

# Delete
db.delete(doc)
```

Simple, explicit, no hidden magic.

---

## ModelInspector (Django Forms-Inspired)

Auto-renders UI from Pydantic model definitions:

```python
class DocumentInspector(ModelInspector):
    """Auto-renders fields from Document model."""

    model = Document
    fields = ['name', 'tags', 'status', 'created_at', 'file_type']
    readonly = ['created_at', 'file_type']

    widgets = {
        'tags': TagTokenField,
        'status': StatusDropdown,
    }

# Usage
inspector.load(selected_document)  # Auto-populates all fields
inspector.save()  # Writes back to model, calls model.save()
```

---

## File Structure

```
src/fichero/
├── models.py              # Pydantic models
├── db.py                  # DuckDB wrapper
├── loaders/               # Media import (shared CLI/GUI)
├── tools/                 # Processing tools (shared CLI/GUI)
├── cli/                   # Command-line interface
│
└── app/                   # macOS GUI (AppKit via Rubicon)
    ├── __init__.py
    ├── base.py            # View protocol, EditorContainer
    ├── sidebar.py         # NSOutlineView
    ├── browser.py         # NSCollectionView grid
    ├── inspector.py       # ModelInspector base class
    ├── window.py          # MainWindow (4-pane NSSplitView)
    │
    └── editors/           # Swappable editor views
        ├── __init__.py
        ├── document.py    # Preview + metadata (combined)
        ├── workflow.py    # Workflow editor
        └── search.py      # Search results
```

---

## What Gets Deleted

| File | Reason |
|------|--------|
| `views/library/sidebar_data_model.py` | Replaced by direct model queries |
| `views/collection/collection_view.py` | Replaced by `views/browser.py` |
| `views/preview/preview_view.py` | Merged into `views/editors/document.py` |
| `views/adjust/adjust_view.py` | Merged into `views/editors/document.py` |
| `windows/info_window.py` | Not needed - Inspector shows everything |
| All Toga widget wrappers | Native Cocoa instead |

## What Gets Kept/Cleaned

| File | Action |
|------|--------|
| `source_list.py` | Move to `views/sidebar.py`, clean up |
| `menu.py` | Keep (already native) |
| `toolbar.py` | Keep (already native) |
| `models.py` | Add managers |
| `db.py` | Keep as-is |
| `loaders/` | Keep as-is |

---

## The 7 Core Models

| Model | Purpose | Replaces |
|-------|---------|----------|
| **Document** | Files, folders, pages, chunks in hierarchy | Collection, CollectionItem |
| **Artifact** | AI outputs (transcriptions, entities, etc.) | ProcessingOutput, ExtractedMetadata |
| **Workflow** | Processing pipeline definitions | workflow configs |
| **Run** | Workflow execution tracking | ProcessingResult |
| **Trace** | LangChain/LangGraph debug data | (new) |
| **Note** | User annotations with positions | (new) |
| **Event** | Audit trail for undo/history | TimelineEvent |

---

## Document Hierarchy

The `Document` model handles everything from collections to text chunks:

```
Collection: "Family Archive"           ← doc_type: collection
  └── Folder: "Box 1"                  ← doc_type: folder
        └── Group: "Letter from John"  ← doc_type: group (logical document)
              ├── File: page_001.jpg   ← doc_type: file
              ├── File: page_002.jpg   ← doc_type: file
              └── File: page_003.jpg   ← doc_type: file
                    └── Chunk: signature ← doc_type: chunk (region)
```

**Key fields:**
- `parent_id` - Creates hierarchy
- `doc_type` - collection, folder, group, file, page, chunk
- `file_type` - image, pdf, audio, video, text, word, epub
- `metadata` - Flexible dict for source_path, thumbnails, IIIF data, etc.
- `page_content` - Text content (LangChain compatible)

---

## Media Loader Architecture

### Implementation Status: DONE

The unified loader system is implemented in `src/fichero/loaders/`:

| Loader | Library | Formats | Status |
|--------|---------|---------|--------|
| **ImageLoader** | PIL + system tools | JPG, PNG, TIFF, HEIC, JXL, RAW | ✅ Done |
| **PDFLoader** | PyMuPDF | PDF → images + text | ✅ Done |
| **DocumentLoader** | Kreuzberg | DOCX, XLSX, PPTX, EPUB, TXT, MD | ✅ Done |
| **IIIFLoader** | aiohttp | IIIF v2.x and v3.0 manifests | ✅ Done |
| AudioLoader | Whisper | MP3, WAV, M4A | Future |
| VideoLoader | ffmpeg | MP4, MOV, AVI | Future |

### Format Routing

```
Source                      → Loader         → Output
────────────────────────────────────────────────────────────
image.jpg/.png/.tiff        → ImageLoader    → PIL Images for VLM
image.heic/.heif            → ImageLoader    → heif-convert → PIL
image.cr2/.nef/.arw         → ImageLoader    → rawpy → PIL
document.pdf                → PDFLoader      → PyMuPDF → Images + Text
document.docx/.xlsx/.pptx   → DocumentLoader → Kreuzberg → Text
book.epub                   → DocumentLoader → Kreuzberg → Text
manifest.json (IIIF URL)    → IIIFLoader     → Download → PIL Images
file.txt/.md                → DocumentLoader → Direct read → Text
```

### MediaContent (Normalized Output)

```python
@dataclass
class MediaContent:
    source: str                        # Original path/URL
    text: str | None = None            # Extracted text
    images: list[Image.Image] = []     # PIL Images for VLM
    audio: bytes | None = None         # Future: audio bytes
    metadata: dict = {}                # Format-specific metadata
    mime_type: str | None = None       # Detected MIME type
    needs_vlm: bool = True             # Does this need VLM?
```

### Usage

```python
from fichero.loaders import load_media

# Load any supported format
content = await load_media("/path/to/document.pdf")

# Access normalized output
print(content.page_count)    # Number of pages/images
print(content.text)          # Extracted text (if any)
print(content.needs_vlm)     # Whether VLM transcription needed

# Process images for VLM
for img in content.images:
    # Send to Qwen/GPT-4o for transcription
    pass
```

### Library Responsibilities

| Library | What It Does | Why |
|---------|-------------|-----|
| **PyMuPDF** | PDF → images + text | Fast, no poppler dependency, renders pages to images |
| **Kreuzberg** | Office docs, EPUB, text extraction | Handles 56+ formats, table extraction, layout preservation |
| **PIL/Pillow** | Standard images | JPG, PNG, TIFF, BMP, GIF, WebP |
| **heif-convert** | HEIC/HEIF images | System tool for iPhone photos |
| **rawpy** | RAW camera images | CR2, NEF, ARW, DNG |
| **djxl** | JPEG XL images | System tool for JXL format |
| **aiohttp** | IIIF downloads | Async HTTP for manifest + image downloads |

### Decision: PyMuPDF vs Kreuzberg for PDFs

We use **PyMuPDF** as the primary PDF loader because:
1. It renders pages to images (needed for VLM transcription of scanned docs)
2. No external dependencies (unlike pdf2image which needs poppler)
3. Also extracts text from digital PDFs

Kreuzberg is used for:
1. Office documents (DOCX, XLSX, PPTX)
2. E-books (EPUB)
3. Plain text files with encoding detection

For PDFs with complex layouts where you want better text extraction,
use `PDFTextLoader` which uses Kreuzberg instead.

---

## Data Flow: Import to Artifact

```
1. USER IMPORTS
   ┌─────────────────────────────────────────────────────────┐
   │  File drop / IIIF URL / Folder scan                     │
   └─────────────────────────────────────────────────────────┘
                              ↓
2. UNIFIED LOADER
   ┌─────────────────────────────────────────────────────────┐
   │  Route to appropriate loader based on source type       │
   │  Returns: MediaContent (text and/or images)             │
   └─────────────────────────────────────────────────────────┘
                              ↓
3. CREATE DOCUMENTS
   ┌─────────────────────────────────────────────────────────┐
   │  Document(doc_type=file, file_type=image, ...)         │
   │  Store original path, generate thumbnails               │
   │  db.save(document)                                      │
   └─────────────────────────────────────────────────────────┘
                              ↓
4. RUN WORKFLOW (if requested)
   ┌─────────────────────────────────────────────────────────┐
   │  Workflow: "Transcribe" → Run execution                 │
   │  LangGraph pipeline processes MediaContent              │
   └─────────────────────────────────────────────────────────┘
                              ↓
5. CREATE ARTIFACTS
   ┌─────────────────────────────────────────────────────────┐
   │  Artifact(document_id=..., artifact_type="transcription")│
   │  Track: provider, model, confidence, version            │
   │  db.save(artifact)                                      │
   └─────────────────────────────────────────────────────────┘
                              ↓
6. USER REVIEW (optional)
   ┌─────────────────────────────────────────────────────────┐
   │  User corrects transcription                            │
   │  New Artifact: provider="human", version=2              │
   │  Chains to original via source_artifact_id              │
   └─────────────────────────────────────────────────────────┘
```

---

## File Storage Strategy

### Path Types

| Storage Type | Description | Document.metadata |
|--------------|-------------|-------------------|
| **External** | File stays in user's folder | `source_path`, `bookmark` (macOS alias) |
| **Local** | Copied to library | `local_path` |
| **Derived** | Generated (thumbnails, etc.) | `thumbnail_path`, `display_path` |
| **Remote** | URL or IIIF | `source_url`, `source_type` |

### Library Structure

```
~/Library/Application Support/Fichero/
├── library.duckdb              # Main database (DuckDB)
├── vectors/                    # LanceDB embeddings
│
├── derived/                    # All derived/generated files
│   └── {document_id}/
│       ├── full.jpg            # Full resolution (if copied)
│       ├── display.jpg         # Display size
│       ├── thumb.jpg           # Thumbnail
│       └── pages/              # Extracted pages (from PDF)
│
├── traces/                     # LangGraph debug logs
└── exports/                    # Export outputs
```

### macOS File References

For external files, store macOS bookmarks (survive moves/renames):

```python
Document(
    name="letter.jpg",
    doc_type=DocType.file,
    metadata={
        "source_type": "external",
        "source_path": "/Users/bob/Documents/letter.jpg",
        "bookmark": "<base64 macOS bookmark data>",
        "thumbnail_path": "derived/abc123/thumb.jpg"
    }
)
```

---

## KVC Bridge: The Thin Wrapper

The bridge exposes Pydantic models to Cocoa Bindings without duplicating data.

### KVCDocument - Wrapper for Document

```python
from rubicon.objc import ObjCClass, objc_method, NSObject
from fichero.db import db
from fichero.models import Document

NSObject = ObjCClass("NSObject")

class KVCDocument(NSObject):
    """
    Thin KVC wrapper around a Pydantic Document.

    NOT a copy - holds a reference to the actual Document.
    Changes go straight to the model and database.
    """

    _doc: Document = None  # The wrapped Pydantic model

    @classmethod
    def wrap(cls, doc: Document) -> "KVCDocument":
        """Wrap a Document for use with Cocoa Bindings."""
        obj = cls.alloc().init()
        obj._doc = doc
        return obj

    # --- KVC Protocol ---

    @objc_method
    def valueForKey_(self, key: str):
        """KVC getter - reads from Pydantic model."""
        key = str(key)
        if key == "children":
            return self.children()
        if key == "isLeaf":
            return self.isLeaf()
        return getattr(self._doc, key, None)

    @objc_method
    def setValue_forKey_(self, value, key: str):
        """KVC setter - writes to model AND persists."""
        key = str(key)
        self.willChangeValueForKey_(key)
        setattr(self._doc, key, value)
        db.save(self._doc)  # Persist immediately
        self.didChangeValueForKey_(key)

    # --- Tree Structure (for NSTreeController) ---

    @objc_method
    def children(self):
        """Return child documents wrapped for KVC."""
        from fichero.models import DocType
        kids = db.query(Document, parent_id=self._doc.id)
        return [KVCDocument.wrap(k) for k in kids]

    @objc_method
    def isLeaf(self):
        """Is this a leaf node (no children)?"""
        from fichero.models import DocType
        return self._doc.doc_type in (DocType.file, DocType.chunk)

    # --- Exposed Properties (for bindings) ---

    @objc_method
    def name(self):
        return self._doc.name

    @objc_method
    def setName_(self, value):
        self.setValue_forKey_(str(value), "name")

    @objc_method
    def thumbnail(self):
        """Return NSImage for thumbnail."""
        path = self._doc.metadata.get("thumbnail_path")
        if path:
            NSImage = ObjCClass("NSImage")
            return NSImage.alloc().initWithContentsOfFile_(path)
        return None
```

### Data Flow Example

```
User renames item in sidebar
    ↓
NSOutlineView editing ends
    ↓
Binding calls setValue_forKey_("name", "New Name")
    ↓
KVCDocument.setValue_forKey_:
    1. willChangeValueForKey_("name")  ← KVO notification
    2. self._doc.name = "New Name"     ← Update Pydantic model
    3. db.save(self._doc)              ← Persist to DuckDB
    4. didChangeValueForKey_("name")   ← KVO notification
    ↓
All bound views update automatically
```

### Why This Works

1. **Single source of truth**: `Document` (Pydantic) holds the data
2. **No sync needed**: Changes go directly to the model
3. **Automatic persistence**: `db.save()` on every change
4. **KVO for free**: `willChange/didChange` triggers view updates
5. **Lazy loading**: `children()` queries on demand

---

## Sidebar: NSTreeController + NSOutlineView

### Structure

```
NSTreeController
    ↓ binds to
[KVCDocument] array (root collections)
    ↓ children() returns
[KVCDocument] array (folders)
    ↓ children() returns
[KVCDocument] array (items)
    ↓ binds to
NSOutlineView
```

### Setup

```python
from rubicon.objc import ObjCClass

NSTreeController = ObjCClass("NSTreeController")
NSOutlineView = ObjCClass("NSOutlineView")

def setup_sidebar(outline_view, root_documents: list[Document]):
    """Wire up sidebar with Cocoa Bindings."""

    # Wrap root documents
    wrapped = [KVCDocument.wrap(d) for d in root_documents]

    # Create tree controller
    controller = NSTreeController.alloc().init()
    controller.setChildrenKeyPath_("children")
    controller.setLeafKeyPath_("isLeaf")
    controller.setContent_(wrapped)

    # Bind outline view to controller
    outline_view.bind_toObject_withKeyPath_options_(
        "content",
        controller,
        "arrangedObjects",
        None
    )
    outline_view.bind_toObject_withKeyPath_options_(
        "selectionIndexPaths",
        controller,
        "selectionIndexPaths",
        None
    )

    return controller
```

### What We Get For Free

- **Expand/collapse** - NSOutlineView handles it
- **Selection** - Single, multiple, keyboard navigation
- **Drag-drop reordering** - NSTreeController supports it
- **Add/remove** - Controller methods with undo support
- **Sorting** - Sort descriptors on controller

---

## Collection Grid: NSArrayController + NSCollectionView

### Structure

```
NSArrayController
    ↓ binds to
[KVCDocument] array (items in selected folder)
    ↓ binds to
NSCollectionView
    ↓ displays
NSCollectionViewItem (thumbnail + label)
```

### Setup

```python
NSArrayController = ObjCClass("NSArrayController")
NSCollectionView = ObjCClass("NSCollectionView")

def setup_collection_view(collection_view, items: list[Document]):
    """Wire up collection grid with Cocoa Bindings."""

    # Wrap items
    wrapped = [KVCDocument.wrap(d) for d in items]

    # Create array controller
    controller = NSArrayController.alloc().init()
    controller.setContent_(wrapped)

    # Bind collection view
    collection_view.bind_toObject_withKeyPath_options_(
        "content",
        controller,
        "arrangedObjects",
        None
    )
    collection_view.bind_toObject_withKeyPath_options_(
        "selectionIndexes",
        controller,
        "selectionIndexes",
        None
    )

    return controller
```

### What We Get For Free

- **Grid layout** - NSCollectionViewFlowLayout
- **Rubber-band selection** - Native drag selection
- **Keyboard navigation** - Arrow keys, page up/down
- **Smooth scrolling** - With thousands of items
- **Image caching** - NSCollectionViewItem handles it
- **Drag-drop** - NSPasteboard integration

---

## Migration Strategy

### Phase 1: Parallel Systems (Current → Transitional)

- Keep SQLite LibraryStorage working
- Add DuckDB db.py alongside
- New imports go to DuckDB
- Existing data stays in SQLite
- UI works with both

### Phase 2: Gradual Migration

- Background job migrates SQLite → DuckDB
- Service layer queries both, prefers DuckDB
- No UI changes needed

### Phase 3: Full Cutover

- All data in DuckDB
- Remove SQLite code
- Simplify service layer

---

## Questions for Andy (Briefcase/Packaging)

1. **Kreuzberg packaging**: Does Kreuzberg work in Briefcase-packaged apps? It has native dependencies (poppler, tesseract optional). If problematic, we can use PyMuPDF as fallback for PDFs.

2. **DuckDB packaging**: DuckDB has native extensions. Any known issues with Briefcase on macOS ARM64?

3. **LanceDB packaging**: LanceDB is Rust-based. Does it package correctly?

4. **External file access**: For "external" collections that reference files outside the app bundle, are there macOS sandbox considerations for Briefcase apps?

5. **IIIF network access**: For fetching IIIF manifests and images, any special entitlements needed?

---

## Implementation Order

### Phase 1: Data Layer (DONE)
1. ✅ models.py with 7 Pydantic models
2. ✅ db.py DuckDB wrapper with full CRUD
3. ✅ 35 tests passing

### Phase 2: Loaders (DONE)
4. ✅ MediaLoader base class
5. ✅ ImageLoader (PIL, HEIC, JXL, RAW)
6. ✅ PDFLoader (PyMuPDF)
7. ✅ DocumentLoader (Kreuzberg)
8. ✅ IIIFLoader

### Phase 3: Native Menu/Toolbar (IN PROGRESS)
9. ✅ AppMenu - native NSMenu
10. 🔄 AppToolbar - native NSToolbar
11. ⏳ Wire to MainWindow

### Phase 4: Data Layer (DONE)
12. ✅ Plain Pydantic models (no manager abstraction)
13. ✅ Use `db.query()`, `db.save()`, `db.delete()` directly

### Phase 5: Native App (No Toga)
14. ✅ `app/base.py` - View protocol, EditorContainer
15. ✅ `app/sidebar.py` - NSOutlineView (from source_list.py)
16. 🔄 `app/browser.py` - NSCollectionView grid
17. ⏳ `app/inspector.py` - ModelInspector base class
18. ⏳ `app/window.py` - 4-pane NSSplitView layout

### Phase 6: Editors
19. ⏳ `app/editors/document.py` - Preview + metadata combined
20. ⏳ `app/editors/workflow.py` - Workflow editor
21. ⏳ `app/editors/search.py` - Search results

### Phase 9: Cleanup
26. ⏳ Delete `views/library/sidebar_data_model.py`
27. ⏳ Delete `views/collection/collection_view.py`
28. ⏳ Delete `views/preview/preview_view.py`
29. ⏳ Delete `views/adjust/adjust_view.py`
30. ⏳ Delete `windows/info_window.py`
31. ⏳ Delete Toga widget wrappers
32. ⏳ SQLite → DuckDB migration script

### Future
- AudioLoader (Whisper)
- VideoLoader (ffmpeg)
- NSUndoManager integration

---

## Summary

This plan:
- **Django-inspired**: `Model.objects.filter()`, `model.save()`, `ModelInspector`
- **Native AppKit**: NSSplitView, NSOutlineView, NSCollectionView
- **Simple callbacks**: No KVC/KVO complexity
- **Declarative inspectors**: Auto-render UI from Pydantic model fields
- **DuckDB + LanceDB**: ML-friendly storage with vector search
- **Window state restoration**: Native NSWindowRestoration protocol

The key insight: **Django patterns work beautifully with Pydantic + native Cocoa**. Models have managers, views have callbacks, inspectors auto-render from model definitions.
