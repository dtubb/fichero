# Node Editor Fix Plan

## Issues Fixed

### 1. Gesture Blocking ✅
- Removed `.contentShape(Rectangle())` from node wrapper
- Changed from `.simultaneousGesture(TapGesture())` to `.onTapGesture`
- Changed from `.simultaneousGesture(DragGesture())` to `.gesture(DragGesture())`
- Added `.highPriorityGesture` on port drag gestures

### 2. Port Dragging ✅
- Port drag gestures now use `.highPriorityGesture` to take precedence
- Added `.contentShape(Circle())` explicitly on ports for proper hit testing
- Reduced minimum drag distance to 3px for responsiveness

### 3. Zoom Complexity Removed ✅
- Removed `canvasScale` and `lastScale` state
- Removed `canvasZoomGesture` (MagnificationGesture)
- Removed `scaleEffect` from canvas content
- Simplified coordinate calculations (no more division by scale)

### 4. Popover Positioning ✅
- Changed to `attachmentAnchor: .rect(.bounds)`
- Changed to `arrowEdge: .trailing` (arrow points left toward node)

### 5. Edge Completion ✅
- When drag ends, finds nearest input port within 30px threshold
- Automatically completes edge connection based on position
- No need for system drag-and-drop

---

## Summary of Changes

### WorkflowCanvasView.swift
- Removed zoom-related state and gestures
- Simplified node gesture handling
- Added position-based edge completion in `endEdgeDrag()`

### PortView.swift
- `DraggablePortView`: Uses `.highPriorityGesture` with `.contentShape(Circle())`
- `DroppablePortView`: Simplified to just show hover feedback

### Gesture Hierarchy (New)
```
Canvas Background
├── .gesture(DragGesture)      // Pan canvas
├── .onTapGesture              // Deselect all

Node (WorkflowNodeView)
├── .onTapGesture              // Select + open popover
├── .gesture(DragGesture)      // Move node

Port (DraggablePortView)
├── .highPriorityGesture       // Edge drag (takes priority)
```

---

## Testing Checklist

- [ ] Click canvas to deselect nodes
- [ ] Click node to select and open popover
- [ ] Drag node to move it
- [ ] Drag from output port to create edge line
- [ ] Release near input port to connect
- [ ] Click edge to select it
- [ ] Pan canvas by dragging background
