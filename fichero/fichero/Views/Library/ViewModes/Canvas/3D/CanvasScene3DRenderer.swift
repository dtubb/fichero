import FicheroAPIClient
import Foundation
import OSLog
import RealityKit
import simd
import SwiftUI

// MARK: - RealityKit perspective-3D renderer (#3104)

/// The 3D 'Space' renderer — the perspective twin of `CanvasOrtho2DRenderer`.
/// Same #3103 contract, same shared `CanvasInteractionController`, so 2D and 3D
/// behave identically (selection / drag / persist / CRUD); the ONLY differences
/// are renderer-local: a `PerspectiveCamera` with orbit/pan/zoom, the full xyz
/// projection (z USED, via `Canvas3DProjection`), and cylinder connectors.
///
/// Supersedes the internals of #3088's `SpaceSceneView`: scene content is driven
/// ONLY by `apply(_ ops:)` from `CanvasSceneDiff` (never the old
/// `layoutRevision`-bump + reposition-everything pass), and positions come
/// pre-resolved from `CanvasSceneState.resolve` (its `effectivePosition` moved
/// into the contract — no local copy).
@MainActor
final class CanvasScene3DRenderer: CanvasSceneRenderer {
    private let log = Logger(subsystem: "app.fichero.fichero", category: "CanvasScene3DRenderer")

    let root = Entity()
    private let placeablesRoot = Entity()
    private let edgesRoot = Entity()
    let camera = PerspectiveCamera()

    private var placeablesById: [String: CanvasPlaceable] = [:]
    private var selection: Set<String> = []
    private var appliedState = CanvasSceneState.empty

    // Orbit camera state (renderer-local, ported from the proven #3088 rig).
    private var yaw: Float = 0
    private var pitch: Float = 0.35
    private var distance: Float = 6
    private var lookAt = SIMD3<Float>(0, 0, 0)
    static let defaultDistance: Float = 6
    /// Extent of one placeable in scene units — the basis for how close the
    /// camera may get before an item is legible (#4411).
    private static let itemExtent: Float = 1

    /// Span of the current arrangement, refreshed whenever placeables change.
    /// The zoom-out bound derives from THIS rather than a constant, so "as far
    /// out as it goes" and "everything fits" are the same place.
    private var arrangementSpan: Float = 1

    var detailTier: CanvasDetailTier = .thumbnail
    var onIntent: ((CanvasIntent) -> Void)?
    var isDragSuppressed: ((String) -> Bool)?

    /// Closer camera → larger reported zoom, so `CanvasDetailTier` swaps in
    /// thumbnails / full textures as the user flies in (same rule as 2D).
    var reportedZoomScale: Double { Double(Self.defaultDistance / distance) }

    init() {
        root.addChild(placeablesRoot)
        root.addChild(edgesRoot)
        updateCamera()
    }

    // MARK: - CanvasSceneRenderer

    func apply(_ ops: [CanvasSceneOp]) {
        for operation in ops { applyOne(operation) }
    }

    func reconcile(to newState: CanvasSceneState) {
        apply(CanvasSceneDiff.compute(from: appliedState, to: newState))
        appliedState = newState
    }

    /// Drag-onto-item target picking is #3086 (needs a scene raycast); tap/drag
    /// use RealityKit entity targeting, so this is nil until then.
    func placeableId(at viewPoint: CGPoint) -> String? { nil }

    func focus(on id: String) {
        guard let placeable = placeablesById[id] else { return }
        lookAt = Canvas3DProjection.scenePosition(placeable.position)
        updateCamera()
    }

