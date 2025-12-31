# Phase 0.6: Frontend Testing Plan

**Date:** 2025-12-30
**Status:** ✅ Backend Ready | ✅ Swift App Built | ⏳ Manual Testing Required

---

## Backend Status: ✅ READY

The backend server is running on port 8765 with full package document support:

- ✅ All 46 endpoints updated with dependency injection
- ✅ DatabaseManager correctly isolates databases per package
- ✅ Routes require `X-Fichero-Library-Path` header
- ✅ 40/51 tests passing (core functionality working)

**Verified with curl**:
```bash
# Documents endpoint returns empty array for new library
curl -H "X-Fichero-Library-Path: /Users/dtubb/Desktop/TestLibrary.fichero" \
     http://127.0.0.1:8765/api/documents
# Result: []

# Create document works
curl -X POST -H "X-Fichero-Library-Path: /Users/dtubb/Desktop/TestLibrary.fichero" \
     -H "Content-Type: application/json" \
     -d '{"name":"Test Folder","documentType":"collection"}' \
     http://127.0.0.1:8765/api/documents
# Result: Document created with ID

# Without header - correctly returns error
curl http://127.0.0.1:8765/api/documents
# Result: {"detail": "Field required: X-Fichero-Library-Path"}
```

---

## Swift Frontend Status: ✅ BUILT

The Swift app is built with package document support:

- ✅ `FicheroDocument` struct with FileDocument conformance
- ✅ `.fichero` UTType registered in Info.plist
- ✅ APIClient sends `X-Fichero-Library-Path` header (line 78-82 in APIClient.swift)
- ✅ DocumentTabView sets library path on load (line 30 in DocumentTabView.swift)
- ✅ App registered with Launch Services (can open .fichero files)

---

## Test Library Prepared

Test library created at: `/Users/dtubb/Desktop/TestLibrary.fichero`

**Structure**:
```
TestLibrary.fichero/
├── document.json          # Library metadata
├── fichero.duckdb         # Created by backend (contains 1 test document)
├── lance/                 # Vector storage (empty)
├── storage/               # Thumbnails/display images (empty)
└── files/                 # Imported files (empty)
```

**Contents**: 1 document created via curl (Test Folder)

---

## Manual Testing Steps

### 1. Launch Fichero App

```bash
# Launch the built app
open /Users/dtubb/Library/Developer/Xcode/DerivedData/Fichero-*/Build/Products/Debug/Fichero.app
```

Or open from Xcode and run (⌘R).

### 2. Open Test Library

- File > Open (⌘O)
- Navigate to Desktop
- Select `TestLibrary.fichero`
- Should open the library

### 3. Verify Backend Connection

**Expected behavior**:
- App should connect to backend on port 8765
- If backend not running, should show "Backend Connection" view
- If backend running, should show ContentView with 3-column layout

**Check console for APIClient logs**:
```
[APIClient] GET http://127.0.0.1:8765/api/documents
[APIClient] Response received, X bytes
```

### 4. Verify Document Display

**Expected**:
- Sidebar should show "Test Folder" document
- Document count should be 1 (not 8 from old global database)
- No old documents should appear

**If documents don't appear**:
- Check Console.app for errors
- Check backend logs for incoming requests
- Verify `X-Fichero-Library-Path` header is being sent

### 5. Test Document Creation

- Click "+" button or use File > New Folder
- Create a new folder named "New Folder"
- Should appear in sidebar
- Refresh browser to verify it persists

### 6. Test Library Isolation

