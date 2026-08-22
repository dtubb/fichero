#if canImport(AppKit)
import AppKit
#endif
import RealityKit
import SwiftUI

// MARK: - Gestures (split from CanvasSpaceView for file_length /
// type_body_length — the struct keeps state + scene; the gesture grammar
// lives here).

extension CanvasSpaceView {
    var marqueeModifiersHeld: Bool {
        #if canImport(AppKit)
        NSEvent.modifierFlags.contains(.shift) && NSEvent.modifierFlags.contains(.option)
        #else
        false  // iPad marquee arrives with the touch grammar, not modifiers
        #endif
    }

    func marqueeGesture(in size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 4)
            .onChanged { value in
                if marqueeStart == nil { marqueeStart = value.startLocation }
                guard let start = marqueeStart else { return }
                marqueeScreenRect = CGRect(
                    x: min(start.x, value.location.x),
                    y: min(start.y, value.location.y),
                    width: abs(value.location.x - start.x),
                    height: abs(value.location.y - start.y)
                )
            }
            .onEnded { _ in
                defer { marqueeStart = nil; marqueeScreenRect = nil }
                guard let rect = marqueeScreenRect, rect.width > 2, rect.height > 2 else { return }
                let hits = renderer.screenPositions(in: size)
                    .filter { rect.contains($0.value) }
                    .map(\.key)
                controller?.dispatch(.marquee(
                    ids: Set(hits),
                    modifiers: CanvasInteractionController.liveSelectionModifiers()
                ))
            }
    }

    /// Double-click a card → close in on it; again → the prior pose (user,
    /// 2026-08-20). Simultaneous so the first click still selects.
    var doubleTapZoom: some Gesture {
        TapGesture(count: 2)
            .targetedToAnyEntity()
            .onEnded { value in
                let id = value.entity.name
                guard !id.isEmpty else { return }
                toggleFocusZoom(on: id)
            }
    }

    /// One toggle for both routes — see CanvasSceneView.toggleFocusZoom.
    func toggleFocusZoom(on id: String) {
        if let snapshot = focusReturnSnapshot {
            renderer.restoreCamera(snapshot)
            focusReturnSnapshot = nil
        } else {
            focusReturnSnapshot = renderer.cameraSnapshot()
            renderer.focusZoom(on: id)
        }
    }

    var tapSelect: some Gesture {
        TapGesture()
            .targetedToAnyEntity()
            .onEnded { value in
                let id = value.entity.name
                controller?.dispatch(.tap(
                    id: id.isEmpty ? nil : id,
                    modifiers: CanvasInteractionController.liveSelectionModifiers()
                ))
            }
    }

    /// Drag a card in 3D: move it in the camera's view plane and persist a single
    /// snapped row on release — same controller path as 2D, only the screen→world
    /// conversion is 3D (camera-plane) instead of ortho.
    var nodeDrag: some Gesture {
        DragGesture(minimumDistance: 2)
            .targetedToAnyEntity()
            .onChanged { value in
                let id = value.entity.name
                guard !id.isEmpty else { return }
                if draggingNodeId == nil {
                    draggingNodeId = id
                    dragStartWorld = Canvas3DProjection.worldPosition(value.entity.position(relativeTo: nil))
                    controller?.dispatch(.dragBegan(id: id))
                }
                guard let start = dragStartWorld else { return }
                #if canImport(AppKit)
                let moveInZ = NSEvent.modifierFlags.contains(.option)
                #else
                let moveInZ = false
                #endif
                let world = start + renderer.worldDragDelta(screenTranslation: value.translation, moveInZ: moveInZ)
                renderer.liveMove(id: id, toWorld: world)
                renderer.setHoverTarget(renderer.dropTargetId(nearWorld: world, excluding: id))
                controller?.dispatch(.dragMoved(id: id, position: world))
            }
            .onEnded { value in
                guard let id = draggingNodeId, let start = dragStartWorld else { return }
                #if canImport(AppKit)
                let moveInZ = NSEvent.modifierFlags.contains(.option)
                #else
                let moveInZ = false
                #endif
                let world = start + renderer.worldDragDelta(screenTranslation: value.translation, moveInZ: moveInZ)
                renderer.setHoverTarget(nil)
                let target = dropTarget(near: world, dragged: id)
                let modifiers: CanvasDropModifiers = optionHeld ? .forceLink : []
                controller?.dispatch(.dragEnded(id: id, position: world, dropTarget: target, modifiers: modifiers))
                if target == nil {
                    controller?.registerMoveUndo(id: id, origin: start, destination: world, undoManager: undoManager)
                }
                draggingNodeId = nil
                dragStartWorld = nil
            }
    }
}