    func fit() {
        let points = placeablesById.values.map { Canvas3DProjection.scenePosition($0.position) }
        guard !points.isEmpty else {
            lookAt = .zero
            arrangementSpan = Self.itemExtent
            distance = Self.defaultDistance
            updateCamera()
            return
        }
        let xValues = points.map(\.x), yValues = points.map(\.y), zValues = points.map(\.z)
        lookAt = SIMD3<Float>(
            (xValues.min()! + xValues.max()!) / 2,
            (yValues.min()! + yValues.max()!) / 2,
            (zValues.min()! + zValues.max()!) / 2
        )
        let span = max(xValues.max()! - xValues.min()!, yValues.max()! - yValues.min()!, zValues.max()! - zValues.min()!, 1)
        arrangementSpan = span
        setDistance(span * 1.4)
    }

    // MARK: - Camera (view drives these from orbit/pan/zoom gestures)

    /// Orbit yaw/pitch by a per-frame screen delta (clamped pitch, no gimbal flip).
    func orbit(byScreenDelta delta: CGSize) {
        yaw += Float(delta.width) * 0.008
        pitch = min(max(pitch + Float(delta.height) * 0.008, -1.15), 1.15)
        updateCamera()
    }

    /// Pan the look-at target across the camera's right/up plane; speed scales
    /// with distance so the pan feels constant at any zoom (ported from #3088).
    func pan(byScreenDelta delta: CGSize) {
        let speed = distance * 0.0022
        lookAt += (-cameraRight * Float(delta.width) + cameraUp * Float(delta.height)) * speed
        updateCamera()
    }

    func setDistance(_ value: Float) {
        // #4411: was clamped to a fixed 2.2…16 — about 7x, which is neither
        // enough to read a page nor enough to see a whole arrangement. The
        // bounds now come from the content.
        distance = CanvasZoomRange.clamp(
            value, arrangementSpan: arrangementSpan, itemExtent: Self.itemExtent
        )
        updateCamera()
    }

    var currentDistance: Float { distance }

    /// The world position at the camera's look-at target — where a newly-added
    /// item lands so it appears centred in front of the camera (#3090).
    var focusWorldPosition: SIMD3<Double> { Canvas3DProjection.worldPosition(lookAt) }

    /// A screen drag → a world delta in the camera's view plane, for dragging a
    /// card in 3D. ponytail: distance-scaled camera-plane heuristic (depth is the
    /// card's; exact feel is the calibration knob — tune with the flag on).
    func worldDragDelta(screenTranslation: CGSize) -> SIMD3<Double> {
        let speed = distance * 0.0022
        let delta = (cameraRight * Float(screenTranslation.width) - cameraUp * Float(screenTranslation.height)) * speed
        return SIMD3<Double>(Double(delta.x), Double(delta.y), Double(delta.z))
    }

    /// Move a card to a world position IN PLACE (visual-only, no diff) — live
    /// drag feedback; the controller persists the snapped row on release.
    func liveMove(id: String, toWorld world: SIMD3<Double>) {
        placeablesRoot.findEntity(named: id)?.position = Canvas3DProjection.scenePosition(world)
    }

    /// The placeable dropped ONTO at `world` (nearest by world proximity,
    /// excluding the dragged id) — drag-onto target resolution (#3086), the SAME
    /// resolver the 2D renderer uses.
    func dropTargetId(nearWorld world: SIMD3<Double>, excluding: String) -> String? {
        CanvasDropResolver.nearestId(
            to: world,
            among: placeablesById.map { (id: $0.key, position: $0.value.position) },
            excluding: excluding
        )
    }

    private var hoverTargetId: String?

    /// Highlight the current drop target while dragging over it (#3086) — a cheap
    /// scale bump, cleared on nil (bounded, no ring geometry).
    func setHoverTarget(_ id: String?) {
        guard id != hoverTargetId else { return }
        if let previous = hoverTargetId { placeablesRoot.findEntity(named: previous)?.scale = .one }
        hoverTargetId = id
        if let id { placeablesRoot.findEntity(named: id)?.scale = SIMD3<Float>(repeating: 1.12) }
    }

    private var cameraRight: SIMD3<Float> { SIMD3<Float>(cos(yaw), 0, -sin(yaw)) }
    private var cameraUp: SIMD3<Float> {
        SIMD3<Float>(-sin(yaw) * sin(pitch), cos(pitch), -cos(yaw) * sin(pitch))
    }

