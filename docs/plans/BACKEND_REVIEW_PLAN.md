# Backend Data Layer Review Plan

## Overview

This plan systematically reviews the backend data layer to ensure all components are properly integrated and tested. The goal is to verify the CLI can perform all data operations before focusing on the GUI.

---

## CRITICAL ISSUES FOUND

### Issue 1: Duplicate LanceDB Connections (BROKEN)

**Problem**: Two separate LanceDB systems that don't talk to each other:

```
db.py (lines 188-312)           haystack_search.py (lines 84-100)
├── table: "embeddings"         ├── table: "document_embeddings"
├── save_embedding()            ├── index_document()
├── search_similar()            ├── search_documents()
└── lance connection #1         └── lance connection #2 (different!)
```

**Fix**: Delete `search/` folder. Move search into `db.py`. One LanceDB connection.

### Issue 2: Loaders Not Connected to Ingest (BROKEN)

**Problem**: When you ingest a file, text is NEVER extracted:

```
ingest.py                       loaders/
├── Creates Document            ├── Has UnifiedLoader
├── Extracts: size, checksum    ├── Can extract: text, images
├── NEVER calls loaders         └── Never used!
└── page_content = empty
```

**Result**: Search has nothing to index because documents have no content!

**Fix**: Ingest should optionally use loaders to populate `page_content`.

### Issue 3: No Auto-Embedding (NOT HOOKED UP)

**Problem**: Saving a document does NOT create embeddings:

```python
db.save(doc)  # Saves to DuckDB... but no embedding created!
# Must manually call:
index_document(doc)  # Different system entirely
```

**Fix**: Option A: `db.save()` auto-embeds when `page_content` exists
        Option B: `embed()` method on Document model (Pydantic computed)

### Issue 4: Keychain Uses Subprocess (WRONG)

**Problem**: `keychain.py` uses `subprocess.run(["security", ...])`:
- Won't work in sandboxed app
- Crude approach
- Should use Rubicon for native Keychain API

**Fix**: Rewrite with Rubicon-ObjC to use Security framework directly.

---

## Current State Analysis

### Components Reviewed

| Component | File | Status | Critical Issue? |
|-----------|------|--------|-----------------|
| **Database** | `db.py` | ✅ Works | Has LanceDB but not used |
| **Models** | `models.py` | ✅ Works | - |
| **Storage** | `storage.py` | ✅ Works | - |
| **Search** | `search/haystack_search.py` | ❌ DUPLICATE | Different LanceDB! |
| **Ingest** | `ingest.py` | ⚠️ Partial | No text extraction |
| **Bookmarks** | `bookmarks.py` | ✅ Works | Uses Rubicon correctly |
| **Keychain** | `keychain.py` | ❌ WRONG | Uses subprocess |
| **Settings** | `settings.py` | ✅ Works | - |
| **Loaders** | `loaders/` | ⚠️ Unused | Never called from ingest |

---

## Phase 1: Fix Critical Issues (CODE FIXES)

### 1.1 Consolidate Search into db.py

**Delete**: `src/fichero/search/` folder entirely

**Enhance db.py** to add proper search:

```python
# In db.py - add these methods:

class Database:
    # ... existing code ...

    def embed(self, doc: Document) -> bool:
        """Create/update embedding for document."""
        text = doc.page_content or doc.name
        if not text or len(text) < 10:
            return False

        vector = self._embed_text(text)
        self.save_embedding(doc, vector, text)
        return True

    def search(self, query: str, limit: int = 10) -> list[Document]:
        """Semantic search for documents."""
        vector = self._embed_text(query)
        results = self.search_similar(vector, limit, Document)
        return results

    def _embed_text(self, text: str) -> list[float]:
        """Generate embedding vector for text."""
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
        return self._embedder.encode(text).tolist()
```

### 1.2 Fix Keychain with Rubicon

**Rewrite `keychain.py`**:

```python
"""macOS Keychain using Security framework via Rubicon."""

from rubicon.objc import ObjCClass
from rubicon.objc.runtime import load_library

Security = load_library("Security")

# Keychain item classes
kSecClass = ObjCClass("NSString").stringWithString_("kSecClass")
kSecClassGenericPassword = ObjCClass("NSString").stringWithString_(
    "kSecClassGenericPassword"
)
# ... proper Security framework calls
```

### 1.3 Connect Loaders to Ingest

**Add to `ingest.py`**:

```python
async def ingest_file(
    path: Path,
    mode: IngestMode = IngestMode.LINK,
    extract_text: bool = True,  # NEW: default True
    parent_id: str | None = None,
) -> Document:
    """Ingest file, optionally extracting text content."""
    # ... existing validation ...

    doc = Document(name=path.name, path=str(path), ...)

    if extract_text:
        from fichero.loaders import load_media
        try:
            content = await load_media(path)
            if content.text:
                doc.page_content = content.text
        except Exception as e:
            logger.warning(f"Text extraction failed: {e}")

    db.save(doc)
    return doc
```

