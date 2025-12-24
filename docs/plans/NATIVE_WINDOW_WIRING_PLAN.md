# Native Window Wiring Plan

## Goal

Wire up the native macOS window components so they work together:
- Sidebar → Browser → Editor → Inspector
- Toolbar Search → db.search() → Browser results
- Fix sidebar crash on folder expansion

## Design Principles

1. **Pythonic** - Simple functions, clear data flow, no over-abstraction
2. **Pydantic + DuckDB + LanceDB** - Single source of truth for data
3. **Views are dumb** - Components receive data, don't query database
4. **Window controller orchestrates** - All data flow through MainWindowController

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    MainWindowController                          │
│  (window.py - orchestrates all data flow)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │ Sidebar  │───▶│ Browser  │───▶│  Editor  │    │Inspector │  │
│  │          │    │          │    │          │    │          │  │
│  │ on_select│    │ on_select│    │ .load()  │    │ .load()  │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
│       │                │               ▲              ▲         │
│       │                │               │              │         │
│       ▼                ▼               │              │         │
│  ┌─────────────────────────────────────┴──────────────┘         │
│  │              Data Layer (db.py)                              │
│  │  db.query(Document, parent_id=...) → [Document, ...]         │
│  │  db.search(query) → [SearchResult, ...]                      │
│  │  db.get(Document, id) → Document                             │
│  └──────────────────────────────────────────────────────────────┘
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Current Issues (2025-12-11)

### 1. Sidebar Crash on Folder Expansion

**Problem:** Recursive `_load_document_children()` can crash due to:
- Deep recursion on large hierarchies
- DuckDB concurrency issues
- KVO notifications during tree modification

**Solution:** Limit recursion depth, add error handling.

### 2. Toolbar Search Not Connected

**Problem:** `AppToolbar` has `on_search` parameter but it's never passed.

**Solution:** Pass callback in `_setup_menu_toolbar()`.

### 3. Search Results Display

**Problem:** No way to show search results in browser.

**Solution:** Search results update `browser.items` directly.

## Implementation Plan

### Phase 1: Fix Sidebar (Prevent Crash)

File: `sidebar_native.py`

1. Add max depth limit to `_load_document_children()`
2. Wrap db calls in try/except
3. Add logging for debugging

### Phase 2: Wire Toolbar Search

File: `window.py`

1. Add `_on_toolbar_search()` method
2. Pass it to AppToolbar via `on_search` parameter
3. Search calls `db.search()` and updates browser

### Phase 3: Add Logging

Files: `window.py`, `sidebar_native.py`, `browser.py`

1. Add info-level logging at key data flow points
2. Makes debugging easier

## Data Flow After Fix

```
User clicks folder in Sidebar
         │
         ▼
sidebar.on_select("doc:abc123")
         │
         ▼
window._on_sidebar_select("doc:abc123")
         │
         ├─▶ Strip prefix: "abc123"
         ├─▶ db.get(Document, "abc123") → doc
         ├─▶ db.query(Document, parent_id="abc123") → children
         └─▶ browser.items = children
                   │
                   ▼
         Browser shows thumbnails


User types in search bar
         │
         ▼
toolbar.on_search("query")
         │
         ▼
window._on_toolbar_search("query")
         │
         ├─▶ db.search("query") → [SearchResult, ...]
         ├─▶ Convert to Documents
         └─▶ browser.items = docs
```

## Files to Modify

| File | Changes |
|------|---------|
| `sidebar_native.py` | Add depth limit, error handling |
| `window.py` | Add `_on_toolbar_search()`, wire to toolbar |

## Testing

1. Launch app: `PYTHONPATH=src .venv/bin/python -m fichero.gui`
2. Click folders in sidebar - should not crash
3. Type in search bar - should show results in browser
4. Click search result - should show in editor/inspector

---

## Future: Local OCR Providers

For image text extraction without API calls, add local OCR as providers:

| Library | Notes |
|---------|-------|
| **kreuzberg** | In pyproject.toml. Multi-format extraction |
| **rapidocr** | Installed. Pure Python, fast |
| **ocrmac** | Installed. Native macOS Vision framework (best for Mac) |
| **pytesseract** | In pyproject.toml. Tesseract wrapper |

Implementation: Add as providers in transcription system, no API key needed.
