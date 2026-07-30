import SwiftUI

// MARK: - Zoom and Pan

extension WorkflowCanvasView {
    func handleZoom(value: CGFloat) {
        // Calculate new scale with constraints (10% to 400%)
        let newScale = lastScale * value
        let constrainedScale = max(0.1, min(4.0, newScale))

        // Only update if within bounds
        if constrainedScale != scale {
            scale = constrainedScale
        }
    }

    func handleZoomEnded(value: CGFloat) {
        lastScale = scale
    }

    func handlePan(value: DragGesture.Value) {
        // Don't pan if we're dragging a node or an edge
        guard draggingNodeIndex == nil && draggedEdge == nil else { return }

        if !isPanning {
            // Start panning - store initial offset
            lastOffset = offset
            isPanning = true
        }

        // Calculate new offset based on drag translation
        let newOffset = CGSize(
            width: lastOffset.width + value.translation.width,
            height: lastOffset.height + value.translation.height
        )

        offset = newOffset
    }
}

// MARK: - Node Dragging

extension WorkflowCanvasView {
    func handleNodeDrag(value: DragGesture.Value, index: Int) {
        // Don't move node if we're dragging an edge from a port
        guard draggedEdge == nil else { return }

        // On first drag event, store starting position
        if nodeDragStartPosition == nil {
            dragUndoWorkflow = workflow
            nodeDragStartPosition = CGPoint(
                x: workflow.nodes[index].positionX,
                y: workflow.nodes[index].positionY
            )
            draggingNodeIndex = index
        }

        // Move node relative to start position
        if let startPos = nodeDragStartPosition {
            var newX = startPos.x + value.translation.width
            var newY = startPos.y + value.translation.height

            // Apply grid snapping if enabled
            if snapToGrid {
                newX = snapToGridValue(newX)
                newY = snapToGridValue(newY)
            }

            // Move ONLY the dragged node (#4323). Neighbour-push collision
            // resolution used to shove other nodes around on every drag tick
            // and the drift was then autosaved — repositioning one node could
            // silently rearrange (and persist) the whole graph.
            workflow.nodes[index].positionX = newX
            workflow.nodes[index].positionY = newY
        }
    }

    /// Snap a value to the nearest grid line
    func snapToGridValue(_ value: CGFloat) -> CGFloat {
        let gridSize = gridSpacing / scale  // Adjust grid size based on zoom level
        let remainder = value.truncatingRemainder(dividingBy: gridSize)

        if abs(remainder) < snapThreshold / scale {
            return value - remainder  // Snap to grid
        } else {
            return value  // Keep original position
        }
    }

    func finishNodeDrag() {
        nodeDragStartPosition = nil
        draggingNodeIndex = nil
        if let previousWorkflow = dragUndoWorkflow {
            registerUndo(from: previousWorkflow, actionName: "Move Node")
            dragUndoWorkflow = nil
        }
    }
}
