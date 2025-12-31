# Phase 0.6: Multiple Libraries - Backend Implementation Plan

**Date:** 2025-12-30
**Status:** Planning
**Frontend:** ✅ Complete
**Backend:** ⏳ Planning

---

## Executive Summary

Fichero must support multiple independent libraries, similar to DEVONthink or Bookends. Each `.fichero` document represents a complete library with its own:
- DuckDB database (`fichero.duckdb`)
- LanceDB vector store (`lance/`)
- Storage directory (`storage/` for thumbnails, previews)
- Files directory (`files/` for COPY mode imports)

The frontend has been updated to:
1. Track library metadata (ID, name, created date) in `FicheroDocument`
2. Send `X-Fichero-Library-ID` header with every HTTP request
3. Set library ID when document loads in `DocumentTabView`

This document outlines the required backend changes.

---

## Current Architecture Problem

**Single Global Database**: The current backend uses a single database connection initialized at startup:

```python
# src/fichero/db.py
class DatabaseManager:
    def __init__(self):
        self.db_path = get_db_path()  # Always ~/Library/Application Support/Fichero/fichero.duckdb
        self.lance_path = get_lance_path()  # Always .../lance/
        self.conn = duckdb.connect(str(self.db_path))
        self.lance_db = lancedb.connect(str(self.lance_path))
```

**Problem**: All API requests share the same database connection, regardless of which library the user is working with.

---

## Required Changes

### 1. Database Manager - Multi-Library Support

**File**: `src/fichero/db.py`

**Current**:
```python
class DatabaseManager:
    def __init__(self):
        self.db_path = get_db_path()
        self.conn = duckdb.connect(str(self.db_path))
        self.lance_db = lancedb.connect(str(self.lance_path))
```

**New**:
```python
class DatabaseManager:
    def __init__(self):
        # Connection pool: library_id -> (duckdb_conn, lance_db)
        self._connections: Dict[str, Tuple[duckdb.DuckDBPyConnection, lancedb.DBConnection]] = {}
        self._lock = threading.Lock()

    def get_connection(self, library_id: str) -> Tuple[duckdb.DuckDBPyConnection, lancedb.DBConnection]:
        """Get or create database connections for a specific library."""
        with self._lock:
            if library_id not in self._connections:
                # Compute paths for this library
                library_dir = get_library_directory(library_id)
                db_path = library_dir / "fichero.duckdb"
                lance_path = library_dir / "lance"

                # Create directory if needed
                library_dir.mkdir(parents=True, exist_ok=True)
                lance_path.mkdir(parents=True, exist_ok=True)

                # Create connections
                duckdb_conn = duckdb.connect(str(db_path))
                lance_conn = lancedb.connect(str(lance_path))

                # Initialize schema if new database
                self._initialize_schema(duckdb_conn, lance_conn)

                self._connections[library_id] = (duckdb_conn, lance_conn)

            return self._connections[library_id]

    def close_connection(self, library_id: str):
        """Close connections for a specific library."""
        with self._lock:
            if library_id in self._connections:
                duckdb_conn, lance_conn = self._connections[library_id]
                duckdb_conn.close()
                # lance_conn doesn't need explicit close
                del self._connections[library_id]

    def _initialize_schema(self, duckdb_conn, lance_conn):
        """Initialize database schema for new library."""
        # Run CREATE TABLE statements
        # Create LanceDB tables
        pass
```

**Helper Function**:
```python
def get_library_directory(library_id: str) -> Path:
    """Get storage directory for a specific library."""
    app_support = Path.home() / "Library" / "Application Support" / "Fichero"
    return app_support / "libraries" / library_id
```

---

### 2. FastAPI Dependency - Extract Library ID

**File**: `src/fichero/api/main.py`

**Add Dependency**:
```python
from fastapi import Header, HTTPException

async def get_library_id(
    x_fichero_library_id: Optional[str] = Header(None)
) -> str:
    """Extract library ID from request header."""
    if not x_fichero_library_id:
        raise HTTPException(
            status_code=400,
            detail="Missing X-Fichero-Library-ID header. Please open a library document first."
        )

    # Validate UUID format
    try:
        uuid.UUID(x_fichero_library_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid library ID format: {x_fichero_library_id}"
        )

    return x_fichero_library_id
```

---

### 3. API Routes - Use Library-Specific Connections

**Current Pattern**:
```python
@router.get("/documents")
async def list_documents():
    # Uses global db_manager connection
    results = db_manager.conn.execute("SELECT * FROM documents").fetchall()
    return results
```

