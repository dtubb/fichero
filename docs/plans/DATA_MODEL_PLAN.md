# Fichero Data Model Plan

## The Big Picture

Fichero is a document processing app. Here's what happens:

```
1. IMPORT    →  User adds files (PDFs, images, folders)
2. ORGANIZE  →  Files arranged in hierarchy (collections, folders, groups)
3. PROCESS   →  AI extracts content (OCR, entities, summaries)
4. REVIEW    →  User corrects and annotates
5. EXPORT    →  Output to Word, PDF, etc.
```

We need to track all of this in a database.

---

## The 7 Models

| Model | What it is | Real-world example |
|-------|------------|-------------------|
| **Document** | Any file or organizational unit | A PDF, an image, a folder, a page |
| **Artifact** | Any AI output | Transcription, entities, summary |
| **Workflow** | A processing recipe | "OCR then extract people and places" |
| **Run** | One execution of a workflow | "Processing batch of 50 images" |
| **Trace** | Debug data from AI calls | "GPT-4 took 3.2s and used 800 tokens" |
| **Note** | User annotation | "Check this translation" |
| **Event** | Change history | "User renamed document at 3pm" |

---

## How They Relate

```
                    ┌─────────────────────────────────────┐
                    │           DOCUMENT                   │
                    │  (files, folders, pages, groups)    │
                    └─────────────┬───────────────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
              ▼                   ▼                   ▼
        ┌──────────┐       ┌──────────┐       ┌──────────┐
        │ ARTIFACT │       │   NOTE   │       │  EVENT   │
        │ (AI out) │       │ (user    │       │ (history)│
        └────┬─────┘       │ comments)│       └──────────┘
             │             └──────────┘
             │
    ┌────────┴────────┐
    │                 │
    ▼                 ▼
┌───────┐       ┌─────────┐
│  RUN  │◄──────│WORKFLOW │
│(exec) │       │(recipe) │
└───┬───┘       └─────────┘
    │
    ▼
┌─────────┐
│  TRACE  │
│(debug)  │
└─────────┘
```

---

## Model 1: Document

**What it represents:** Any node in your file hierarchy.

```
Collection: "Family Archive"
  └── Folder: "Box 1"
        └── Group: "Letter from John"     ← A logical document (3 pages)
              ├── File: page_001.jpg
              ├── File: page_002.jpg
              └── File: page_003.jpg
                    └── Chunk: signature   ← A cropped region
```

**Key fields:**

| Field | Purpose |
|-------|---------|
| `parent_id` | Hierarchy (folder contains file) |
| `doc_type` | collection, folder, group, file, page, chunk |
| `path` | Where the file lives |
| `page_content` | Text content (LangChain compatible) |
| `metadata` | Everything else (size, thumbnail, checksum, etc.) |

**Derived files** (extracted pages, enhanced images, thumbnails):
- Stored in library: `~/Library/Fichero/derived/{id}/`
- Tracked via `metadata["derived_from"]`

---

## Model 2: Artifact

**What it represents:** Any output from processing.

```python
# AI transcribes an image
Artifact(
    document_id="page_001",
    artifact_type="transcription",
    content="Dear Mary, I am writing from London...",
    provider="qwen",
    model="qwen-vl-max",
    version=1
)

# User corrects it
Artifact(
    document_id="page_001",
    source_artifact_id=above.id,  # Chains to original
    artifact_type="transcription",
    content="Dear Mary, I am writing from Liverpool...",  # Fixed
    provider="human",
    version=2
)
```

**Key fields:**

| Field | Purpose |
|-------|---------|
| `document_id` | Which document this is about |
| `source_artifact_id` | For versioning (points to previous version) |
| `artifact_type` | "transcription", "entities", "summary", etc. |
| `content` | Text output |
| `data` | Structured output (JSON for entities, etc.) |
| `provider` | "qwen", "openai", "human" |
| `version` | Version number |

---

## Model 3: Workflow

**What it represents:** A recipe for processing.

```python
Workflow(
    name="Full Analysis",
    description="OCR, extract entities, summarize",
    steps=[
        {"name": "transcribe", "tool": "transcribe", "provider": "qwen"},
        {"name": "entities", "tool": "extract_entities", "provider": "openai"},
        {"name": "summarize", "tool": "summarize", "provider": "openai"}
    ]
)
```

---

## Model 4: Run

**What it represents:** One execution of a workflow.

```python
Run(
    workflow_id="full_analysis",
    document_ids=["page_001", "page_002", "page_003"],
    status="running",
    progress=0.33,
    current_step="transcribe",
    tokens_used=2500,
    cost_usd=0.05
)
```

**Key fields:**

