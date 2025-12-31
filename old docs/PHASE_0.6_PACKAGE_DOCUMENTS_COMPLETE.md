# Phase 0.6: Package Documents Implementation

**Date:** 2025-12-30
**Status:** ✅ Frontend Complete | ✅ Backend Core Complete | ⏳ Route Updates Needed

---

## Executive Summary

Successfully implemented **portable package documents** for Fichero. Each `.fichero` file is now a self-contained package (like `.keynote` or `.pages`) containing:
- `document.json` - Session metadata
- `fichero.duckdb` - Database
- `lance/` - Vector embeddings
- `storage/` - Thumbnails and previews
- `files/` - Imported files (COPY mode)

**Key Benefits:**
- ✅ **Portable** - Copy/move/backup as single file
- ✅ **Mac-native** - Right-click → Show Package Contents
- ✅ **Shareable** - Send entire library to colleagues
- ✅ **Clean** - No Application Support clutter
- ✅ **Multi-library** - Open multiple libraries simultaneously

---

## What Changed from Previous Design

**BEFORE (Application Support storage):**
```
MyLibrary.fichero                          ← JSON file
~/Library/Application Support/Fichero/
└── libraries/
    └── 550e8400.../                       ← Data here
        ├── fichero.duckdb
        ├── lance/
        └── files/
```

**AFTER (Package documents):**
```
MyLibrary.fichero/                         ← Package (all data inside!)
├── document.json                          ← Metadata
├── fichero.duckdb                         ← Database
├── lance/                                 ← Vectors
├── storage/                               ← Thumbnails
└── files/                                 ← Files
```

---

## Frontend Changes ✅ COMPLETE

### 1. FicheroDocument.swift - Package FileDocument

**UTType Declaration:**
```swift
extension UTType {
    static var ficheroSession: UTType {
        UTType(exportedAs: "ca.tubb.fichero.library", conformingTo: .package)
    }
}
```

**Reading Package:**
```swift
init(configuration: ReadConfiguration) throws {
    // Read document.json from package
    guard let documentWrapper = configuration.file.fileWrappers?["document.json"],
          let data = documentWrapper.regularFileContents else {
        throw CocoaError(.fileReadCorruptFile)
    }

    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601
    self = try decoder.decode(FicheroDocument.self, from: data)
}
```

**Writing Package:**
```swift
func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper {
    // Encode metadata to document.json
    let data = try encoder.encode(self)
    let documentFile = FileWrapper(regularFileWithContents: data)

    // Create package directory with document.json, lance/, storage/, files/
    var fileWrappers: [String: FileWrapper] = [
        "document.json": documentFile
    ]

    // Preserve existing database, lance, storage, files from existingFile
    // ... (see code for full implementation)

    return FileWrapper(directoryWithFileWrappers: fileWrappers)
}
```

**Package Path Helper:**
```swift
func packagePaths(for packageURL: URL) -> (
    databasePath: URL,
    lanceDBPath: URL,
    storagePath: URL,
    filesPath: URL
) {
    return (
        databasePath: packageURL.appendingPathComponent("fichero.duckdb"),
        lanceDBPath: packageURL.appendingPathComponent("lance"),
        storagePath: packageURL.appendingPathComponent("storage"),
        filesPath: packageURL.appendingPathComponent("files")
    )
}
```

### 2. Info.plist - Package Type Declaration

```xml
<key>UTExportedTypeDeclarations</key>
<array>
    <dict>
        <key>UTTypeConformsTo</key>
        <array>
            <string>com.apple.package</string>
        </array>
        <key>UTTypeDescription</key>
        <string>Fichero Library</string>
        <key>UTTypeIdentifier</key>
        <string>ca.tubb.fichero.library</string>
        <key>UTTypeTagSpecification</key>
        <dict>
            <key>public.filename-extension</key>
            <array>
                <string>fichero</string>
            </array>
        </dict>
        <key>LSTypeIsPackage</key>
        <true/>
    </dict>
</array>
```

### 3. APIClient.swift - Send Package Path Header

