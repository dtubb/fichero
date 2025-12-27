# TODO-052: UI Refresh Fix - 2025-12-27

## Issue Found During Testing
User reported: "Does not update in UI, and not sure if backend also updates"

After rename TextField accepted input and submitted, the sidebar didn't show the new name.

## Root Cause
The `performRename` function called the backend API successfully but didn't refresh the UI state. It was missing the `documentStore.refresh()` call that the delete function uses.

## Solution
Added UI refresh after successful rename:

```swift
private func performRename(itemId: String, newName: String) async {
    // ... existing code ...

    do {
        let documentService = DocumentService()
        _ = try await documentService.renameDocument(actualId, newName: newName)
        NSLog("[SidebarItemRow] Renamed item \(actualId) to '\(newName)'")

        // Refresh UI if documentStore is available
        if let store = documentStore {
            await store.refresh()
        }
    } catch {
        NSLog("[SidebarItemRow] Failed to rename item: \(error.localizedDescription)")
    }
}
```

## Pattern Used
Follows the same pattern as `performDelete` in SidebarItemContextMenu (lines 721-751), which uses `documentStore` to ensure UI updates.

## Testing
- SwiftLint: PASSED (5 pre-existing warnings)
- Xcode Build: SUCCEEDED
- Change: 3 lines added (lines 631-634 in SidebarView.swift)

## Files Modified
- `Fichero/Fichero/Views/Sidebar/SidebarView.swift` - Added documentStore.refresh() call

## Status
Ready for retest. UI should now update immediately after rename.