| Field | Purpose |
|-------|---------|
| `status` | queued, running, completed, failed, cancelled |
| `progress` | 0.0 to 1.0 |
| `attempt` | Retry count |
| `tokens_used` | Total tokens consumed |
| `cost_usd` | Total cost |

---

## Model 5: Trace

**What it represents:** Debug data from LangChain/LangGraph calls.

When AI runs, lots happens under the hood. Trace captures it for debugging:

```python
Trace(
    run_id="run_123",
    name="transcribe",
    trace_type="llm",
    model="qwen-vl-max",
    status="completed",
    latency_ms=3200,
    tokens_in=150,
    tokens_out=800,
    cost_usd=0.003,
    input_preview="[image: page_001.jpg]",
    output_preview="Dear Mary, I am writing..."
)
```

**Why it matters:**
- Debug failures: "Why did this fail?"
- Track costs: "How much am I spending on OpenAI?"
- Optimize: "Which calls are slow?"

---

## Model 6: Note

**What it represents:** User annotations.

```python
Note(
    target_type="Document",
    target_id="page_001",
    content="Handwriting is hard to read here",
    note_type="comment",
    bbox=(100, 200, 300, 50)  # Position on image
)
```

**Types:** comment, question, flag, correction

---

## Model 7: Event

**What it represents:** Change history for undo.

```python
Event(
    event_type="document.update",
    target_type="Document",
    target_id="page_001",
    before={"name": "old_name.jpg"},
    after={"name": "new_name.jpg"},
    source="user"
)
```

**Enables:**
- Undo/redo
- Audit trail ("who changed what when")
- Time travel ("show me state from yesterday")

---

## File Storage

**Where files live:**

```
~/Library/Application Support/Fichero/
├── library.duckdb              # Main database (DuckDB)
├── vectors/                    # Embeddings (LanceDB)
├── derived/                    # Processed files
│   └── {document_id}/
│       ├── thumbnail.png
│       ├── enhanced.png
│       └── page_001.png
├── traces/                     # Full LangChain debug logs
│   └── {run_id}.jsonl
└── exports/
    └── {export_id}/
```

**Original files:**
- User chooses: "Copy to library" or "Keep in place"
- If kept in place: store macOS bookmark (survives moves/renames)
- Bookmark stored in `metadata["bookmark"]`

---

## Embeddings (Vector Search)

Stored in **LanceDB** (separate from DuckDB):

```python
# Save embedding
db.save_vectors("embeddings", [{
    "id": artifact.id,
    "document_id": doc.id,
    "text": artifact.content[:500],
    "vector": [0.1, 0.2, 0.3, ...]  # From embedding model
}])

# Semantic search
results = db.search_vectors("embeddings", query_vector, limit=10)
```

---

## Summary Table

| Model | Stored in | Purpose |
|-------|-----------|---------|
| Document | DuckDB | File hierarchy |
| Artifact | DuckDB | AI outputs |
| Workflow | DuckDB | Pipeline recipes |
| Run | DuckDB | Pipeline execution |
| Trace | DuckDB + JSONL | AI debug data |
| Note | DuckDB | User annotations |
| Event | DuckDB | Change history |
| Embeddings | LanceDB | Vector search |

---

## What's NOT in the database

| Data | Where it goes |
|------|---------------|
| Settings | YAML config file |
| API keys | macOS Keychain or .env |
| UI state | Memory (not persisted) |
| Full trace logs | JSONL files |

---

## Remote Sources (IIIF, URLs)

Documents can come from remote sources, not just local files:

```python
Document(
    name="manuscript_page_042.jpg",
    doc_type=DocType.file,
    file_type=FileType.image,
    metadata={
        # Remote source
        "source_type": "iiif",  # or "url", "local"
        "source_url": "https://example.org/iiif/manuscript/canvas/42",
        "iiif_manifest": "https://example.org/iiif/manuscript/manifest.json",

        # Downloaded versions
        "full_path": "derived/abc123/full.jpg",        # Full resolution
        "display_path": "derived/abc123/display.jpg",  # Smaller for UI
        "thumbnail_path": "derived/abc123/thumb.jpg",  # Thumbnail

        # IIIF-specific
        "iiif_image_id": "https://example.org/iiif/image/42",
        "iiif_width": 4000,
        "iiif_height": 6000,
    }
)
```

**Source types:**

| source_type | Example |
|-------------|---------|
| `local` | File on disk (`/Users/bob/docs/letter.pdf`) |
| `url` | Direct URL (`https://example.com/image.jpg`) |
| `iiif` | IIIF manifest/canvas |
| `s3` | AWS S3 bucket |
| `gcs` | Google Cloud Storage |

**Downloaded versions:**

