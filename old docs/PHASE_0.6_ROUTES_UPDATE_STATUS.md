# Phase 0.6: Package Documents - Route Updates Status

**Date:** 2025-12-30
**Status:** ✅ Core Infrastructure Complete | ✅ ALL 6 Route Files Complete | ✅ Routes Update COMPLETE

---

## Completed Files ✅

### 1. main.py - Core Infrastructure ✅
- ✅ DatabaseManager integrated
- ✅ `get_library_database()` dependency created
- ✅ Lifespan updated to close all connections on shutdown
- ✅ Health check supports both general and library-specific modes
- ✅ Stats endpoint uses dependency

### 2. documents.py - ALL 11 endpoints updated ✅
- ✅ Imports changed to `from fichero.db import Database`
- ✅ Dependency imported: `from fichero.api.main import get_library_database`
- ✅ All 11 endpoints have `db: Database = Depends(get_library_database)` parameter

**Endpoints:**
1. ✅ GET / - list_documents
2. ✅ GET /collections - list_collections
3. ✅ GET /roots - list_roots
4. ✅ GET /{doc_id} - get_document
5. ✅ GET /{doc_id}/children - get_children
6. ✅ GET /{doc_id}/ancestors - get_ancestors
7. ✅ POST / - create_document
8. ✅ PUT /{doc_id} - update_document
9. ✅ DELETE /{doc_id} - delete_document
10. ✅ POST /reorder - reorder_documents
11. ✅ POST /import - import_file
12. ✅ PUT /{doc_id}/move - move_document

### 3. search.py - ALL 9 endpoints updated ✅
- ✅ Imports changed to `from fichero.db import Database, SearchResult`
- ✅ Dependency imported
- ✅ All 9 endpoints updated

**Endpoints:**
1. ✅ POST / - enhanced_search
2. ✅ GET /stats - search_stats
3. ✅ POST /reindex - reindex_all
4. ✅ POST /embed/{doc_id} - embed_document
5. ✅ POST /saved - save_search
6. ✅ GET /saved - list_saved_searches
7. ✅ POST /saved/{search_id}/duplicate - duplicate_saved_search
8. ✅ DELETE /saved/{search_id} - delete_saved_search
9. ✅ POST /saved/reorder - reorder_saved_searches

### 4. chat.py - ALL 3 endpoints updated ✅
- ✅ Imports changed to `from fichero.db import Database`
- ✅ Dependency imported: `from fichero.api.main import get_library_database`
- ✅ All 3 database-using endpoints have `db: Database = Depends(get_library_database)` parameter
- ✅ Helper function `_get_langchain_llm` updated to accept db parameter

**Endpoints:**
1. ✅ POST / - chat
2. ✅ GET /providers - list_providers
3. ✅ POST /extract-text - extract_text

### 5. workflows.py - ALL 10 endpoints updated ✅
- ✅ Imports changed to `from fichero.db import Database`
- ✅ Dependency imported: `from fichero.api.main import get_library_database`
- ✅ All inline `from fichero.db import db` imports removed
- ✅ All 10 endpoints updated

**Endpoints:**
1. ✅ POST / - create_workflow
2. ✅ POST /import - import_workflow
3. ✅ GET /{workflow_id}/export - export_workflow
4. ✅ GET / - list_workflows
5. ✅ GET /{workflow_id} - get_workflow
6. ✅ PUT /{workflow_id} - update_workflow
7. ✅ DELETE /{workflow_id} - delete_workflow
8. ✅ POST /{workflow_id}/duplicate - duplicate_workflow
9. ✅ POST /reorder - reorder_workflows
10. ✅ POST /{workflow_id}/run - run_saved_workflow

### 6. storage.py - ALL 4 endpoints updated ✅
- ✅ Imports changed to `from fichero.db import Database`
- ✅ Dependency imported: `from fichero.api.main import get_library_database`
- ✅ Added `Header` import for package path extraction
- ✅ All endpoints have both db dependency AND `x_fichero_library_path` header parameter
- ✅ Package path extracted in each endpoint for future storage updates

**Endpoints:**
1. ✅ GET /thumbnail/{doc_id} - get_thumbnail
2. ✅ GET /display/{doc_id} - get_display_image
3. ✅ GET /source/{doc_id} - get_source_file
4. ✅ GET /stats - storage_stats

### 7. providers.py - ALL 8 endpoints updated ✅
- ✅ Imports changed to `from fichero.db import Database`
- ✅ Dependency imported: `from fichero.api.main import get_library_database`
- ✅ All 8 database-using endpoints updated

**Endpoints:**
1. ✅ GET / - list_providers
2. ✅ POST / - create_provider
3. ✅ GET /{provider_id} - get_provider
4. ✅ PATCH /{provider_id} - update_provider
5. ✅ DELETE /{provider_id} - delete_provider
6. ✅ GET /{provider_id}/models - list_provider_models
7. ✅ POST /{provider_id}/models - add_model_to_provider
8. ✅ DELETE /{provider_id}/models/{model_id} - remove_model_from_provider

---

## Summary

**All backend route files have been successfully updated for package document support!**

### Files Updated (7 total)
1. ✅ main.py - Core infrastructure (DatabaseManager, get_library_database dependency, lifespan)
2. ✅ documents.py - 12 endpoints
3. ✅ search.py - 9 endpoints
4. ✅ chat.py - 3 endpoints (plus helper function)
5. ✅ workflows.py - 10 endpoints
6. ✅ storage.py - 4 endpoints (with package path extraction)
7. ✅ providers.py - 8 endpoints

