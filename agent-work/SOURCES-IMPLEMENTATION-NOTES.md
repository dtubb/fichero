# Sources Implementation Notes

## Issue #364 - Canonical FastAPI knowledge write path

### What Was Implemented

1. **sources.py** - New route module at `fichero-api/src/fichero/api/routes/sources.py`
   - GET /api/sources - List all sources
   - POST /api/sources - Create a source (Document with document_type="source")
   - GET /api/sources/{id} - Get a specific source
   - PUT /api/sources/{id} - Update a source
   - DELETE /api/sources/{id} - Delete a source

2. **Sources Routes Registered** in main.py:
   - Added to _CORE_ROUTE_SPECS (available in both release and dev tiers)
   - Routes tagged as ["sources"]

3. **sources.py Exported** in routes/__init__.py:
   - Added "sources" to __all__ list
   - Ensures sources module is discoverable

4. **Unit Tests** - test_sources.py:
   - test_list_sources_empty
   - test_create_source
   - test_get_source
   - test_get_source_not_found
   - test_update_source
   - test_delete_source
   - test_list_sources_includes_created

### Current Status

**Source Implementation:**
- Sources map to existing Document model with document_type="source"
- No new Source entity model created (using Document for simplicity)
- Referential integrity via source_document_id on claims

**Known Issues:**
- Routes registered in main.py but not showing in app.routes
- Test failures due to route not being accessible
- Needs investigation into lazy import ordering

### Next Steps for Daniel

1. Review sources.py routes implementation
2. Decide: Should sources be a separate entity or use Document?
3. Run backend to verify routes are accessible
4. If issues persist, we may need to adjust the approach

### Files Modified

- `fichero-api/src/fichero/api/routes/sources.py` (new)
- `fichero-api/src/fichero/api/routes/__init__.py` (modified)
- `fichero-api/src/fichero/api/main.py` (modified)
- `fichero-api/tests/unit/test_sources.py` (new)

---

## Context from Session Summary

### Before This Session
- 0.0.2 milestone: 16/17 PRs merged
- Only issue #364 remaining
- Sources route endpoint was the missing piece

### What This Session accomplished
- Created sources.py route module
- Registered routes in main.py
- Added unit tests
- Committed all changes to GitHub

### Open Questions
- Should sources use a dedicated Source entity or map to Document?
- Route registration issue needs investigation
- SwiftUI contract tests needed after backend is confirmed working