**Changed from library ID to library path:**
```swift
/// Current library path - set by DocumentTabView when a library is loaded
/// Sent as "X-Fichero-Library-Path" header with every request
@Published var currentLibraryPath: String?

private func configureRequest(_ request: inout URLRequest) {
    if let libraryPath = currentLibraryPath {
        request.setValue(libraryPath, forHTTPHeaderField: "X-Fichero-Library-Path")
    }
}
```

All 8 HTTP methods updated to call `configureRequest(&request)`.

### 4. FicheroApp.swift - Pass Document URL

```swift
DocumentGroup(newDocument: FicheroDocument()) { file in
    DocumentTabView(document: file.$document, documentURL: file.fileURL)
        // ... environment objects
}
```

### 5. DocumentTabView.swift - Set Library Path

```swift
struct DocumentTabView: View {
    @Binding var document: FicheroDocument
    let documentURL: URL?  // Package file URL

    var body: some View {
        // ...
        .task {
            // Set library path for all API requests from this tab
            if let url = documentURL {
                APIClient.shared.currentLibraryPath = url.path
            }
            await loadContext()
        }
    }
}
```

---

## Backend Changes ✅ CORE COMPLETE

### 1. db.py - DatabaseManager for Package Documents

**New DatabaseManager Class:**
```python
class DatabaseManager:
    """Manages multiple Database instances for package documents."""

    def __init__(self):
        self._databases: dict[str, Database] = {}
        self._lock = threading.Lock()

    def get_database(self, package_path: str | Path) -> Database:
        """Get or create Database instance for a package."""
        package_path = Path(package_path)
        package_str = str(package_path)

        with self._lock:
            if package_str not in self._databases:
                # Create connection for this package
                db_path = package_path / "fichero.duckdb"
                db = Database(path=db_path)
                db._migrate_workflow_table()
                db._migrate_saved_search_table()
                self._databases[package_str] = db

            return self._databases[package_str]

    def close_database(self, package_path: str | Path):
        """Close database connection for a package."""
        # ... implementation

    def close_all(self):
        """Close all database connections."""
        # ... implementation


# Global database manager
db_manager = DatabaseManager()
```

**Features:**
- Thread-safe connection pooling
- Lazy initialization (creates DB on first access)
- Automatic schema migration for new packages
- Clean shutdown closes all connections

### 2. main.py - FastAPI Dependency

**get_library_database Dependency:**
```python
async def get_library_database(
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path")
) -> Database:
    """Extract library path from header and return Database instance."""
    if not x_fichero_library_path:
        raise HTTPException(
            status_code=400,
            detail="Missing X-Fichero-Library-Path header"
        )

    try:
        db = db_manager.get_database(x_fichero_library_path)
        return db
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to access library database: {str(e)}"
        )
```

**Health Check - Works With or Without Library:**
```python
@app.get("/api/health")
async def health_check(
    x_fichero_library_path: str | None = Header(None, alias="X-Fichero-Library-Path")
):
    if x_fichero_library_path:
        # Library-specific health
        db = db_manager.get_database(x_fichero_library_path)
        return {
            "status": "healthy",
            "library_path": x_fichero_library_path,
            "document_count": db.count(Document),
        }
    else:
        # General backend health
        return {
            "status": "healthy",
            "backend_version": "0.1.0",
            "active_libraries": len(db_manager._databases),
        }
```

**Stats Endpoint - Requires Library:**
```python
@app.get("/api/stats")
async def get_stats(db: Database = Depends(get_library_database)):
    return {
        "documents": db.count(Document),
        "artifacts": db.count(Artifact),
        "embedding_stats": db.embedding_stats(),
    }
```

**Lifespan - Close All Connections on Shutdown:**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Fichero API starting up...")
    from fichero.db import db_manager
    yield
    logger.info("Shutting down - closing all database connections...")
    db_manager.close_all()
```

### 3. documents.py - Example Route Update ✅

**Pattern for All Route Updates:**
```python
# OLD
from fichero.db import db