**New Pattern**:
```python
@router.get("/documents")
async def list_documents(library_id: str = Depends(get_library_id)):
    # Get library-specific connection
    duckdb_conn, lance_db = db_manager.get_connection(library_id)

    # Use library-specific connection
    results = duckdb_conn.execute("SELECT * FROM documents").fetchall()
    return results
```

**Affected Routes** (ALL routes in these files):
- `src/fichero/api/routes/documents.py` (9 endpoints)
- `src/fichero/api/routes/search.py` (3 endpoints)
- `src/fichero/api/routes/chat.py` (4 endpoints)
- `src/fichero/api/routes/workflows.py` (5 endpoints)
- `src/fichero/api/routes/ingest.py` (2 endpoints)
- `src/fichero/api/routes/storage.py` (3 endpoints)
- `src/fichero/api/routes/collections.py` (6 endpoints)

**Total**: ~32 endpoints need library_id dependency added

---

### 4. Storage Service - Library-Specific Paths

**File**: `src/fichero/storage.py`

**Current**:
```python
def get_storage_path(document_id: str, type: str) -> Path:
    """Get storage path for document asset."""
    base = Path.home() / "Library" / "Application Support" / "Fichero" / "storage"
    return base / type / f"{document_id}.jpg"
```

**New**:
```python
def get_storage_path(library_id: str, document_id: str, type: str) -> Path:
    """Get storage path for document asset in specific library."""
    library_dir = get_library_directory(library_id)
    storage_dir = library_dir / "storage" / type
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir / f"{document_id}.jpg"
```

**Update Callers**:
- `generate_thumbnail()` - add library_id parameter
- `get_display_image()` - add library_id parameter
- `get_source_file()` - add library_id parameter

---

### 5. Ingest Service - Library-Specific File Paths

**File**: `src/fichero/ingest.py`

**Current**:
```python
def copy_file_to_library(source_path: Path, document_id: str) -> Path:
    """Copy file to Fichero storage (COPY mode)."""
    files_dir = Path.home() / "Library" / "Application Support" / "Fichero" / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    dest = files_dir / source_path.name
    # APFS clone copy
    subprocess.run(["cp", "-c", str(source_path), str(dest)])
    return dest
```

**New**:
```python
def copy_file_to_library(library_id: str, source_path: Path, document_id: str) -> Path:
    """Copy file to library-specific storage (COPY mode)."""
    library_dir = get_library_directory(library_id)
    files_dir = library_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    dest = files_dir / source_path.name
    # APFS clone copy
    subprocess.run(["cp", "-c", str(source_path), str(dest)])
    return dest
```

---

### 6. Health Check - Library-Aware Stats

**File**: `src/fichero/api/routes/health.py`

**Current**:
```python
@router.get("/health")
async def health_check():
    """Health check endpoint."""
    count = db_manager.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    return {
        "status": "ok",
        "database": str(db_manager.db_path),
        "document_count": count
    }
```

**New**:
```python
@router.get("/health")
async def health_check(library_id: Optional[str] = Header(None, alias="X-Fichero-Library-ID")):
    """Health check endpoint - optionally library-aware."""
    if library_id:
        # Library-specific health
        duckdb_conn, _ = db_manager.get_connection(library_id)
        count = duckdb_conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        library_dir = get_library_directory(library_id)

        return {
            "status": "ok",
            "library_id": library_id,
            "database": str(library_dir / "fichero.duckdb"),
            "document_count": count
        }
    else:
        # Global health (backend is running)
        return {
            "status": "ok",
            "backend_version": "0.1.0",
            "libraries_active": len(db_manager._connections)
        }
```

---

### 7. New Library Management Endpoints

**File**: `src/fichero/api/routes/libraries.py` (NEW)

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import uuid
from datetime import datetime

router = APIRouter(prefix="/libraries", tags=["libraries"])

class LibraryMetadata(BaseModel):
    library_id: str
    library_name: str
    created_at: datetime
    document_count: int
    storage_size_bytes: int

