import RealityKit
import simd
import SwiftUI

// MARK: - Corner-handle resize on the 2D canvas (#4409)

/// Split out of `CanvasSceneView` by cohesion: the one gesture that changes a
/// card's SIZE rather than its position or the selection.
///
/// Attached alongside the card drag rather than above it. Ordering between two
/// `highPriorityGesture`s is not something to rely on, so the two are made
/// mutually exclusive BY SUBJECT instead — each guards on whether the targeted
/// entity is a resize handle, so exactly one of them acts on a given drag.
extension CanvasSceneView {

    /// Drag a corner handle → resize the card (#4409).
    ///
    /// Live feedback SCALES the existing card (no rebuild, so the page texture
    /// survives the gesture); the release persists `w`/`h` on the one layout
    /// row and registers an undo, so a resize is undoable like every other
    /// mutation on this surface.
    func resizeDrag(in size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 1)
            .targetedToAnyEntity()
            .onChanged { value in
                guard let parsed = CanvasSelectionFrame.handle(fromEntityName: value.entity.name) else { return }
                if resizeHandle == nil {
                    resizeHandle = (parsed.itemId, parsed.corner)
                    resizeOriginSize = renderer.persistedSize(of: parsed.itemId)
                }
                guard let origin = resizeOriginSize else { return }
                let delta = Canvas2DProjection.sceneDelta(
                    screenTranslation: value.translation,
                    orthoScale: renderer.orthoScale,
                    viewHeight: size.height
                )
                // Proportional by default; ⇧ frees the aspect ratio. ⇧ is safe
                // to reuse here — a handle drag can never be a selection
                // extend — and ⌥ already means force-link on this surface.
                let free = CanvasInteractionController.liveSelectionModifiers().contains(.shift)
                let updated = CanvasSelectionFrame.resizedSize(
                    from: origin,
                    corner: parsed.corner,
                    sceneDelta: SIMD2<Float>(delta.x, delta.y),
                    proportional: !free
                )
                resizeLiveSize = updated
                renderer.liveResize(id: parsed.itemId, toSize: updated)
            }
            .onEnded { _ in
                defer {
                    resizeHandle = nil
                    resizeOriginSize = nil
                    resizeLiveSize = nil
                }
                guard let handle = resizeHandle,
                      let origin = resizeOriginSize,
                      let final = resizeLiveSize,
                      final != origin,
                      let world = renderer.worldPosition(of: handle.itemId) else { return }
                controller?.dispatch(.resize(id: handle.itemId, size: final, position: world))
                controller?.registerResizeUndo(
                    id: handle.itemId,
                    at: world,
                    origin: origin,
                    destination: final,
                    undoManager: undoManager
                )
            }
    }
}