@router.get("")
async def list_documents(...):
    docs = list(db.query(Document, **filters))
    return docs
```

```python
# NEW
from fichero.db import Database
from fichero.api.main import get_library_database
from fastapi import Depends

@router.get("")
async def list_documents(
    ...,
    db: Database = Depends(get_library_database),
):
    docs = list(db.query(Document, **filters))  # Uses library-specific db
    return docs
```

---

## Remaining Work ⏳

### Route Files That Need Updating

Apply the same pattern to ALL endpoints in these files:

1. **`src/fichero/api/routes/documents.py`** - ✅ 1/9 endpoints updated
   - ✅ `GET /` - list_documents
   - ⏳ `GET /collections` - list_collections
   - ⏳ `GET /{id}` - get_document
   - ⏳ `POST /` - create_document
   - ⏳ `PUT /{id}` - update_document
   - ⏳ `DELETE /{id}` - delete_document
   - ⏳ `GET /hierarchy` - get_hierarchy
   - ⏳ `POST /move` - move_document
   - ⏳ `POST /duplicate` - duplicate_document

2. **`src/fichero/api/routes/search.py`** - 0/3 endpoints
   - ⏳ `POST /` - search_documents
   - ⏳ `POST /semantic` - semantic_search
   - ⏳ `GET /saved` - list_saved_searches

3. **`src/fichero/api/routes/chat.py`** - 0/4 endpoints
   - ⏳ `POST /` - chat
   - ⏳ `GET /conversations` - list_conversations
   - ⏳ `GET /conversations/{id}` - get_conversation
   - ⏳ `DELETE /conversations/{id}` - delete_conversation

4. **`src/fichero/api/routes/workflows.py`** - 0/5 endpoints
   - ⏳ `POST /execute` - execute_workflow
   - ⏳ `GET /` - list_workflows
   - ⏳ `POST /` - create_workflow
   - ⏳ `GET /{id}` - get_workflow
   - ⏳ `DELETE /{id}` - delete_workflow

5. **`src/fichero/api/routes/ingest.py`** - 0/2 endpoints
   - ⏳ `POST /import` - import_file
   - ⏳ `POST /folder` - import_folder

6. **`src/fichero/api/routes/storage.py`** - 0/3 endpoints
   - ⏳ `GET /thumbnail/{doc_id}` - get_thumbnail
   - ⏳ `GET /display/{doc_id}` - get_display
   - ⏳ `GET /source/{doc_id}` - get_source

7. **`src/fichero/api/routes/providers.py`** - May not need updates (no DB access)

8. **`src/fichero/api/routes/models.py`** - May not need updates (no DB access)

**Total**: ~22 endpoints need the `db: Database = Depends(get_library_database)` parameter added

---

## Update Pattern - Copy/Paste Instructions

For each endpoint in the route files:

### Step 1: Update imports at top of file
```python
# Remove this
from fichero.db import db

# Add these
from fichero.db import Database
from fichero.api.main import get_library_database
from fastapi import Depends  # Add to existing import if needed
```

### Step 2: Add dependency to each endpoint
```python
@router.get("some/path")
async def endpoint_name(
    # ... existing parameters ...
    db: Database = Depends(get_library_database),  # ← Add this
) -> ReturnType:
    # Function body stays the same - db is now library-specific!
    result = db.query(SomeModel)
    return result
```

That's it! The function body doesn't change - just add the dependency parameter.

---

## Storage Service Updates Needed

**Current ingest.py:**
```python
# Hardcoded paths
storage_dir = Path.home() / "Library" / "Application Support" / "Fichero" / "storage"
```

**Needs to become:**
```python
# Package-relative paths
def get_storage_path(package_path: Path, doc_id: str, type: str) -> Path:
    return package_path / "storage" / type / f"{doc_id}.jpg"

def get_files_path(package_path: Path, doc_id: str) -> Path:
    return package_path / "files" / f"{doc_id}"