@router.get("/list")
async def list_libraries() -> List[LibraryMetadata]:
    """List all libraries with metadata."""
    libraries_dir = Path.home() / "Library" / "Application Support" / "Fichero" / "libraries"

    if not libraries_dir.exists():
        return []

    libraries = []
    for library_path in libraries_dir.iterdir():
        if library_path.is_dir():
            library_id = library_path.name

            # Get connection to read metadata
            duckdb_conn, _ = db_manager.get_connection(library_id)

            # Query document count
            count = duckdb_conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

            # Calculate storage size
            storage_size = sum(
                f.stat().st_size
                for f in library_path.rglob("*")
                if f.is_file()
            )

            # Get library name from metadata table (if exists)
            try:
                name_result = duckdb_conn.execute(
                    "SELECT library_name FROM library_metadata LIMIT 1"
                ).fetchone()
                library_name = name_result[0] if name_result else "Untitled Library"
            except:
                library_name = "Untitled Library"

            libraries.append(LibraryMetadata(
                library_id=library_id,
                library_name=library_name,
                created_at=datetime.fromtimestamp(library_path.stat().st_birthtime),
                document_count=count,
                storage_size_bytes=storage_size
            ))

    return libraries

@router.post("/create")
async def create_library(library_name: str = "New Library") -> LibraryMetadata:
    """Create a new library."""
    library_id = str(uuid.uuid4())
    library_dir = get_library_directory(library_id)
    library_dir.mkdir(parents=True, exist_ok=True)

    # Initialize database connections (will create schema)
    duckdb_conn, lance_db = db_manager.get_connection(library_id)

    # Store library metadata
    duckdb_conn.execute("""
        CREATE TABLE IF NOT EXISTS library_metadata (
            library_name TEXT,
            created_at TIMESTAMP
        )
    """)
    duckdb_conn.execute(
        "INSERT INTO library_metadata VALUES (?, ?)",
        [library_name, datetime.now()]
    )

    return LibraryMetadata(
        library_id=library_id,
        library_name=library_name,
        created_at=datetime.now(),
        document_count=0,
        storage_size_bytes=0
    )

@router.delete("/{library_id}")
async def delete_library(library_id: str):
    """Delete a library and all its data."""
    library_dir = get_library_directory(library_id)

    if not library_dir.exists():
        raise HTTPException(status_code=404, detail="Library not found")

    # Close connections first
    db_manager.close_connection(library_id)

    # Delete directory and all contents
    import shutil
    shutil.rmtree(library_dir)

    return {"status": "deleted", "library_id": library_id}
```

**Register Router**:
```python
# src/fichero/api/main.py
from .routes import libraries

