# TODO-054: Fix Drag and Drop Folder Hierarchy

## What to do
Fix folder drag and drop to properly establish parent-child hierarchy when dropping folders into other folders.

## Steps
- [x] Step 1: Review current drag and drop implementation
- [x] Step 2: Study sample_code/AdoptingDragAndDropUsingSwiftUI for patterns
- [x] Step 3: Implement .dropDestination for folders to accept other folders
- [x] Step 4: Add visual feedback during drag (highlight drop zone)
- [x] Step 5: Implement hierarchy update logic (set parent folder)
- [x] Step 6: Call backend API to persist hierarchy change
- [x] Step 7: Update sidebar state to reflect new hierarchy
- [x] Step 8: Run swiftlint and fix violations
- [x] Step 9: Add custom UTType declaration to project
- [ ] Step 10: Clean rebuild and test drag/drop functionality
- [ ] Step 11: Verify visual feedback appears
- [ ] Step 12: Verify backend API is called

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

## Implementation Notes (Dec 26, 2025)

### Changes Made
1. **Moved modifiers**: `.draggable()` and `.dropDestination()` now on `DisclosureGroup`, not just label
2. **Custom UTType**: Added `ca.tubb.fichero.item` to handle all sidebar items (docs, workflows, chats, searches)
3. **Project config**: Added `INFOPLIST_KEY_UTExportedTypeDeclarations` to project.pbxproj
4. **Enhanced visuals**: Drop target highlight at 0.2 opacity

### Testing Status
- Code written but NOT YET TESTED with clean rebuild
- Requires Product > Clean Build Folder, then rebuild
- See `summaries/2025-12-26-session.md` for detailed testing plan

### Known Issues to Address
- `isDescendant()` currently placeholder - needs proper circular reference detection
- No user feedback for invalid drops (only logs)
- Multi-item drops untested

## Need help?
- Review sample_code/AdoptingDragAndDropUsingSwiftUI thoroughly
- Test edge cases (drag folder into its own child, etc.)
- See summaries/2025-12-26-session.md for detailed testing checklist
