# Drag & Drop Test Plan

## What We Fixed

1. **Drag & drop now uses the same pattern as rename/delete** ✅
   - Uses `documentStore` instance (not creating new `DocumentService`)
   - No `refresh()` call that reloads everything
   - Updates `@Published` properties in-place
   - SwiftUI maintains state via stable IDs

2. **DocumentStore loads full tree** ✅
   - Changed from loading only root items to ALL documents
   - Allows `SidebarItemBuilder` to construct full hierarchy from `parent_id`
   - Children now appear correctly in sidebar

3. **Consistent state management** ✅
   - All operations (rename, delete, move) follow the same pattern
   - No more losing expanded state or selection

## Test Cases

### Test 1: Basic Drag Into Folder
1. Launch app (backend must be running on port 8765)
2. Create 3 folders at root: "Folder A", "Folder B", "Folder C"
3. Drag "Folder C" into "Folder A"
4. **Expected:**
   - ✅ "Folder C" disappears from root
   - ✅ "Folder A" and "Folder B" stay visible at root
   - ✅ Expand "Folder A" → see "Folder C" inside
   - ✅ Selection stays on same item (or moves intelligently)

### Test 2: Expanded State Preserved
1. Create nested structure: A → B → C → D
2. Expand all folders so you can see A > B > C > D
3. Create "New Item" at root
4. Drag "New Item" into "Folder D"
5. **Expected:**
   - ✅ "New Item" disappears from root
   - ✅ All folders (A, B, C, D) stay expanded
   - ✅ "New Item" appears inside "Folder D"

### Test 3: Drag Out of Folder Back to Root
1. Create "Root Folder"
2. Create "Child Item" inside "Root Folder"
3. Drag "Child Item" out of "Root Folder" to the root level
4. **Expected:**
   - ✅ "Child Item" appears at root
   - ✅ "Root Folder" stays visible
   - ✅ "Root Folder" is now empty when expanded

### Test 4: Rename During Drag Operation
1. Create "Folder X" and "Folder Y"
2. Start dragging "Folder Y" (don't drop yet if possible)
3. Press CMD+R to rename "Folder X" to "Folder Z"
4. Complete the drag of "Folder Y" into "Folder Z"
5. **Expected:**
   - ✅ Rename works
   - ✅ Drag completes successfully
   - ✅ No crashes or state loss

### Test 5: Delete After Drag
1. Create "Container" and "Item A", "Item B"
2. Drag "Item A" into "Container"
3. Select "Container"
4. Press CMD+Backspace to delete "Container"
5. **Expected:**
   - ✅ Delete confirmation appears
   - ✅ "Container" and "Item A" are both deleted
   - ✅ "Item B" remains visible
   - ✅ Selection moves to "Item B" or nil

## How to Run Tests

```bash
# 1. Start backend
cd /Users/dtubb/code/fichero_main/fichero
PYTHONPATH=src .venv/bin/uvicorn fichero.api.main:app --port 8765

# 2. Launch app from Xcode or:
open /Users/dtubb/Library/Developer/Xcode/DerivedData/Fichero-aybnjpnpxtkwnsdnrdqxyvaengwh/Build/Products/Debug/Fichero.app

# 3. Watch console logs for verification:
# - Look for "[DocumentStore] Loading all documents for tree building..."
# - Should see "[SidebarView] ✅ Move successful - UI updates automatically via @Published"
# - Should NOT see "[SidebarView] Calling documentStore.refresh()"
```

## Success Criteria

- ✅ Drag & drop moves items correctly
- ✅ UI doesn't "flash" or reload during drag
- ✅ Expanded folders stay expanded
- ✅ Selection is maintained or moves intelligently
- ✅ Children appear in parent folders after drag
- ✅ No console errors
- ✅ Consistent with rename/delete behavior

## Implementation Summary

### Before (Broken Pattern)
```swift
// Created new service instance
let documentService = DocumentService()
let result = try await documentService.moveDocument(...)

// Reloaded EVERYTHING, losing all UI state
await documentStore.refresh()
```

### After (Correct Pattern - Same as Rename/Delete)
```swift
// Uses existing documentStore (@ObservedObject)
let result = try await documentStore.moveDocument(...)

// No refresh needed - @Published properties update automatically
// SwiftUI rebuilds UI while maintaining state via stable IDs
```

### Key Changes Made
1. `SidebarItemRow.moveItemToFolder()` - Now uses `documentStore` instead of creating `DocumentService`
2. `DocumentStore.moveDocument()` - Updates state in-place via `updateLocal()`
3. `DocumentStore.loadCollections()` - Loads ALL documents (not just roots) for tree building
