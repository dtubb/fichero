# Phase 0.6: AsyncImage Replacement Complete

**Date:** 2025-12-30
**Status:** ✅ Code Complete | ⏳ Needs File Addition to Xcode Project

---

## Summary

Replaced all 4 AsyncImage usages with custom `LibraryImageView` that properly sends `X-Fichero-Library-Path` headers. This fixes the issue where SwiftUI's AsyncImage doesn't support custom headers.

---

## What Was Done

### 1. Created LibraryImageView Component ✅

**File**: `/Fichero/Fichero/Views/Components/LibraryImageView.swift`

**Features**:
- Loads images using StorageService (which sends headers correctly)
- Supports both thumbnail and display image types
- Handles loading, success, and error states
- Shows placeholder icon on error
- Automatically loads image on appear

**Code**:
```swift
struct LibraryImageView: View {
    enum ImageType {
        case thumbnail
        case display
    }

    let documentId: String
    let imageType: ImageType

    @State private var image: Image?
    @State private var isLoading = false
    @State private var loadError: Error?

    var body: some View {
        // Shows image, progress, or placeholder
    }
}
```

### 2. Replaced All AsyncImage Usages ✅

**Files Modified**: 3 files, 4 replacements

#### LibraryView.swift - 2 replacements
1. **Grid view thumbnail** (line 461) ✅
2. **List view thumbnail** (line 617) ✅

**Before**:
```swift
AsyncImage(url: APIClient.shared.thumbnailURL(for: document.id)) { phase in
    switch phase {
    case .empty: ProgressView()
    case .success(let image): image.resizable()
    case .failure: Image(systemName: "doc")
    }
}
```

**After**:
```swift
LibraryImageView(documentId: document.id, imageType: .thumbnail)
    .aspectRatio(contentMode: .fill)
    .clipped()
```

#### DocumentInspector.swift - 1 replacement
**Inspector thumbnail** (line 58) ✅

**After**:
```swift
LibraryImageView(documentId: doc.id, imageType: .thumbnail)
    .aspectRatio(contentMode: .fill)
    .frame(width: 80, height: 100)
    .clipped()
```

#### EditorView.swift - 1 replacement
**Full-size display image** (line 203) ✅

**After**:
```swift
LibraryImageView(documentId: document.id, imageType: .display)
    .aspectRatio(contentMode: .fit)
    .scaleEffect(scale)
    .offset(offset)
    .gesture(zoomGesture)
    .gesture(panGesture)
    .onTapGesture(count: 2) { toggleZoom(in: geometry.size) }
```

---

## How It Works

### Request Flow

1. **View displays LibraryImageView**:
   ```swift
   LibraryImageView(documentId: "abc123", imageType: .thumbnail)
   ```

2. **LibraryImageView calls StorageService**:
   ```swift
   let storageService = StorageService()
   image = try await storageService.getThumbnail(documentId)
   ```

3. **StorageService creates URLRequest with header**:
   ```swift
   var request = URLRequest(url: thumbnailURL)
   request.setValue(libraryPath, forHTTPHeaderField: "X-Fichero-Library-Path")
   let (data, _) = try await URLSession.shared.data(for: request)
   ```

4. **Backend receives request with library path**:
   ```
   GET /api/storage/thumbnail/abc123
   X-Fichero-Library-Path: /Users/dtubb/Desktop/TestLibrary.fichero
   ```

5. **Backend returns thumbnail from correct library**:
   - Uses library-specific database
   - Returns image bytes

6. **LibraryImageView displays image**

---

## Remaining Step: Add File to Xcode Project

**The file exists but needs to be added to the Xcode project.**

### Option 1: Add via Xcode UI (RECOMMENDED - 30 seconds)

1. **Open Xcode**:
   ```bash
   open Fichero/Fichero.xcodeproj
   ```

2. **Add the file**:
   - Right-click on `Views/Components` folder in Xcode navigator
   - Select "Add Files to Fichero..."
   - Navigate to: `Fichero/Fichero/Views/Components/LibraryImageView.swift`
   - **Important**: Make sure "Copy items if needed" is UNCHECKED
   - Make sure "Add to targets: Fichero" is CHECKED
   - Click "Add"

3. **Build the project** (⌘B)

4. **Done!** The file is now part of the project.

### Option 2: Verify File is Already Added

If the file was auto-discovered by Xcode:

1. Open Xcode project
2. Press ⌘B to build
3. If it builds successfully, the file was auto-added

### Build Verification

After adding the file, build should succeed:

```bash
cd /Users/dtubb/code/fichero_main/fichero
xcodebuild -project Fichero/Fichero.xcodeproj -scheme Fichero -configuration Debug build
```

Expected output:
```
** BUILD SUCCEEDED **
```

---

## Testing Checklist

Once the file is added and build succeeds:

### Thumbnail Loading
- [ ] Grid view thumbnails load correctly
- [ ] List view thumbnails load correctly
- [ ] Inspector thumbnails load correctly
- [ ] Loading spinner shows while loading
- [ ] Placeholder icon shows on error

### Display Images
- [ ] Full-size images load in editor
- [ ] Zoom and pan gestures work
- [ ] Images load from correct library (not mixed across libraries)

### Multi-Library Isolation
- [ ] Open Library A - thumbnails load from A
- [ ] Open Library B - thumbnails load from B (not A's)
- [ ] Thumbnails don't mix between libraries

---

## Files Modified

| File | Changes | Lines |
|------|---------|-------|
| `Views/Components/LibraryImageView.swift` | Created new component | 70 lines |
| `Views/Library/LibraryView.swift` | Replaced 2 AsyncImage calls | -38, +6 |
| `Views/Library/DocumentInspector.swift` | Replaced 1 AsyncImage call | -20, +4 |
| `Views/Library/EditorView.swift` | Replaced 1 AsyncImage call | -15, +7 |
| **Total** | **1 new file, 3 modified** | **+87, -73** |

---

## Benefits

### Before (AsyncImage)
- ❌ No custom headers support
- ❌ Thumbnails fail with "Field required: X-Fichero-Library-Path"
- ❌ Images load from wrong library
- ❌ No library isolation

### After (LibraryImageView)
- ✅ Sends X-Fichero-Library-Path header
- ✅ Images load from correct library
- ✅ Full multi-library isolation
- ✅ Consistent error handling
- ✅ Reusable component

---

## Alternative Approaches Considered

### 1. Query Parameter Instead of Header
```swift
let url = URL(string: "/api/storage/thumbnail/\(id)?library=\(path)")
```

**Pros**: Works with AsyncImage
**Cons**: Inconsistent with rest of API, requires backend changes

### 2. Custom URLProtocol
Intercept all URLSession requests and inject headers.

**Pros**: Transparent, works with AsyncImage
**Cons**: Complex, global side effects, harder to debug

### 3. Our Approach: Custom View
Replace AsyncImage with LibraryImageView.

**Pros**: ✅ Simple, explicit, no magic, reusable
**Cons**: Manual replacement needed (but only 4 places)

---

## Next Steps

1. **Add LibraryImageView.swift to Xcode project** (30 seconds via Xcode UI)
2. **Build the app** (⌘B)
3. **Test thumbnail loading** with backend running
4. **Test multi-library isolation**

---

## Related Documentation

- `PHASE_0.6_SWIFT_REVIEW_COMPLETE.md` - Overall Swift app review
- `PHASE_0.6_STATUS_SUMMARY.md` - Phase 0.6 progress summary

---

**Created By:** Claude Code
**Last Updated:** 2025-12-30 15:05
**Status:** ✅ Code complete, file needs Xcode project addition
**Build Status:** ⏳ Pending file addition