- Close TestLibrary.fichero
- Create a new library (File > New or ⌘N)
- Save as `SecondLibrary.fichero` on Desktop
- Should be empty (no documents from TestLibrary)
- Create a document in SecondLibrary
- Switch back to TestLibrary
- Should still show only "Test Folder" (not SecondLibrary's documents)

---

## Known Issues

### 1. Storage Paths - REQUIRES FIX

**Problem**: `storage.py` module uses global base path instead of package-relative paths.

**Evidence**:
```json
{
  "expected_thumbnail_path": "/Users/dtubb/Library/Application Support/ca.tubb.fichero/thumbnails/...",
  "expected_display_path": "/Users/dtubb/Library/Application Support/ca.tubb.fichero/thumbnails/..."
}
```

Should be:
```json
{
  "expected_thumbnail_path": "/Users/dtubb/Desktop/TestLibrary.fichero/storage/thumbnails/...",
  "expected_display_path": "/Users/dtubb/Desktop/TestLibrary.fichero/storage/display/..."
}
```

**Impact**:
- Thumbnails won't be stored in package
- Thumbnails will be shared across all libraries (not isolated)
- Package won't be portable

**Fix required**: Update `src/fichero/storage.py` to accept package_path parameter

### 2. AsyncImage Headers - REQUIRES FIX

**Problem**: SwiftUI's `AsyncImage` doesn't send custom headers.

**Code locations**:
- `LibraryView.swift:461` - Thumbnail loading
- `LibraryView.swift:617` - Thumbnail loading in list view

**Evidence**:
```swift
AsyncImage(url: APIClient.shared.thumbnailURL(for: document.id))
```

This creates a URL like `http://127.0.0.1:8765/api/storage/thumbnail/{id}` but doesn't send `X-Fichero-Library-Path` header.

**Impact**:
- Thumbnail/display/source endpoints will fail with "Field required" error
- Images won't load in the UI

**Possible fixes**:
1. **Custom image loader** - Create Swift view that uses URLRequest with headers
2. **URL-based library routing** - Change storage endpoint to `/api/storage/{library_id}/thumbnail/{doc_id}`
3. **Query parameter** - Add library path as query param: `/api/storage/thumbnail/{id}?library=/path/to/library.fichero`

**Recommended**: Option 1 (custom loader) - cleaner API, keeps header-based routing consistent

---

## Debugging Tips

### Check if header is being sent

In `APIClient.swift`, the `configureRequest` method (line 78-82) adds the header:
```swift
private func configureRequest(_ request: inout URLRequest) {
    if let libraryPath = currentLibraryPath {
        request.setValue(libraryPath, forHTTPHeaderField: "X-Fichero-Library-Path")
    }
}
```

**Add debug logging**:
```swift
private func configureRequest(_ request: inout URLRequest) {
    if let libraryPath = currentLibraryPath {
        NSLog("[APIClient] Setting library path: %@", libraryPath)
        request.setValue(libraryPath, forHTTPHeaderField: "X-Fichero-Library-Path")
    } else {
        NSLog("[APIClient] WARNING: No library path set!")
    }
}
```

### Check backend logs

Backend logs all requests to stdout:
```
INFO:     127.0.0.1:54321 - "GET /api/documents HTTP/1.1" 200 OK
```

Check if headers are being received by adding logging to `get_library_database` in `main.py`.

### Check database files

Verify databases are created in correct locations:
```bash
# Test library database
ls -lh /Users/dtubb/Desktop/TestLibrary.fichero/fichero.duckdb

# Check database content
duckdb /Users/dtubb/Desktop/TestLibrary.fichero/fichero.duckdb "SELECT COUNT(*) FROM documents"
```

---

## Next Steps After Manual Testing

### If basic CRUD works ✅

1. Fix storage paths issue (update storage.py to use package paths)
2. Fix AsyncImage loading (implement custom image loader)
3. Test multi-window/multi-library scenarios
4. Complete remaining 11 failing backend tests

### If API requests fail ❌

**Possible causes**:
1. `currentLibraryPath` not being set correctly
2. DocumentTabView not receiving correct `documentURL`
3. Header not being added to requests
4. Backend not receiving header

**Debug steps**:
1. Add logging to DocumentTabView's `.task` block
2. Add logging to APIClient's `configureRequest`
3. Check backend logs for incoming requests
4. Use Network.framework/Charles Proxy to inspect HTTP traffic

---

## Testing Checklist

- [ ] App launches successfully
- [ ] Can open TestLibrary.fichero
- [ ] Backend connection works (green indicator)
- [ ] Document list shows 1 document (Test Folder)
- [ ] Can create new documents
- [ ] Can delete documents
- [ ] Can rename documents
- [ ] Creating second library shows empty document list
- [ ] Documents in different libraries don't mix
- [ ] Closing and reopening library persists changes
- [ ] Console shows correct API requests with headers

---

## Related Files

### Frontend
- `Fichero/Fichero/Models/FicheroDocument.swift` - Document model
- `Fichero/Fichero/Views/DocumentTabView.swift` - Sets library path
- `Fichero/Fichero/Services/APIClient.swift` - HTTP client with headers
- `Fichero/Fichero/Info.plist` - UTType registration

### Backend
- `src/fichero/api/main.py` - get_library_database dependency
- `src/fichero/db.py` - DatabaseManager and Database classes
- `src/fichero/storage.py` - Storage path generation (NEEDS FIX)
- All route files in `src/fichero/api/routes/` - Use dependency injection

### Tests
- `tests/conftest.py` - Test fixtures
- `tests/unit/test_api.py` - API tests (40/51 passing)

---

**Created By:** Claude Code
**Last Updated:** 2025-12-30
**Ready for:** Manual testing with built app