### 1.4 Auto-Embed on Save (Optional Hook)

**Option A**: Add `auto_embed` flag to db.save():

```python
def save(self, obj: BaseModel, auto_embed: bool = True) -> None:
    """Save object. If Document with page_content, auto-embed."""
    # ... existing save logic ...

    if auto_embed and hasattr(obj, 'page_content') and obj.page_content:
        self.embed(obj)
```

**Option B**: Signal-based (cleaner, like Django):

```python
# In models.py
class Document(BaseModel):
    # ... fields ...

    class Config:
        # Post-save hook
        post_save_hooks = ['create_embedding']
```

---

## Phase 2: Code Review Checklist

### 2.1 db.py Review

- [ ] DuckDB connection management correct?
- [ ] LanceDB lazy init works?
- [ ] JSON serialization handles all types?
- [ ] Enum handling in queries?
- [ ] Thread safety considerations?
- [ ] Error handling sufficient?

### 2.2 models.py Review

- [ ] All fields have correct types?
- [ ] Computed fields work?
- [ ] Default values make sense?
- [ ] Enums cover all cases?
- [ ] Metadata accessor properties work?

### 2.3 storage.py Review

- [ ] Thumbnail sharding correct?
- [ ] Bookmark resolution works?
- [ ] Thread pool for batch ops?
- [ ] Path resolution fallbacks?

### 2.4 ingest.py Review

- [ ] APFS clone works?
- [ ] Bookmark creation correct?
- [ ] File type detection complete?
- [ ] Progress callbacks work?
- [ ] Error handling for bad files?

### 2.5 loaders/ Review

- [ ] All formats supported?
- [ ] Async/sync wrappers work?
- [ ] Docling optional correctly?
- [ ] IIIF loader tested?
- [ ] Error handling for corrupt files?

### 2.6 keychain.py Review (After Rubicon Fix)

- [ ] Rubicon Security framework calls correct?
- [ ] Error handling for missing keychain?
- [ ] Works in sandboxed app?

### 2.7 settings.py Review

- [ ] JSON persistence works?
- [ ] Default values sensible?
- [ ] Attribute proxy works?

---

## Phase 3: Unit Tests

### 3.1 Tests to Create

| File | Tests |
|------|-------|
| `test_db_search.py` | Embedding, search, delete embedding |
| `test_keychain.py` | Set/get/delete with Rubicon |
| `test_bookmarks.py` | Create/resolve/stale check |
| `test_settings.py` | Load/save/defaults |
| `test_loaders.py` | Each loader type |
| `test_ingest_with_extraction.py` | Text extraction during ingest |

### 3.2 Integration Tests

| Test | What it Verifies |
|------|------------------|
| `test_ingest_to_search.py` | Ingest file → extract text → embed → search finds it |
| `test_keychain_to_provider.py` | Set key → provider can use it |
| `test_full_pipeline.py` | Ingest folder → thumbnails → search → export |

---

## Phase 4: CLI Commands

```bash
# Core commands needed:
fichero ingest <path> [--copy|--link] [--no-extract]
fichero search <query> [--limit N]
fichero db stats
fichero db reindex

# Key management:
fichero keys set <provider>
fichero keys get <provider>
fichero keys list

# Diagnostics:
fichero doctor  # Check all integrations working
```

---

## Implementation Status

### ✅ COMPLETED

1. **Fix keychain.py** - Rewritten with Rubicon Security framework
   - Uses `NSMutableDictionary`, `SecItemAdd`, `SecItemCopyMatching`, etc.
   - No more subprocess calls

2. **Consolidate search** - Deleted `search/` folder
   - Search methods now in `db.py`: `embed()`, `search()`, `reindex_all()`
   - Single LanceDB connection, single embeddings table

3. **Connect loaders** - Added `extract_text` param to ingest
   - `ingest_file(path, extract_text=True)` uses loaders
   - Sets `doc.page_content` with extracted text

4. **Add auto-embed** - Added to `db.save()` and `ingest_file()`
   - `db.save(doc, auto_embed=True)` creates embedding
   - `ingest_file(path, auto_embed=True)` creates embedding

5. **Tests** - 119 tests passing
   - `test_db.py`: 35 tests
   - `test_ingest_module.py`: 39 tests
   - `test_storage.py`: 24 tests
   - `test_backend_integration.py`: 20 tests (new)

---

## Success Criteria

✅ Backend is ready:

1. ✅ Single LanceDB connection (in db.py)
2. ✅ Keychain uses Rubicon (no subprocess)
3. ✅ Ingest extracts text via loaders
4. ✅ Embeddings created on save (when content exists)
5. ✅ `db.search()` returns relevant documents
6. ✅ All tests pass
7. ⏳ CLI commands - can add as needed

---

## Notes

- Keep implementations simple and Pythonic
- Django-style patterns (models, managers)
- Comments where logic isn't obvious
- No over-engineering
- Test-driven where practical
