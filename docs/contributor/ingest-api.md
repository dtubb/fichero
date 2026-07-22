<!-- Verified against fichero/importers/ingest.py (2026-07-18). Describes only what is built. -->

# Ingest API Documentation

The ingest module provides an API for file and folder ingestion with various
configuration options. The functions live in `fichero.importers.ingest`.

Both `ingest_file` and `ingest_folder` also accept internal `db` and
`package_path` arguments (inject a `Database` / target the library package);
omit them for normal use — they default to the active library.

## Core Functions

### `ingest_file()`

Ingest a single file with configurable options.

```python
from fichero.importers.ingest import ingest_file, IngestMode

# Basic usage - LINK mode (default)
doc = ingest_file(Path("/path/to/file.pdf"))

# COPY mode with text extraction
doc = ingest_file(
    Path("/path/to/document.docx"),
    mode=IngestMode.COPY,
    extract_text=True,
    auto_embed=True
)

# With parent collection
doc = ingest_file(
    Path("/path/to/image.jpg"),
    parent_id="collection_id_here",
    extract_metadata=True
)
```

**Parameters:**
- `path` (Path): Path to file
- `mode` (IngestMode): LINK (default), COPY, or MOVE
- `parent_id` (str, optional): Parent collection ID
- `extract_metadata` (bool): Extract file metadata (default: True)
- `extract_text` (bool): Extract text content (default: True, #881 — so dropped .md/.txt/.docx/.pdf-with-text are searchable immediately; image-only files still skip the loader)
- `auto_embed` (bool): Create embeddings (default: True, #881 — paired with `extract_text` so ingested text is immediately semantic-searchable)
- `save` (bool): Save to database (default: True)

**Returns:** `Document` object

**Raises:**
- `FileNotFoundError`: If file doesn't exist
- `ValueError`: If path is not a file

### `ingest_folder()`

Ingest all files from a folder with recursive processing.

```python
from fichero.importers.ingest import ingest_folder, IngestMode

# Basic folder ingestion
docs = ingest_folder(Path("/path/to/folder"))

# Advanced options
docs = ingest_folder(
    Path("/path/to/large_folder"),
    mode=IngestMode.COPY,
    recursive=True,
    extract_text=True,
    auto_embed=True,
    on_progress=lambda current, total: print(f"Progress: {current}/{total}")
)

# Without creating collection
docs = ingest_folder(
    Path("/path/to/files"),
    create_collection=False,
    parent_id="existing_collection_id"
)
```

**Parameters:**
- `folder` (Path): Folder to ingest
- `mode` (IngestMode): LINK (default), COPY, or MOVE
- `parent_id` (str, optional): Parent collection ID
- `recursive` (bool): Process subdirectories (default: True)
- `create_collection` (bool): Create collection for folder (default: True)
- `extract_text` (bool): Extract text content (default: True, #881 — so dropped .md/.txt/.docx/.pdf-with-text are searchable immediately; image-only files still skip the loader)
- `auto_embed` (bool): Create embeddings (default: True, #881 — paired with `extract_text` so ingested text is immediately semantic-searchable)
- `on_progress` (Callable): Progress callback (current, total)

**Returns:** List of `Document` objects

**Raises:**
- `FileNotFoundError`: If folder doesn't exist
- `ValueError`: If path is not a folder

## Ingestion Modes

### LINK Mode

```python
# Reference external file with bookmark
doc = ingest_file(Path("/external/location/file.pdf"), mode=IngestMode.LINK)
```

**Characteristics:**
- Creates macOS bookmark to reference original file
- No file copying - saves storage space
- Original file must remain accessible
- Bookmark data stored in document metadata

**Use cases:**
- Large files that shouldn't be duplicated
- Files that change frequently
- Limited storage scenarios

### COPY Mode

```python
# Import file into library
doc = ingest_file(Path("/external/file.jpg"), mode=IngestMode.COPY)
```

**Characteristics:**
- Copies file into Fichero's library storage
- Uses APFS cloning for instant copies on same volume
- Falls back to regular copy for cross-volume operations
- Files organized in sharded directory structure

**Use cases:**
- Files that should be preserved independently
- Portable libraries
- Offline access requirements

### MOVE Mode

```python
# Move file into library storage; the original is deleted
doc = ingest_file(Path("/external/file.jpg"), mode=IngestMode.MOVE)
```

**Characteristics:**
- Copies the file into Fichero's library storage, then deletes the original
- The library owns the only copy afterwards

**Use cases:**
- Files you want the library to take full ownership of
- Clearing the original location after import

## Utility Functions

### `detect_file_type()`

Detect file type from extension.

```python
from fichero.importers.ingest import detect_file_type

file_type = detect_file_type(Path("/path/to/file.jpg"))
# Returns: FileType.image
```

**Parameters:**
- `path` (Path): Path to file

**Returns:** `FileType` enum value

### `discover_files()`

Discover files in a folder with filtering.

```python
from fichero.importers.ingest import discover_files

# Find all files
for file_path in discover_files(Path("/path/to/folder")):
    print(file_path)

# Find specific extensions
for file_path in discover_files(
    Path("/path/to/folder"),
    extensions={".jpg", ".png"}
):
    print(file_path)
```

**Parameters:**
- `folder` (Path): Folder to search
- `extensions` (set[str], optional): Extensions to include
- `recursive` (bool): Search subdirectories (default: True)

**Yields:** Path objects

### `count_files()`

Count files in a folder.

```python
from fichero.importers.ingest import count_files

count = count_files(Path("/path/to/folder"))
print(f"Found {count} files")

# Count specific file types
image_count = count_files(
    Path("/path/to/folder"),
    extensions={".jpg", ".png", ".gif"}
)
```

**Parameters:**
- `folder` (Path): Folder to count
- `extensions` (set[str], optional): Extensions to include
- `recursive` (bool): Count subdirectories (default: True)

**Returns:** int (file count)

### `find_duplicates()`

Find duplicate documents by checksum.

```python
from fichero.importers.ingest import find_duplicates

duplicates = find_duplicates(documents)
for checksum, duplicate_docs in duplicates.items():
    print(f"Found {len(duplicate_docs)} duplicates for {checksum}")
```

**Parameters:**
- `documents` (list[Document]): Documents to check

**Returns:** dict[str, list[Document]] (checksum → duplicate documents)

## Advanced Usage Patterns

### Batch Processing with Progress Tracking

```python
def progress_callback(current, total):
    percentage = (current / total) * 100
    print(f"Processing: {current}/{total} ({percentage:.1f}%)")

docs = ingest_folder(
    Path("/large/folder"),
    mode=IngestMode.COPY,
    extract_text=True,
    on_progress=progress_callback
)
```

### Custom Folder Hierarchy

```python
# Ingest with custom parent collection
collection = db.query(Document, doc_type=DocType.collection)[0]
docs = ingest_folder(
    Path("/path/to/files"),
    parent_id=collection.id,
    create_collection=False
)
```

### Selective Text Extraction

```python
# Only extract text from specific file types
from fichero.models import FileType

docs = ingest_folder(Path("/path/to/folder"))
for doc in docs:
    if doc.file_type in {FileType.pdf, FileType.word}:
        # Extract text for documents
        doc = ingest_file(
            Path(doc.path),
            mode=doc.metadata.get("ingest_mode", IngestMode.LINK),
            extract_text=True,
            save=True
        )
```

### Error Handling and Recovery

```python
try:
    docs = ingest_folder(Path("/path/to/folder"))
except Exception as e:
    logger.error(f"Ingestion failed: {e}")
    # Implement recovery logic
```

## API Best Practices

1. **Mode Selection**: Choose LINK for large files, COPY for portability
2. **Text Extraction**: Enable for searchable content types (PDF, Word, text)
3. **Progress Tracking**: Use callbacks for large operations
4. **Error Handling**: Implement proper exception handling
5. **Memory Management**: Process files in batches for large folders
6. **Deduplication**: Use `find_duplicates()` to avoid redundant imports
7. **Metadata**: Extract metadata for better organization and search

## Performance Considerations

- **APFS Cloning**: Near-instant for same-volume copies
- **Memory Usage**: Text extraction can be memory-intensive for large documents
- **Batch Size**: Process large folders in reasonable batches
- **Parallel Processing**: Consider parallel processing for independent files

## Integration Examples

### Database Integration

```python
from fichero.db import db
from fichero.importers.ingest import ingest_file

# Ingest and query
doc = ingest_file(Path("/path/to/file.pdf"))
results = db.search("some query")
```

### Search Integration

```python
# Ingest with text extraction for search
doc = ingest_file(
    Path("/path/to/document.docx"),
    extract_text=True,
    auto_embed=True
)

# Now searchable
results = db.semantic_search("find relevant content")
```

### Bookmark System Integration

```python
# LINK mode creates bookmarks automatically
doc = ingest_file(Path("/external/file.pdf"), mode=IngestMode.LINK)
bookmark_data = doc.metadata.get("bookmark")
```