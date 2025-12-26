# Context for TODO-054: Fix Drag and Drop Folder Hierarchy

## Background
User reports folders show "+" indicator when dragging over other folders but don't actually establish hierarchy. This is a critical UX issue.

## What you need to know
- SwiftUI .draggable and .dropDestination are key modifiers
- sample_code/AdoptingDragAndDropUsingSwiftUI has reference implementation
- Need to validate drop to prevent circular references (folder into its child)
- Backend needs to support parent-child folder relationships
- Visual feedback improves UX (highlight valid drop zones)
- Previous drag and drop work: TODO-021, TODO-038
