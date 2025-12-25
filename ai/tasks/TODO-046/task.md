# TODO-046: Implement SwiftUI Canvas Foundation

## What to do
Create the foundation for the SwiftUI node editor canvas with zoom, pan, and basic interactions

## Steps
- [ ] Step 1: Create WorkflowCanvasView.swift with infinite canvas
- [ ] Step 2: Implement zoom and pan functionality with gesture recognition
- [ ] Step 3: Add grid background with snapping for precise node placement
- [ ] Step 4: Implement node drag-and-drop functionality
- [ ] Step 5: Add node selection (single and multi-select)
- [ ] Step 6: Implement canvas state persistence and serialization
- [ ] Step 7: Create basic unit tests for canvas interactions
- [ ] Step 8: Test performance with multiple nodes

## Files
- File to create: Fichero/Fichero/Views/WorkflowCanvasView.swift (main canvas)
- File to modify: Fichero/Fichero/Models/Workflow.swift (extend for canvas state)
- File to create: Fichero/FicheroTests/WorkflowCanvasTests.swift (unit tests)
- File to create: Fichero/Fichero/Views/CanvasGridView.swift (grid background)

## Questions for Human
- [ ] Question 1: What zoom range should be supported?
    Answer: 10% to 400% with smooth scaling
- [ ] Question 2: Should we implement undo/redo functionality?
    Answer: Yes, basic undo/redo for node operations
- [ ] Question 3: What's the expected performance target for node count?
    Answer: Should handle 100+ nodes smoothly

## Answers and Implementation
- Will use SwiftUI gesture recognizers for interactions
- Will implement efficient rendering for performance
- Will follow Audio Hijack Pro patterns for canvas behavior
- Will add proper state management for canvas operations
- Will create comprehensive unit tests for all interactions

## Need help?
- Review TODO-042 workflow_plan.md for canvas architecture
- Check SwiftUI documentation for gesture handling
- Keep implementation focused on core canvas functionality