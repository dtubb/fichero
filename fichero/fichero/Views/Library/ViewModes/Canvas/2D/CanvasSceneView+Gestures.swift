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

    /// A new press finds a drag SwiftUI cancelled without `onEnded` (#4601): finish it before the press is read, so
    /// a click selects instead of moving the previously dragged card. One card is saved where it was left and
    /// selected as its release would have; a carried selection goes back where it started.
    func finishLeftoverDrag() {
        switch CanvasLeftoverDrag.at(press: draggingNodeId, carried: groupDragOrigins.count) {
        case .none:
            return
        case .single(let id):
            CanvasDragLog.ended(id, dropTarget: "nothing: the gesture was cancelled, finished at the next press")
            renderer.setHoverTarget(nil)
            if let controller { Task { await controller.flushActiveDrag() } }
        case .group(let id):
            CanvasDragLog.ended(id, dropTarget: "nothing: the gesture was cancelled, the selection put back")
            if let origin = dragOriginWorld { renderer.liveMove(id: id, toWorld: origin) }
            for (other, otherOrigin) in groupDragOrigins { renderer.liveMove(id: other, toWorld: otherOrigin) }
            for (page, pageOrigin) in nestedDragOrigins { renderer.liveMove(id: page, toWorld: pageOrigin) }
            renderer.setGroupDragging(false)
        }
        pressDragging = false
        draggingNodeId = nil
        dragStartScene = nil
        dragOriginWorld = nil
        groupDragOrigins = [:]
        nestedDragOrigins = [:]
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