    private func updateCamera() {
        let offset = SIMD3<Float>(
            sin(yaw) * cos(pitch) * distance,
            sin(pitch) * distance,
            cos(yaw) * cos(pitch) * distance
        )
        camera.position = lookAt + offset
        camera.look(at: lookAt, from: camera.position, relativeTo: nil)
    }

    // MARK: - Op application (granular; never a rebuild)

    private func applyOne(_ operation: CanvasSceneOp) {
        switch operation {
        case .insert(let placeable):
            placeablesById[placeable.id] = placeable
            placeablesRoot.addChild(makeCard(placeable))
        case .move(let id, let position):
            // Don't fight a local drag: a store echo for the dragged id is skipped
            // (the isDragSuppressed seam); every other move repositions in place.
            guard isDragSuppressed?(id) != true else { return }
            placeablesById[id]?.position = position
            placeablesRoot.findEntity(named: id)?.position = Canvas3DProjection.scenePosition(position)
        case .resize(let id, let size):
            placeablesById[id]?.size = size
            reskinCard(id)
        case .updateContent(let id):
            reskinCard(id)
        case .remove(let id):
            placeablesById[id] = nil
            placeablesRoot.findEntity(named: id)?.removeFromParent()
        case .setEdges(let edges):
            rebuildEdges(edges)
        case .setSelection(let newSelection):
            let changed = selection.symmetricDifference(newSelection)
            selection = newSelection
            for id in changed { reskinCard(id) }
        }
    }

    // MARK: - Cards

    private static let defaultCardSize = CGSize(width: 0.8, height: 0.6)

    private func reskinCard(_ id: String) {
        guard let placeable = placeablesById[id] else { return }
        placeablesRoot.findEntity(named: id)?.removeFromParent()
        placeablesRoot.addChild(makeCard(placeable))
    }

    private func makeCard(_ placeable: CanvasPlaceable) -> ModelEntity {
        let size = placeable.size ?? Self.defaultCardSize
        // Source cards take their page's true aspect once the texture has
        // loaded (#4193), area-normalized to the configured card footprint;
        // the fallback keeps the configured shape until then so cards don't
        // jump mid-load. makeCard consults the memo so selection reskins and
        // scene diffs keep the true shape.
        let (width, height) = CanvasCardGeometry.dimensions(
            area: Float(size.width) * Float(size.height),
            aspect: sourceId(of: placeable).flatMap { CanvasCardGeometry.knownAspect(forSourceId: $0) },
            fallback: Float(size.width) / Float(size.height)
        )
        let depth: Float = 0.04
        let mesh = MeshResource.generateBox(size: SIMD3<Float>(width, height, depth), cornerRadius: min(width, height) * 0.08)
        let entity = ModelEntity(mesh: mesh, materials: [SimpleMaterial(color: baseColor(for: placeable.content), isMetallic: false)])
        entity.name = placeable.id
        entity.position = Canvas3DProjection.scenePosition(placeable.position)
        entity.components.set(InputTargetComponent())
        entity.components.set(CollisionComponent(shapes: [.generateBox(size: SIMD3<Float>(width, height, depth))]))
        entity.components.set(HoverEffectComponent())

        if selection.contains(placeable.id) {
            entity.addChild(makeSelectionOutline(width: width, height: height, depth: depth))
        }
        if case .node(let node) = placeable.content,
           let sourceId = node.sourceId, !sourceId.isEmpty,
           node.nodeType == .source, detailTier >= .thumbnail {
            loadThumbnail(sourceId: sourceId, into: entity)
        }
        return entity
    }

