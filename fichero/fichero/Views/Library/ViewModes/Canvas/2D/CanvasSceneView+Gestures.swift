import RealityKit
import SwiftUI

// MARK: - Gestures (split from CanvasSceneView for file_length /
// type_body_length).

extension CanvasSceneView {
    /// Double-click a card → fill the view with it; double-click again →
    /// return to the exact prior pose (user, 2026-08-20). Simultaneous so the
    /// first click still selects instantly.
    var doubleTapZoom: some Gesture {
        TapGesture(count: 2)
            .targetedToAnyEntity()
            .onEnded { value in
                let id = value.entity.name
                guard !CanvasSelectionFrame.isDecoration(id), !id.isEmpty else { return }
                toggleFocusZoom(on: id)
            }
    }

    /// One toggle for both routes — double-click AND the context menu's
    /// "Zoom to Card" (touch-reachability: iPad has no double-click, so the
    /// action must exist on a route touch can reach).
    func toggleFocusZoom(on id: String) {
        if let snapshot = focusReturnSnapshot {
            renderer.restoreCamera(snapshot)
            focusReturnSnapshot = nil
        } else {
            focusReturnSnapshot = renderer.cameraSnapshot()
            renderer.focusZoom(on: id)
        }
    }

    /// Tap a card → select it through the controller (writes `selectedNodeId`).
    var tapSelect: some Gesture {
        TapGesture()
            .targetedToAnyEntity()
            .onEnded { value in
                let id = value.entity.name
                // A tap on the frame or a handle is not a tap on a placeable:
                // decoration entities carry synthetic names that match nothing
                // in the scene, so dispatching one would select a placeable
                // that does not exist and silently clear the real selection.
                guard !CanvasSelectionFrame.isDecoration(id) else { return }
                controller?.dispatch(.tap(
                    id: id.isEmpty ? nil : id,
                    modifiers: CanvasInteractionController.liveSelectionModifiers()
                ))
            }
    }

    /// Drag a card → move it live and persist a single snapped row on release
    /// (#3084). The controller suppresses store echoes for the dragged id
    /// mid-drag, so the gesture is never fought.
    func nodeDrag(in size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 2)
            .targetedToAnyEntity()
            .onChanged { value in
                let id = value.entity.name
                guard !id.isEmpty else { return }
                // A drag that started on a resize handle belongs to
                // `resizeDrag`. Without this the same gesture would ALSO move
                // the card, so resizing would drag the thing being resized.
                guard !CanvasSelectionFrame.isDecoration(id) else { return }
                if draggingNodeId == nil {
                    draggingNodeId = id
                    let startScene = value.entity.position(relativeTo: nil)
                    dragStartScene = startScene
                    dragOriginWorld = Canvas2DProjection.worldPosition(startScene)
                    controller?.dispatch(.dragBegan(id: id))
                }
                guard let start = dragStartScene else { return }
                let world = draggedWorld(start: start, translation: value.translation, viewHeight: size.height, id: id)
                renderer.liveMove(id: id, toWorld: world)
                renderer.setHoverTarget(renderer.dropTargetId(nearWorld: world, excluding: id))
                controller?.dispatch(.dragMoved(id: id, position: world))
            }
            .onEnded { value in
                guard let id = draggingNodeId, let start = dragStartScene else { return }
                let world = draggedWorld(start: start, translation: value.translation, viewHeight: size.height, id: id)
                renderer.setHoverTarget(nil)
                let target = dropTarget(near: world, dragged: id)
                let modifiers: CanvasDropModifiers = optionHeld ? .forceLink : []
                controller?.dispatch(.dragEnded(id: id, position: world, dropTarget: target, modifiers: modifiers))
                // Only a plain place (no drop target) registers a move-undo — a
                // move-into / link is undone through its own action's audit trail.
                if target == nil, let controller, let origin = dragOriginWorld {
                    controller.registerMoveUndo(id: id, origin: origin, destination: world, undoManager: undoManager)
                }
                draggingNodeId = nil
                dragStartScene = nil
                dragOriginWorld = nil
            }
    }
}
