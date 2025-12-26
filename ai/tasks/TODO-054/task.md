# TODO-054: Fix Drag and Drop Folder Hierarchy

## What to do
Fix folder drag and drop to properly establish parent-child hierarchy when dropping folders into other folders.

## Steps
- [ ] Step 1: Review current drag and drop implementation
- [ ] Step 2: Study sample_code/AdoptingDragAndDropUsingSwiftUI for patterns
- [ ] Step 3: Implement .dropDestination for folders to accept other folders
- [ ] Step 4: Add visual feedback during drag (highlight drop zone)
- [ ] Step 5: Implement hierarchy update logic (set parent folder)
- [ ] Step 6: Call backend API to persist hierarchy change
- [ ] Step 7: Update sidebar state to reflect new hierarchy
- [ ] Step 8: Run swiftlint and fix violations
- [ ] Step 9: Test nested folder drag and drop

## Files
- File to change: Fichero/Fichero/Views/Browser/SidebarView.swift (or related component)
- Reference: sample_code/AdoptingDragAndDropUsingSwiftUI

## Questions for Human
- [ ] Question 1: Should there be a maximum nesting depth for folders?
    Answer: No artificial limit, let backend/filesystem handle constraints
- [ ] Question 2: What should happen if drop fails (e.g., circular reference)?
    Answer: Show error message and revert to original state

## Answers and Implementation
- Use .draggable and .dropDestination modifiers
- Implement proper drop validation (prevent circular references)
- Visual feedback during drag operation
- Backend API call to update folder parent relationship
- Handle errors gracefully with user feedback

## Need help?
- Review sample_code/AdoptingDragAndDropUsingSwiftUI thoroughly
- Test edge cases (drag folder into its own child, etc.)
