# TODO-024 Implementation Notes

## Analysis Findings

### Issue 1: Layout Recursion Warnings
The layout recursion warning "It's not legal to call -layoutSubtreeIfNeeded on a view which is already being laid out" typically occurs in SwiftUI when there are layout conflicts or when views are trying to update their layout during an existing layout pass.

### Issue 2: UI Not Updating After Import
The UI doesn't refresh after successful import because the state management in the DocumentStore and SidebarView doesn't properly trigger UI updates.

### Root Cause Analysis

1. **Import Flow**:
   - User drops file on Library section or sidebar item
   - `handleFileDropOnLibrary` or `handleDroppedFile` is called in SidebarView
   - These call `documentStore.importFile(at:parentId:)`
   - DocumentStore calls `service.importFile(at:parentId:)`
   - DocumentService makes HTTP POST to `/api/documents/import`
   - On success, DocumentStore updates local state and publishes changes

2. **State Management Issues**:
   - The DocumentStore properly publishes changes via `documentChangePublisher`
   - However, the SidebarView doesn't properly react to these changes
   - The `libraryItems` are computed in ContentView but not properly refreshed
   - The reactive architecture isn't working as expected

3. **Layout Recursion Issues**:
   - Likely caused by the combination of drag-and-drop operations and immediate UI updates
   - The drop operation triggers layout changes while the view is still processing the drop
   - Need to ensure UI updates happen after the drop operation completes

### Proposed Solutions

1. **Fix UI Update Issues**:
   - Ensure DocumentStore properly publishes changes that trigger UI refresh
   - Make sure SidebarView reacts to document changes
   - Add explicit UI refresh mechanisms if needed

2. **Fix Layout Recursion**:
   - Use DispatchQueue.main.async to defer UI updates after drop operations
   - Ensure layout operations don't conflict with ongoing layout passes
   - Add proper state management for drop operations

3. **Improve Error Handling**:
   - Add better error handling and user feedback
   - Add loading states during import operations
   - Improve success/error alerts

## Implementation Plan

1. **First Fix**: Update DocumentStore to ensure proper UI refresh
2. **Second Fix**: Add deferred UI updates in SidebarView to prevent layout recursion
3. **Third Fix**: Improve error handling and user feedback
4. **Testing**: Test with sample files and verify both issues are resolved

## Changes Made

### 1. Fixed UI Update Issue in ContentView.swift
- Added `.onReceive` handler for `documentStore.documentChangePublisher` with error handling
- Created `handleDocumentChange(_:)` and `handleDocumentChangeOnMain(_:)` functions
- Used `@State private var refreshCounter = 0` to force UI refresh
- Added thread safety with DispatchQueue.main.async for UI updates
- Used `replaceError(with:)` to handle publisher errors properly
- Handles collection updates, document creation, deletion, and updates

### 2. Fixed Layout Recursion in SidebarView.swift
- Wrapped import operations in `DispatchQueue.main.async` to defer execution
- Applied to both `handleFileDropOnLibrary` and `handleDroppedFile` functions
- This prevents layout conflicts during drag-and-drop operations
- Ensures UI updates happen after the drop operation completes

### 3. Improved State Management
- The DocumentStore already had proper publishing mechanisms
- The issue was that ContentView wasn't listening to these changes
- Now ContentView properly reacts to all document change events

## Technical Details

### Root Cause Analysis
1. **UI Not Updating**: ContentView computed `libraryItems` from `documentStore.collections` but had no mechanism to react to changes
2. **Layout Recursion**: Immediate UI updates during drag-and-drop operations caused layout conflicts

### Solution Approach
1. **Reactive UI**: Added proper event handling to ensure UI refreshes when data changes
2. **Deferred Updates**: Used `DispatchQueue.main.async` to schedule UI updates after drop operations complete
3. **State Consistency**: Ensured all document change events trigger appropriate UI updates

## Files Modified
- `Fichero/Fichero/Views/ContentView.swift` - Added document change event handling with refresh counter
- `Fichero/Fichero/Views/Sidebar/SidebarView.swift` - Fixed layout recursion in import functions

## Next Steps
- Test the fixes with sample files
- Verify both layout recursion warnings and UI update issues are resolved
- Add loading states and improved error handling if needed
