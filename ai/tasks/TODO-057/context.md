# Context for TODO-057: Enable Drag from Finder to Ingest Files

## Background
Critical feature for macOS app - users expect to drag files from Finder to import them. Currently not supported.

## What you need to know
- sample_code/AdoptingDragAndDropUsingSwiftUI shows external drag patterns
- Backend file import API exists (TODO-004, TODO-025)
- Use UTType.fileURL for accepting file drops
- Progress indication important for large files/folders
- Error handling critical (show which files failed and why)
- Integration with existing import workflow
- Consider accepting drops on entire window, not just specific areas
