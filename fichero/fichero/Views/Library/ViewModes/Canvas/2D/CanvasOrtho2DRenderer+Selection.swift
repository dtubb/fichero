import CoreGraphics
import Foundation
import RealityKit
import simd

// MARK: - The 2D canvas's selection frames and resize (#4409)

/// Split out of `CanvasOrtho2DRenderer` by cohesion: everything here is about
/// showing WHICH cards are selected and letting one of them be resized. The
/// card/edge/camera half stays in the main file.
///
/// The members this reaches for (`placeablesById`, `selection`,
/// `placeablesRoot`, `decorator`, `cardDimensions`) are internal rather than
/// private for exactly this reason — Swift's `private` is FILE-scoped.
extension CanvasOrtho2DRenderer {

    // MARK: - Card geometry (shared by the card mesh and the frame around it)

    /// The size a card is drawn at right now: the live drag size while a resize
    /// gesture is in flight, else the persisted one.
    func effectiveSize(_ placeable: CanvasPlaceable) -> CGSize {
        if let override = liveSizeOverride, override.id == placeable.id { return override.size }
        return placeable.size ?? Self.defaultCardSize
    }

    /// Source cards take their page's true aspect once the texture has loaded
    /// (#4193), area-normalized to the configured card footprint; the fallback
    /// keeps the configured shape until then so cards don't jump mid-load.
    /// Shared by the card mesh and the selection frame, so a frame can never
    /// be drawn at a size the card is not.
    func cardDimensions(_ placeable: CanvasPlaceable, size: CGSize? = nil) -> (width: Float, height: Float) {
        let size = size ?? effectiveSize(placeable)
        return CanvasCardGeometry.dimensions(
            area: Float(size.width) * Float(size.height),
            aspect: sourceId(of: placeable).flatMap { CanvasCardGeometry.knownAspect(forSourceId: $0) },
            fallback: Float(size.width) / Float(size.height)
        )
    }

    // MARK: - Selection decoration (#4409)

    /// Redraw the selection frames and handles from the CURRENT card geometry.
    func refreshSelectionDecoration() {
        decorator.update(items: selectionFrameItems())
    }

    /// The selected placeables, projected, at their LIVE positions.
    ///
    /// Position comes from the card entity when one exists rather than from
    /// `placeablesById`, because `liveMove` moves the entity without touching
    /// the applied state — reading the model instead would leave the frame
    /// behind while the card is dragged.
    func selectionFrameItems() -> [CanvasSelectionFrame.Item] {
        selection.compactMap { id in
            guard let placeable = placeablesById[id] else { return nil }
            let entity = placeablesRoot.findEntity(named: id)
            let scene = entity?.position ?? Canvas2DProjection.scenePosition(placeable.position)
            let (width, height) = cardDimensions(placeable)
            return CanvasSelectionFrame.Item(
                id: id,
                centerX: scene.x,
                centerY: scene.y,
                width: width,
                height: height,
                isResizable: CanvasSelectionFrame.isResizable(placeable.content)
            )
        }
    }

    // MARK: - Resize

    /// The persisted size of a placeable — the origin a resize drag grows from.
    func persistedSize(of id: String) -> CGSize? {
        placeablesById[id].map { $0.size ?? Self.defaultCardSize }
    }

    /// The placeable's current world position, so a resize can persist its row
    /// without moving a card that has no saved row yet to the origin.
    func worldPosition(of id: String) -> SIMD3<Double>? {
        placeablesById[id]?.position
    }

    /// Live resize feedback: SCALE the existing card rather than rebuilding it,
    /// so the loaded page texture survives the gesture (the same reason
    /// selection no longer rebuilds). The `.resize` op on release replaces the
    /// mesh properly and clears the override.
    func liveResize(id: String, toSize size: CGSize) {
        guard let placeable = placeablesById[id],
              let entity = placeablesRoot.findEntity(named: id) else { return }
        let base = cardDimensions(placeable, size: placeable.size ?? Self.defaultCardSize)
        liveSizeOverride = (id, size)
        let target = cardDimensions(placeable, size: size)
        guard base.width > 0, base.height > 0 else { return }
        entity.scale = SIMD3<Float>(target.width / base.width, target.height / base.height, 1)
        refreshSelectionDecoration()
    }

    /// Apply a committed size: new mesh and collision, SAME entity and SAME
    /// materials — so a resize never drops the page texture either.
    func resizeCardInPlace(_ id: String) {
        if liveSizeOverride?.id == id { liveSizeOverride = nil }
        guard let placeable = placeablesById[id],
              let entity = placeablesRoot.findEntity(named: id) as? ModelEntity else { return }
        let (width, height) = cardDimensions(placeable)
        entity.scale = .one
        entity.model?.mesh = MeshResource.generatePlane(
            width: width, height: height, cornerRadius: min(width, height) * 0.08
        )
        entity.components.set(CollisionComponent(shapes: [.generateBox(size: SIMD3<Float>(width, height, 0.02))]))
    }
}