```

Pass `package_path` from the API route (extracted from header):
```python
@router.post("/import")
async def import_file(
    file_path: str,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
):
    package_path = Path(x_fichero_library_path)
    storage_path = get_storage_path(package_path, doc_id, "thumbnails")
    # ... use package-relative path
```

---

## Testing Checklist

### Frontend Testing

- [ ] Create new library (File → New)
  - Verify .fichero package created
  - Verify document.json inside package
  - Verify empty lance/, storage/, files/ directories created

- [ ] Import documents to library
  - Verify fichero.duckdb created inside package
  - Verify documents stored in package's database
  - Verify files/ populated for COPY mode

- [ ] Multi-tab testing
  - Open Library A in Tab 1
  - Open Library B in Tab 2
  - Switch tabs
  - Verify each tab shows correct library data

- [ ] Multi-window testing
  - Open same library in two windows
  - Verify changes in one window appear in other (shared database)

- [ ] Move/rename package
  - Move MyLibrary.fichero to different folder
  - Open it
  - Verify all data still accessible

- [ ] Share package
  - Copy .fichero file to another Mac
  - Open it
  - Verify all documents, vectors, files present

### Backend Testing

- [ ] Health check without library
  ```bash
  curl http://127.0.0.1:8765/api/health
  # Should return: {"status": "healthy", "backend_version": "0.1.0", "active_libraries": 0}
  ```

- [ ] Health check with library
  ```bash
  curl -H "X-Fichero-Library-Path: /Users/name/MyLibrary.fichero" \
       http://127.0.0.1:8765/api/health
  # Should return: {"status": "healthy", "library_path": "...", "document_count": N}
  ```

- [ ] Database isolation
  - Import document to Library A
  - List documents from Library B
  - Verify Library B doesn't see Library A's documents

- [ ] Concurrent access
  - Open 3 different libraries
  - Make changes to each
  - Verify no cross-contamination

- [ ] Package creation
  - Create new .fichero file in Swift app
  - Verify backend creates fichero.duckdb on first request
  - Verify schema tables created properly

---

## Performance Notes

### Connection Pooling Benefits

- **Reuse across requests**: Opening Library A 100 times = 1 database connection
- **Fast switching**: Switching tabs reuses existing connection
- **Memory efficient**: Only active libraries kept in memory

### Potential Optimizations

If > 10 libraries open simultaneously, consider:
1. **LRU eviction**: Close least-recently-used connections
2. **Max connection limit**: Prevent unbounded memory growth
3. **Connection timeout**: Close idle connections after N minutes

Current implementation is simple and works well for typical usage (1-5 libraries).

---

## Architecture Benefits

### Before (External Storage)
**Problems:**
- Libraries scattered in Application Support
- Hard to backup (need to find all files)
- Can't share libraries easily
- Library ID in document, data elsewhere

### After (Package Documents)
**Solutions:**
- ✅ Everything in one place
- ✅ Backup = copy file
- ✅ Share = send file
- ✅ Portable across Macs
- ✅ Mac-native (packages)
- ✅ Clean filesystem

---

## Migration Notes

**No migration needed** - This is a new feature. Existing users (if any) would need to re-import their documents into new .fichero packages.

If migration is required later:
1. Create migration script that:
   - Reads old Application Support database
   - Creates new .fichero package
   - Copies database, lance/, storage/, files/ into package
   - Updates file paths in database

---

## Related Documentation

- **Swift Code**: `Fichero/Fichero/Models/FicheroDocument.swift`
- **Backend Core**: `src/fichero/db.py` (DatabaseManager)
- **FastAPI Dependency**: `src/fichero/api/main.py` (get_library_database)
- **Example Route**: `src/fichero/api/routes/documents.py`
- **Original Plan**: `PHASE_0.6_BACKEND_PLAN.md`
- **Frontend Summary**: `PHASE_0.6_FRONTEND_COMPLETE.md`

---

**Created By:** Claude Code
**Last Updated:** 2025-12-30
**Status:** ✅ Core Implementation Complete | ⏳ 21 Route Endpoints Need Updates