### Total Endpoints Updated: 46

### Changes Made
- Updated imports from `from fichero.db import db` to `from fichero.db import Database`
- Added `from fichero.api.main import get_library_database` dependency import
- Added `Depends` to FastAPI imports where needed
- Added `db: Database = Depends(get_library_database)` parameter to all database-using endpoints
- Removed all inline `from fichero.db import db` imports
- storage.py also extracts `X-Fichero-Library-Path` header for future storage path updates

### Next Step
Update backend tests to use package document pattern.

---

## Update Pattern Reference (for future use)

For each remaining file:

### Step 1: Update imports at top of file
```python
# Remove this:
from fichero.db import db

# Add these:
from fichero.db import Database
from fichero.api.main import get_library_database
from fastapi import Depends  # Add to existing FastAPI import if needed
```

### Step 2: Add dependency to router definition area
```python
router = APIRouter()


# Import the get_library_database dependency
from fichero.api.main import get_library_database
```

### Step 3: Add dependency parameter to EACH endpoint
```python
# BEFORE:
@router.get("/some/path")
async def my_endpoint(param1: str, param2: int) -> ReturnType:
    result = db.query(SomeModel)  # uses global db
    return result

# AFTER:
@router.get("/some/path")
async def my_endpoint(
    param1: str,
    param2: int,
    db: Database = Depends(get_library_database),  # ← ADD THIS
) -> ReturnType:
    result = db.query(SomeModel)  # now uses library-specific db
    return result
```

**That's it!** The function body doesn't change - just add the parameter.

---

## Special Case: storage.py

For storage.py, also need to extract package path from header and use it for file paths:

```python
from fastapi import Header

@router.get("/thumbnail/{document_id}")
async def get_thumbnail(
    document_id: str,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
):
    from pathlib import Path
    from fastapi.responses import FileResponse

    package_path = Path(x_fichero_library_path)
    thumbnail_path = package_path / "storage" / "thumbnails" / f"{document_id}.jpg"

    if not thumbnail_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    return FileResponse(thumbnail_path)
```

Do the same for `get_display()` and `get_source()`.

---

## Testing Checklist

After updating all routes, test with:

```bash
# Start backend
cd /Users/dtubb/code/fichero_main/fichero
PYTHONPATH=src .venv/bin/uvicorn fichero.api.main:app --port 8765

# Test health check (no library)
curl http://127.0.0.1:8765/api/health

# Should return:
{
  "status": "healthy",
  "backend_version": "0.1.0",
  "active_libraries": 0
}

# Test with library path (create a test package first)
mkdir -p /tmp/TestLibrary.fichero/{lance,storage,files}

# Test health check with library
curl -H "X-Fichero-Library-Path: /tmp/TestLibrary.fichero" \
     http://127.0.0.1:8765/api/health

# Should return:
{
  "status": "healthy",
  "library_path": "/tmp/TestLibrary.fichero",
  "database": "/tmp/TestLibrary.fichero/fichero.duckdb",
  "document_count": 0
}

# Test documents endpoint
curl -H "X-Fichero-Library-Path: /tmp/TestLibrary.fichero" \
     http://127.0.0.1:8765/api/documents

# Should return: []
```

---

## Files Summary

| File | Status | Endpoints | Notes |
|------|--------|-----------|-------|
| main.py | ✅ Complete | 2 | Core infrastructure done |
| documents.py | ✅ Complete | 12 | All endpoints updated |
| search.py | ✅ Complete | 9 | All endpoints updated |
| chat.py | ⏳ TODO | ~5 | Standard pattern |
| workflows.py | ⏳ TODO | ~6 | Standard pattern |
| storage.py | ⏳ TODO | 3 | Needs package paths |
| providers.py | ❓ Check | ? | May not need updates |
| models.py | ✅ Skip | 0 | No DB access |
| ingest.py | ❓ Check | ? | Needs verification |

---

## Backend Tests Updates ⏳

Once routes are updated, tests need updating too:

**Test files to update:**
- `tests/unit/test_api.py` - Update to use package paths
- `tests/integration/test_*` - Update to create test packages
- Any tests that use the global `db` instance

**Test pattern:**
```python
# OLD
from fichero.db import db

def test_something():
    doc = Document(name="test")
    db.save(doc)
    assert db.get(Document, doc.id) is not None

# NEW
from fichero.db import db_manager

def test_something(tmp_path):
    # Create test package
    package_path = tmp_path / "test.fichero"
    package_path.mkdir()
    (package_path / "lance").mkdir()
    (package_path / "storage").mkdir()
    (package_path / "files").mkdir()

    # Get database for test package
    db = db_manager.get_database(package_path)

    # Test as before
    doc = Document(name="test")
    db.save(doc)
    assert db.get(Document, doc.id) is not None
```

---

## Related Documentation

- **Implementation Guide**: `PHASE_0.6_PACKAGE_DOCUMENTS_COMPLETE.md`
- **Frontend Summary**: `PHASE_0.6_FRONTEND_COMPLETE.md`
- **Original Plan**: `PHASE_0.6_BACKEND_PLAN.md`

---

**Created By:** Claude Code
**Last Updated:** 2025-12-30
**Next Step:** Update remaining 4 route files (chat.py, workflows.py, storage.py, providers.py) + tests