    /// A slightly larger accent box sitting just behind a selected card — the 3D
    /// selection frame (a CHILD entity, so it doesn't replace the card's model).
    private func makeSelectionOutline(width: Float, height: Float, depth: Float) -> ModelEntity {
        let mesh = MeshResource.generateBox(
            size: SIMD3<Float>(width + 0.06, height + 0.06, depth * 0.5),
            cornerRadius: (width + 0.06) * 0.1
        )
        let outline = ModelEntity(mesh: mesh, materials: [UnlitMaterial(color: PlatformColor.controlAccentColorCompat3D)])
        outline.position = SIMD3<Float>(0, 0, -depth)   // behind the card face
        return outline
    }

    private func loadThumbnail(sourceId: String, into entity: ModelEntity) {
        Task { @MainActor in
            do {
                let texture = try await SpaceTextureCache.shared.texture(forSourceId: sourceId)
                // First load: memoize the true aspect and rebuild the card
                // once (#4193) — makeCard reads the memo, so the rebuilt card
                // (mesh, collision, selection outline) takes the page's real
                // shape and later reskins keep it. The rebuild's own reload
                // is a cache hit that records no change, so this terminates.
                if CanvasCardGeometry.recordAspect(of: texture, forSourceId: sourceId) {
                    reskinCard(entity.name)
                } else {
                    entity.model?.materials = [UnlitMaterial(texture: texture)]
                }
            } catch {
                log.debug("space thumbnail load failed for \(sourceId, privacy: .public)")
            }
        }
    }

    /// The page-image source id for a source-node placeable, nil otherwise.
    private func sourceId(of placeable: CanvasPlaceable) -> String? {
        guard case .node(let node) = placeable.content,
              node.nodeType == .source,
              let sourceId = node.sourceId, !sourceId.isEmpty else { return nil }
        return sourceId
    }

    private func baseColor(for content: CanvasContent) -> PlatformColor {
        switch content {
        case .node(let node): return SpaceTheme.materialColor(for: node.nodeType)
        case .item(let item): return Self.itemColor(for: item.kind)
        }
    }

    private static func itemColor(for kind: Components.Schemas.CanvasItemKind) -> PlatformColor {
        switch kind {
        case .note: .systemOrange
        case .quote: .systemPurple
        case .workNote: .systemBlue
        case .text: .systemGray
        case .link: .systemGray
        }
    }

    // MARK: - Edges (cylinders between xyz endpoints; rebuilt wholesale)

    private func rebuildEdges(_ edges: [CanvasEdge]) {
        edgesRoot.children.forEach { $0.removeFromParent() }
        for edge in edges {
            guard
                let source = placeablesById[edge.sourceId].map({ Canvas3DProjection.scenePosition($0.position) }),
                let target = placeablesById[edge.targetId].map({ Canvas3DProjection.scenePosition($0.position) })
            else { continue }
            edgesRoot.addChild(makeConnector(from: source, to: target, style: edge.style))
        }
    }

    /// A thin cylinder spanning two 3D points — reads as a tube from any orbit
    /// angle (the 3D twin of the 2D flat connector).
    private func makeConnector(from source: SIMD3<Float>, to target: SIMD3<Float>, style: CanvasEdgeStyle) -> ModelEntity {
        let delta = target - source
        let length = max(simd_length(delta), 0.0001)
        let mesh = MeshResource.generateCylinder(height: length, radius: 0.008)
        let entity = ModelEntity(mesh: mesh, materials: [SimpleMaterial(color: connectorColor(style), isMetallic: false)])
        entity.position = (source + target) / 2
        entity.orientation = simd_quatf(from: SIMD3<Float>(0, 1, 0), to: delta / length)
        return entity
    }

    private func connectorColor(_ style: CanvasEdgeStyle) -> PlatformColor {
        switch style {
        case .connection(let linkType): SpaceTheme.materialColor(for: linkType, alpha: linkType.isSolid ? 0.85 : 0.45)
        case .userLink: .systemGray
        }
    }
}

// MARK: - Accent colour shim

private extension PlatformColor {
    static var controlAccentColorCompat3D: PlatformColor {
        #if canImport(AppKit)
        return .controlAccentColor
        #else
        return .tintColor
        #endif
    }
}
