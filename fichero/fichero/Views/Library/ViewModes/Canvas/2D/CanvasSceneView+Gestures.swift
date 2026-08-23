import RealityKit
import SwiftUI

// MARK: - Gestures (split from CanvasSceneView for file_length /
// type_body_length).

extension CanvasSceneView {

    /// One toggle for both routes — double-click AND the context menu's
    /// "Zoom to Card" (touch-reachability: iPad has no double-click, so the
    /// action must exist on a route touch can reach).
    func toggleFocusZoom(on id: String) {
        if let snapshot = focusReturnSnapshot {
            renderer.restoreCamera(snapshot)
            focusReturnSnapshot = nil
        } else {
            // A double-click IS a jump, so it joins the history — ⌘[ gets you
            // back even after the double-click's own return trip is spent.
            jumpHistory.record(renderer.cameraSnapshot())
            focusReturnSnapshot = renderer.cameraSnapshot()
            renderer.focusZoom(on: id)
        }
    }

    // MARK: - Camera jumps (§16, R10 step 4)

    /// What the View menu's Canvas section drives. Published only while a
    /// canvas is focused, so the section disables itself everywhere else.
    var canvasCommandActions: CanvasViewActions {
        CanvasViewActions(
            zoomToFit: zoomToFit,
            jumpBack: jumpBack,
            jumpForward: jumpForward,
            canJumpBack: jumpHistory.canJumpBack,
            canJumpForward: jumpHistory.canJumpForward
        )
    }

    /// Frame the whole board. Records where the camera WAS, so ⌘[ returns.
    func zoomToFit() {
        jumpHistory.record(renderer.cameraSnapshot())
        renderer.fit()
    }

    /// Walk back to the pose before the last jump — a cut, never a flight.
    func jumpBack() {
        guard let previous = jumpHistory.jumpBack(from: renderer.cameraSnapshot()) else { return }
        renderer.restoreCamera(previous)
    }

    /// Undo a `jumpBack`.
    func jumpForward() {
        guard let next = jumpHistory.jumpForward(from: renderer.cameraSnapshot()) else { return }
        renderer.restoreCamera(next)
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
                // Double-click on the SAME card within the classic interval →
                // zoom toggle; anything else is a select. See lastTapNodeId.
                let now = Date()
                if !id.isEmpty, lastTapNodeId == id,
                   now.timeIntervalSince(lastTapAt) < 0.35 {
                    lastTapNodeId = nil
                    toggleFocusZoom(on: id)
                    return
                }
                lastTapNodeId = id.isEmpty ? nil : id
                lastTapAt = now
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

    // MARK: - Marquee overlay
    //
    // Lives with the gesture that drives it, and out of the main file, which
    // is at its file_length ceiling.

    @ViewBuilder
    var marqueeOverlay: some View {
        if let rect = marqueeRect {
            // SAME style as the icon grid's LibraryMarquee (#4601): the
            // full-opacity stroke read darker than every other marquee.
            Rectangle()
                .fill(Color.accentColor.opacity(0.15))
                .overlay(Rectangle().stroke(Color.accentColor.opacity(0.6), lineWidth: 1))
                .frame(width: rect.width, height: rect.height)
                .position(x: rect.midX, y: rect.midY)
                .allowsHitTesting(false)
        }
    }
}
