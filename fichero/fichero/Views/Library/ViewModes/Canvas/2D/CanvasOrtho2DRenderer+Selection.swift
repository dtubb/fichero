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
    /// `chromeScale` keeps the frame a constant SCREEN thickness across zoom
    /// (#4601): orthoScale grows as the user zooms out, so the world-space
    /// bars grow by the same ratio and cancel out on screen.
    func refreshSelectionDecoration() {
        updateSelectionPlates()
        decorator.showsFrames = false
        // Frame and corner handles for ONE selected card only (2026-09-30): resizing is a one-card
        // act, and a frame per card is what made a large selection slow (every refresh rebuilds
        // every frame's meshes). Several selected cards show their plates alone.
        decorator.update(
            items: selection.count == 1 && !isGroupDragging ? selectionFrameItems() : [],
            chromeScale: orthoScale / Self.defaultOrthoScale
        )
    }

    /// A selected card sits on an accent-coloured plate, as a selected icon does in Finder. The
    /// plate is a CHILD of the card, so it travels with the card through any drag and scales with
    /// it through a resize at no cost; only a card whose selection changed gains or loses one.
    func updateSelectionPlates() {
        let plateName = "selectionPlate"
        for id in platedIds.subtracting(selection) {
            placeablesRoot.findEntity(named: id)?.findEntity(named: plateName)?.removeFromParent()
        }
        for id in selection.subtracting(platedIds) {
            guard let placeable = placeablesById[id], let card = placeablesRoot.findEntity(named: id) else { continue }
            let (width, height) = cardDimensions(placeable)
            let pad = min(width, height) * 0.08
            let plate = ModelEntity(
                mesh: .generatePlane(width: width + pad * 2, height: height + pad * 2, cornerRadius: pad),
                materials: [UnlitMaterial(color: PlatformColor.controlAccentColorCompat.withAlphaComponent(0.55))]
            )
            plate.name = plateName
            plate.position = SIMD3<Float>(0, 0, -0.005)
            card.addChild(plate)
        }
        platedIds = selection.filter { placeablesRoot.findEntity(named: $0) != nil }
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

    /// The card under a screen point, the one drawn on top when cards overlap, or nil over the board.
    ///
    /// The canvas's own hit test, from the geometry it draws with (2026-09-30): RealityKit's
    /// entity-targeted gestures stopped reaching the cards, so every press fell through to the
    /// background rubber band and no card could be clicked or dragged. This reads the same
    /// positions and sizes the cards are drawn from, so it cannot disagree with what is on screen.
    func placeableId(atScreenPoint point: CGPoint, viewSize: CGSize) -> String? {
        let worldPerPoint = Canvas2DProjection.worldPerPoint(orthoScale: orthoScale, viewHeight: viewSize.height)
        guard worldPerPoint > 0 else { return nil }
        let hits = placeablesById.values.filter { placeable in
            let (width, height) = cardDimensions(placeable)
            let center = Canvas2DProjection.screenPoint(
                scene: Canvas2DProjection.scenePosition(placeable.position),
                cameraX: camera.position.x,
                cameraY: camera.position.y,
                orthoScale: orthoScale,
                viewSize: viewSize
            )
            return abs(point.x - center.x) <= CGFloat(width / worldPerPoint) / 2
                && abs(point.y - center.y) <= CGFloat(height / worldPerPoint) / 2
        }
        return hits.max { ($0.zIndex, $0.id) < ($1.zIndex, $1.id) }?.id
    }

    /// The selection frame's corner handle under a screen point (within `tolerance` points), if any.
    /// Checked BEFORE the card: a handle sits on the card's corner, and a press there used to move
    /// the card instead of resizing it (2026-09-30).
    func resizeHandle(atScreenPoint point: CGPoint, viewSize: CGSize, tolerance: CGFloat = 10)
        -> (itemId: String, corner: CanvasSelectionFrame.Corner)? {
        var found: (itemId: String, corner: CanvasSelectionFrame.Corner)?
        func walk(_ entity: Entity) {
            if found == nil, let handle = CanvasSelectionFrame.handle(fromEntityName: entity.name) {
                let screen = Canvas2DProjection.screenPoint(
                    scene: entity.position(relativeTo: nil),
                    cameraX: camera.position.x,
                    cameraY: camera.position.y,
                    orthoScale: orthoScale,
                    viewSize: viewSize
                )
                if hypot(screen.x - point.x, screen.y - point.y) <= tolerance {
                    found = (handle.itemId, handle.corner)
                }
            }
            entity.children.forEach(walk)
        }
        walk(decorator.root)
        return found
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
        // A resize is the person's hand on the board too: no re-fit afterwards (#5423, `liveMove`).
        cameraIsAutoFit = false
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