When you import from URL/IIIF, we download and store:
- `full` - Original resolution (for processing)
- `display` - Reasonable size for UI (e.g., 2000px)
- `thumbnail` - Small preview (e.g., 200px)

---

## File Types (Expanded)

Not just images and PDFs:

```python
class FileType(str, Enum):
    # Images
    image = "image"           # jpg, png, tiff, webp

    # Documents
    pdf = "pdf"
    word = "word"             # docx
    text = "text"             # txt, md

    # Audio
    audio = "audio"           # mp3, wav, m4a

    # Video
    video = "video"           # mp4, mov

    # Books
    epub = "epub"

    # Other
    other = "other"
```

**Each type has different processing:**

| FileType | Processing |
|----------|------------|
| image | OCR, enhance, segment |
| pdf | Extract pages → images → OCR |
| audio | Transcribe with Whisper |
| video | Extract audio → transcribe, extract frames |
| epub | Extract chapters, text |
| word | Extract text, images |

---

## Kreuzberg Integration

[Kreuzberg](https://github.com/deepset-ai/kreuzberg) is an open-source document extraction library.

**What it does:**
- Extracts text from PDFs (better than basic PyMuPDF)
- Handles scanned PDFs (OCR)
- Extracts tables
- Preserves layout

**How it fits:**

```python
# Kreuzberg becomes a provider like "qwen" or "openai"
Artifact(
    document_id="page_001",
    artifact_type="transcription",
    content="Extracted text...",
    provider="kreuzberg",      # ← Kreuzberg as provider
    model="kreuzberg-v1",
    data={
        "tables": [...],       # Extracted tables
        "layout": {...}        # Layout info
    }
)
```

**Workflow step:**

```python
Workflow(
    name="PDF Analysis",
    steps=[
        {"name": "extract", "tool": "kreuzberg_extract", "provider": "kreuzberg"},
        {"name": "summarize", "tool": "summarize", "provider": "openai"}
    ]
)
```

---

## Library Folder Structure (Updated)

```
~/Library/Application Support/Fichero/
├── library.duckdb              # Main database
├── vectors/                    # LanceDB embeddings
│
├── derived/                    # All derived/downloaded files
│   └── {document_id}/
│       ├── full.jpg            # Original/full resolution
│       ├── display.jpg         # Display size
│       ├── thumb.jpg           # Thumbnail
│       ├── enhanced.jpg        # Enhanced version
│       ├── audio.mp3           # Extracted audio (from video)
│       └── pages/              # Extracted pages (from PDF)
│           ├── 001.png
│           └── 002.png
│
├── traces/                     # LangChain debug logs
│   └── {run_id}.jsonl
│
├── exports/                    # Export outputs
│   └── {export_id}/
│
└── cache/                      # Temporary files
    └── downloads/              # In-progress downloads
```

**Path resolution:**

```python
def get_document_path(doc: Document, version: str = "display") -> Path:
    """Get the path to a document's file."""
    base = Path("~/Library/Application Support/Fichero").expanduser()

    # Check metadata for specific version
    if version == "thumbnail" and doc.metadata.get("thumbnail_path"):
        return base / doc.metadata["thumbnail_path"]
    elif version == "display" and doc.metadata.get("display_path"):
        return base / doc.metadata["display_path"]
    elif version == "full" and doc.metadata.get("full_path"):
        return base / doc.metadata["full_path"]

    # Fall back to main path
    if doc.path:
        return Path(doc.path)

    return None
```

---

## Summary: What metadata tracks

| Key | Purpose | Example |
|-----|---------|---------|
| `source_type` | Where it came from | "local", "iiif", "url" |
| `source_url` | Original URL | "https://..." |
| `source_path` | Original local path | "/Users/bob/docs/x.pdf" |
| `full_path` | Full resolution in library | "derived/abc/full.jpg" |
| `display_path` | Display version | "derived/abc/display.jpg" |
| `thumbnail_path` | Thumbnail | "derived/abc/thumb.jpg" |
| `derived_from` | Parent document ID | "doc_xyz" |
| `checksum` | File hash | "sha256:abc..." |
| `bookmark` | macOS bookmark | base64 data |
| `iiif_manifest` | IIIF manifest URL | "https://.../manifest.json" |
| `file_size` | Size in bytes | 1234567 |
| `width`, `height` | Dimensions | 1920, 1080 |
| `duration` | Audio/video length | 125.5 (seconds) |
| `page_count` | PDF pages | 42 |

---

## Later (if needed)

| Model | Purpose |
|-------|---------|
| Entity | Authority records (canonical "John Smith") |
| Link | Relationships (doc↔entity, doc↔doc) |
| Export | Export history |
