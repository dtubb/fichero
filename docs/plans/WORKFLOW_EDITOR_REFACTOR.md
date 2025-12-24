# Workflow Editor Refactor Plan

## Problem Summary

1. **Node clicking doesn't work** - Canvas DragGesture intercepts all touches
2. **File too large** - WorkflowCanvasView.swift is 895 lines with 4+ responsibilities
3. **Edge dragging offset** - Coordinate conversion incomplete

## Root Cause: Gesture Hierarchy

```swift
// CURRENT (broken):
ZStack {
    GridPattern()           // Decorative
    canvasContent           // Contains nodes with tap gestures
}
.gesture(canvasPanGesture)  // DragGesture BLOCKS child gestures
.onTapGesture { ... }       // Also competes with children
```

SwiftUI gesture rules:
- Parent `.gesture()` intercepts before children
- `.simultaneousGesture()` allows children to also receive
- `.highPriorityGesture()` on children wins over parent

## Solution

### File Structure (After)

```
Views/Workflow/
├── WorkflowView.swift           # Main HSplitView container
├── Canvas/
│   ├── WorkflowCanvasView.swift # Pan/zoom, coordinates layers
│   └── CanvasHelpers.swift      # GridPattern, preference keys
├── Node/
│   ├── WorkflowNodeView.swift   # Node visual representation
│   └── NodePopover.swift        # Node configuration sheet
├── Edge/
│   └── EdgeView.swift           # Edge + DraggingEdgeView
├── Port/
│   └── PortView.swift           # Port views (drag/drop)
├── Inspector/
│   └── WorkflowInspectorView.swift
└── Log/
    └── WorkflowOutputLog.swift
```

### Gesture Fix

```swift
// FIXED:
ZStack {
    // Background layer - receives canvas gestures
    GridPattern()
        .allowsHitTesting(false)  // Decorative only

    Color.clear
        .contentShape(Rectangle())
        .gesture(canvasPanGesture)      // Pan on background
        .onTapGesture { deselect() }    // Deselect on background tap

    // Content layer - nodes handle their own gestures
    canvasContent
        .scaleEffect(canvasScale)
        .offset(canvasOffset)
}
.gesture(canvasZoomGesture)  // Zoom can be simultaneous
```

Node gestures:
```swift
WorkflowNodeView(...)
    .position(x: node.positionX, y: node.positionY)
    .onTapGesture { handleNodeTap(node) }           // Tap to select/edit
    .gesture(nodeDragGesture(for: index))           // Drag to move
```

## Implementation Steps

### Step 1: Extract CanvasHelpers.swift
- GridPattern shape
- CanvasFramePreferenceKey

### Step 2: Extract WorkflowNodeView.swift
- Just the visual node (icon, label, ports)
- No popover, no gestures (those stay with canvas)

### Step 3: Extract NodePopover.swift
- Full popover content
- Provider/model selection
- Input mappings
- Delete/duplicate actions

### Step 4: Refactor WorkflowCanvasView.swift
- Fix gesture hierarchy
- Import extracted components
- Clean separation of concerns

### Step 5: Test
- [ ] Single click node → popover appears
- [ ] Drag node → moves smoothly
- [ ] Drag from port → edge follows mouse
- [ ] Drop on port → edge connects
- [ ] Click canvas background → deselects
- [ ] Drag canvas background → pans
- [ ] Pinch → zooms

## File Sizes (Target)

| File | Before | After |
|------|--------|-------|
| WorkflowCanvasView.swift | 895 | ~250 |
| WorkflowNodeView.swift | (new) | ~150 |
| NodePopover.swift | (new) | ~300 |
| CanvasHelpers.swift | (new) | ~50 |