app.include_router(libraries.router)
```

---

## Implementation Checklist

### Core Infrastructure
- [ ] Update `db.py` with connection pooling
- [ ] Add `get_library_directory()` helper
- [ ] Add `get_library_id()` FastAPI dependency
- [ ] Add library metadata table to schema

### API Routes (32 endpoints)
- [ ] `documents.py` - 9 endpoints
- [ ] `search.py` - 3 endpoints
- [ ] `chat.py` - 4 endpoints
- [ ] `workflows.py` - 5 endpoints
- [ ] `ingest.py` - 2 endpoints
- [ ] `storage.py` - 3 endpoints
- [ ] `collections.py` - 6 endpoints
- [ ] `health.py` - 1 endpoint (make optional)

### Storage & Files
- [ ] Update `storage.py` functions with library_id
- [ ] Update `ingest.py` COPY mode with library_id
- [ ] Update `loaders/` to use library-specific paths

### New Features
- [ ] Create `libraries.py` router
- [ ] Implement `/libraries/list`
- [ ] Implement `/libraries/create`
- [ ] Implement `/libraries/delete`
- [ ] Add library metadata table

### Testing
- [ ] Test creating new library
- [ ] Test switching between libraries
- [ ] Test concurrent multi-library access
- [ ] Test library deletion
- [ ] Test import to different libraries

---

## Migration Path

### Existing Users (Single Library)

For users with existing data at `~/Library/Application Support/Fichero/`:
1. Backend should detect if `fichero.duckdb` exists in old location
2. On first launch, create a "default" library:
   ```python
   default_library_id = "00000000-0000-0000-0000-000000000000"
   ```
3. Move existing files to library-specific paths:
   ```
   ~/Library/Application Support/Fichero/
   ├── fichero.duckdb  →  libraries/00000000.../fichero.duckdb
   ├── lance/          →  libraries/00000000.../lance/
   ├── storage/        →  libraries/00000000.../storage/
   └── files/          →  libraries/00000000.../files/
   ```
4. Frontend creates a `.fichero` document pointing to this library ID

**Migration Script**: `src/fichero/migrate_to_multi_library.py`

---

## Performance Considerations

### Connection Pooling
- **Problem**: Creating new DuckDB/LanceDB connections is expensive
- **Solution**: Keep connections open in `_connections` dict, reuse across requests
- **Cleanup**: Add `shutdown` handler to close all connections on server shutdown

### Memory Usage
- **Problem**: Multiple open databases consume memory
- **Solution**: Add LRU eviction if > 5 libraries open simultaneously
- **Implementation**: Use `cachetools.LRUCache` wrapper

### Concurrent Access
- **Problem**: Multiple requests to same library must be thread-safe
- **Solution**: DuckDB supports concurrent reads, single writer
- **Lock Strategy**: Use threading.Lock per library for write operations

---

## API Contract Changes

### Breaking Changes
**NONE** - All changes are additive:
- Old behavior: If no library ID header, return 400 error
- New endpoints: `/libraries/*` are new

### Header Requirement
All existing endpoints now **require** `X-Fichero-Library-ID` header:
```
GET /api/documents
X-Fichero-Library-ID: 550e8400-e29b-41d4-a716-446655440000
```

Exception: `/api/health` works with or without library ID

---

## Testing Strategy

### Unit Tests
```python
# tests/unit/test_multi_library.py

def test_get_connection_creates_new_library():
    """Test that get_connection creates directories and schema."""
    db_manager = DatabaseManager()
    library_id = str(uuid.uuid4())

    duckdb_conn, lance_db = db_manager.get_connection(library_id)

    # Verify directory exists
    library_dir = get_library_directory(library_id)
    assert library_dir.exists()
    assert (library_dir / "fichero.duckdb").exists()
    assert (library_dir / "lance").exists()

    # Verify schema initialized
    result = duckdb_conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in result.fetchall()]
    assert "documents" in tables

def test_multiple_libraries_isolated():
    """Test that documents in different libraries don't mix."""
    db_manager = DatabaseManager()
    lib1 = str(uuid.uuid4())
    lib2 = str(uuid.uuid4())

    # Add document to library 1
    conn1, _ = db_manager.get_connection(lib1)
    conn1.execute("INSERT INTO documents (id, title) VALUES (?, ?)", ["doc1", "Library 1 Doc"])

    # Add document to library 2
    conn2, _ = db_manager.get_connection(lib2)
    conn2.execute("INSERT INTO documents (id, title) VALUES (?, ?)", ["doc2", "Library 2 Doc"])

    # Verify isolation
    lib1_docs = conn1.execute("SELECT * FROM documents").fetchall()
    lib2_docs = conn2.execute("SELECT * FROM documents").fetchall()

    assert len(lib1_docs) == 1
    assert len(lib2_docs) == 1
    assert lib1_docs[0][0] == "doc1"
    assert lib2_docs[0][0] == "doc2"
```

### Integration Tests
```python
# tests/integration/test_api_multi_library.py

async def test_documents_api_with_library_header(client: TestClient):
    """Test that documents API respects library ID header."""
    library_id = str(uuid.uuid4())

    # Create document in library
    response = client.post(
        "/api/documents/import",
        headers={"X-Fichero-Library-ID": library_id},
        json={"file_path": "/path/to/file.pdf", "mode": "LINK"}
    )
    assert response.status_code == 200
    doc_id = response.json()["id"]

    # List documents with library header
    response = client.get(
        "/api/documents",
        headers={"X-Fichero-Library-ID": library_id}
    )
    assert response.status_code == 200
    docs = response.json()
    assert len(docs) == 1
    assert docs[0]["id"] == doc_id

async def test_missing_library_header_returns_400(client: TestClient):
    """Test that missing library header returns error."""
    response = client.get("/api/documents")
    assert response.status_code == 400
    assert "X-Fichero-Library-ID" in response.json()["detail"]
```

---

## Timeline Estimate

**Note**: This is a rough estimate for planning purposes only.

- **Core Infrastructure** (db.py, dependencies): 1 day
- **API Route Updates** (32 endpoints): 2 days
- **Storage & Files Updates**: 1 day
- **Library Management Endpoints**: 1 day
- **Migration Script**: 1 day
- **Testing**: 2 days

**Total**: ~8 days of development

---

## Related Documentation

- `PHASE_0.5_TABS_COMPLETE.md` - Frontend DocumentGroup implementation
- `APPKIT_REMOVAL_SUMMARY.md` - SwiftUI migration progress
- `docs/ingest_api.md` - Ingest system (needs library_id updates)
- `ai/contexts/backend/ARCHITECTURE.md` - Backend architecture overview

---

**Created By:** Claude Code
**Last Updated:** 2025-12-30
**Status:** Planning Document - Ready for Implementation
