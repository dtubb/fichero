# Briefcase Packaging Questions for Fichero Data Layer

## Context

Fichero is adding a new data layer with these dependencies:

```toml
# Already in pyproject.toml (working)
"pydantic>=2.0.0,<3.0.0"
"duckdb>=1.0.0,<2.0.0"

# New additions
"lancedb>=0.25.0,<1.0.0"        # Vector DB (Rust-based)
"langchain>=0.3.25,<0.4.0"      # ML pipeline framework
"langgraph>=0.2.50"             # Workflow graphs
```

## Specific Questions

### 1. DuckDB Native Extensions

DuckDB is an embedded analytical database (like SQLite but columnar). It has native C++ extensions.

**Current status**: Listed in pyproject.toml macOS requires, untested in packaged app.

**Question**: Any known issues with DuckDB in Briefcase macOS packages? Does it need special handling for ARM64?

### 2. LanceDB (Rust-based)

LanceDB is a vector database for ML embeddings. It's written in Rust with Python bindings.

**Wheel**: `lancedb-0.25.3-cp39-abi3-macosx_11_0_arm64.whl` (34.5 MB)

**Question**: Does Briefcase handle Rust-based wheels correctly? Any special considerations for the native library bundling?

### 3. Kreuzberg (Optional)

[Kreuzberg](https://github.com/deepset-ai/kreuzberg) is a document extraction library (PDFs, Office docs, EPUBs). It optionally depends on:
- poppler (for PDF rendering)
- tesseract (for OCR)

**Question**: If we want Kreuzberg, do we need to bundle poppler/tesseract as system dependencies? Or should we stick with PyMuPDF which is pure Python + bundled binaries?

### 4. External File Access

Fichero supports "external collections" where files stay in user's folders (e.g., `/Users/bob/Documents/Archive/`) rather than being copied into the app's library.

We store macOS bookmarks (security-scoped) to survive file moves/renames.

**Questions**:
- Does Briefcase's macOS app have full disk access, or is it sandboxed?
- Do we need specific entitlements for accessing files outside the app container?
- Are security-scoped bookmarks working in Briefcase apps?

### 5. Network Access for IIIF

Fichero fetches images from IIIF servers (cultural heritage image APIs). This involves:
- HTTP requests to fetch manifests (JSON)
- HTTP requests to download images

**Question**: Any network entitlements needed for Briefcase macOS apps?

### 6. PyArrow (LanceDB dependency)

LanceDB depends on PyArrow (Apache Arrow for Python). PyArrow is a large native library.

**Wheel**: `pyarrow-22.0.0-cp312-cp312-macosx_12_0_arm64.whl` (34.2 MB)

**Question**: PyArrow is commonly used - any known Briefcase compatibility notes?

---

## Current Working Dependencies

These are already in pyproject.toml and working:

```toml
# Document processing
"pdf2image>=1.17.0,<2.0.0"
"pymupdf>=1.25.0,<2.0.0"
"python-docx>=1.1.2,<2.0.0"

# AI/ML
"openai>=1.0.0"
"dashscope>=1.20.0"
"langchain>=0.3.25,<0.4.0"
"langchain-core>=0.3.79,<0.4.0"
"langgraph>=0.2.50"

# Data
"pydantic>=2.0.0,<3.0.0"
"duckdb>=1.0.0,<2.0.0"
```

## Proposed Additions

```toml
# Vector search
"lancedb>=0.25.0,<1.0.0"

# Optional: Enhanced document extraction
# "kreuzberg>=0.5.0"  # Only if packaging works
```

---

## Fallback Plan

If LanceDB causes packaging issues:
- Use DuckDB's built-in JSON/array types for basic vector storage
- Add LanceDB later when packaging is resolved

If Kreuzberg causes packaging issues:
- Stick with PyMuPDF for PDFs (already working)
- Use python-docx for Word files (already working)
- Skip EPUB support initially

---

## Test Request

Could you do a quick test build with these additions to pyproject.toml?

```toml
[tool.briefcase.app.fichero.macOS]
requires = [
    # ... existing ...
    "lancedb>=0.25.0,<1.0.0",
]
```

Just `briefcase build macOS` to see if it packages without errors. No need to test functionality - just packaging.
