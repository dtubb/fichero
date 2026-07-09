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

            workflow.nodes[index].positionX = newX
            workflow.nodes[index].positionY = newY

            // Push other nodes out of the way if they would overlap
            resolveCollisions(for: index)
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

    /// Push nodes apart to avoid overlap (with smooth animation)
    func resolveCollisions(for draggedIndex: Int) {
        let draggedNode = workflow.nodes[draggedIndex]
        let minDistance: CGFloat = nodeWidth + 20  // Minimum space between node centers

        for index in workflow.nodes.indices where index != draggedIndex {
            let otherNode = workflow.nodes[index]
            let deltaX = otherNode.positionX - draggedNode.positionX
            let deltaY = otherNode.positionY - draggedNode.positionY
            let distance = hypot(deltaX, deltaY)

            // If nodes are too close, push the other node away with animation
            if distance < minDistance && distance > 0 {
                let overlap = minDistance - distance
                let pushX = (deltaX / distance) * overlap
                let pushY = (deltaY / distance) * overlap

                withAnimation(.spring(response: 0.15, dampingFraction: 0.8)) {
                    workflow.nodes[index].positionX += pushX
                    workflow.nodes[index].positionY += pushY
                }
            } else if distance == 0 {
                // Exactly same position - push right
                withAnimation(.spring(response: 0.15, dampingFraction: 0.8)) {
                    workflow.nodes[index].positionX += minDistance
                }
            }
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
