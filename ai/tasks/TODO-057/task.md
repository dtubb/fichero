# TODO-057: Enable Drag from Finder to Ingest Files

## What to do
Implement external drag and drop from macOS Finder to ingest files and folders into Fichero.

## Steps
- [ ] Step 1: Review sample_code/AdoptingDragAndDropUsingSwiftUI for external drag
- [ ] Step 2: Add .dropDestination accepting file URLs from external sources
- [ ] Step 3: Handle dropped file/folder URLs
- [ ] Step 4: Call backend file import API endpoint
- [ ] Step 5: Show progress indicator during import
- [ ] Step 6: Update sidebar to show newly imported items
- [ ] Step 7: Handle errors (unsupported file types, import failures)
- [ ] Step 8: Run swiftlint
- [ ] Step 9: Test dragging various file types from Finder

## Files
- File to change: Fichero/Fichero/Views/Browser/SidebarView.swift (or main window view)
- Backend API: File import endpoint (check TODO-004, TODO-025)
- Reference: sample_code/AdoptingDragAndDropUsingSwiftUI

## Questions for Human
- [ ] Question 1: Should drag from Finder work on entire window or just sidebar?
    Answer: Entire main content area for better UX, plus sidebar
- [ ] Question 2: Should there be file type validation before import?
    Answer: Yes, show error for unsupported types
- [ ] Question 3: Should import default to a specific folder or prompt user?
    Answer: Default to root, allow drop on folders for targeted import

## Answers and Implementation
- Use UTType for file type handling
- Accept file URLs from external drag sources
- Call existing file import backend API
- Progress feedback during import
- Error handling for unsupported files

## Need help?
- Review sample_code/AdoptingDragAndDropUsingSwiftUI for external drag patterns
- Check backend file import API documentation
- Test with various file types (PDF, TXT, images, etc.)
