# Add New Services to Xcode Project

**Files Created:**
1. `Fichero/Services/DocumentService.swift` - Document CRUD operations
2. `Fichero/Services/StorageService.swift` - Thumbnails, previews, storage stats

**Status:** Files exist on disk but not in Xcode project

## Steps to Add Files in Xcode

1. Open `Fichero.xcodeproj` in Xcode
2. In Project Navigator, navigate to `Fichero` → `Services`
3. Right-click on the `Services` folder
4. Select "Add Files to 'Fichero'..."
5. Navigate to `Fichero/Services/`
6. Select **both** files:
   - `DocumentService.swift`
   - `StorageService.swift`
7. Make sure:
   - "Copy items if needed" is **UNCHECKED** (files already in correct location)
   - "Add to targets" has **Fichero** checked
8. Click "Add"
9. Build (⌘B) to verify

## What These Services Provide

### DocumentService.swift
**Documents API Coverage:**
- ✅ `POST /documents` - Create document/collection
- ✅ `GET /documents/{id}` - Get document
- ✅ `GET /documents/{id}/children` - Get children
- ✅ `GET /documents/{id}/ancestors` - Get ancestors (for breadcrumbs!)
- ✅ `GET /documents/roots` - Get root documents
- ✅ `GET /documents/collections` - Get all collections
- ✅ `PUT /documents/{id}` - Update document
- ✅ `PUT /documents/{id}/move` - Move document
- ✅ `POST /documents/reorder` - Reorder documents
- ✅ `DELETE /documents/{id}` - Delete document

**Features:**
- Create new collections from UI
- Rename documents
- Move documents between collections
- Delete documents
- Breadcrumb navigation support
- Drag-and-drop reordering

### StorageService.swift
**Storage API Coverage:**
- ✅ `GET /storage/thumbnail/{doc_id}` - Get thumbnail
- ✅ `GET /storage/display/{doc_id}` - Get display image
- ✅ `GET /storage/source/{doc_id}` - Get original file
- ✅ `GET /storage/stats` - Get storage statistics

**Features:**
- Document thumbnails in library view
- Full-resolution previews
- Download original files
- Storage usage statistics
- URL providers for AsyncImage

## Usage Example

```swift
// In a view
@StateObject private var documentService = DocumentService()
@StateObject private var storageService = StorageService()

// Create a collection
let collection = try await documentService.createCollection(
    name: "New Folder",
    parentId: nil  // Root level
)

// Load thumbnail
AsyncImage(url: storageService.thumbnailURL(for: document.id)) { image in
    image.resizable().aspectRatio(contentMode: .fit)
} placeholder: {
    ProgressView()
}

// Get storage stats
let stats = try await storageService.getStats()
print("Total storage: \(stats.formattedSize)")
```

## After Adding

Run build to verify:
```bash
cd /Users/dtubb/code/fichero_main/fichero/Fichero
xcodebuild -project Fichero.xcodeproj -scheme Fichero -configuration Debug build
```

Should build successfully with no errors.

## Backend API Coverage Improvement

Before:
- Documents API: **18%** coverage (1/11 endpoints)
- Storage API: **0%** coverage (0/4 endpoints)

After:
- Documents API: **91%** coverage (10/11 endpoints)
- Storage API: **100%** coverage (4/4 endpoints)
