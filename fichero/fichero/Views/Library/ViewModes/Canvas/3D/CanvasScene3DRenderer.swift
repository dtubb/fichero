import FicheroAPIClient
import Foundation
import OSLog
import RealityKit
import simd
import SwiftUI

// MARK: - RealityKit 3D renderer (#3104)

/// The 3D 'Space' renderer — the orbiting twin of `CanvasOrtho2DRenderer`.
/// Same #3103 contract, same shared `CanvasInteractionController`, so 2D and 3D
/// behave identically (selection / drag / persist / CRUD); the ONLY differences
/// are renderer-local: an orbit/pan/zoom camera (ORTHOGRAPHIC for boards since
/// §18.1 defect 1, perspective still reachable via `projection`), the full xyz
/// projection (z USED, via `Canvas3DProjection`), and cylinder connectors.
///
/// Supersedes the internals of #3088's `SpaceSceneView`: scene content is driven
/// ONLY by `apply(_ ops:)` from `CanvasSceneDiff` (never the old
/// `layoutRevision`-bump + reposition-everything pass), and positions come
/// pre-resolved from `CanvasSceneState.resolve` (its `effectivePosition` moved
/// into the contract — no local copy).
@MainActor
final class CanvasScene3DRenderer: CanvasSceneRenderer {
    // Internal, not private: the thumbnail extension file needs it and
    // Swift's `private` is FILE-scoped (same trade as +Selection).
    let log = Logger(subsystem: "app.fichero.fichero", category: "CanvasScene3DRenderer")

    let root = Entity()
    let placeablesRoot = Entity()
    private let edgesRoot = Entity()
    /// Selection decoration, owned separately for the same reason as 2D
    /// (#4409): drawing it inside `makeCard` forced a card REBUILD on every
    /// selection change, which dropped the loaded page texture and flashed the
    /// flat base colour. The affordances differ — 3D draws NO resize handles,
    /// because an axis-handle gizmo in a perspective scene is a separate design
    /// decision and an affordance that does nothing is worse than none — but
    /// the MODEL is shared, which is what #4409 asks for.
    let decorator = CanvasSelectionDecorator(
        showsHandles: false, accentColor: .controlAccentColorCompat3D
    )
    /// A plain `Entity`, not a `PerspectiveCamera`: which camera component it
    /// carries is the shell's choice (`projection`), and swapping components on
    /// one entity keeps the orbit rig — position, look-at, distance — untouched.
    let camera = Entity()

    /// How the board is projected. ORTHOGRAPHIC by default (§18.1 defect 1):
    /// zoomed out to a whole diary, a perspective camera rendered 2,228 cards
    /// as a tapering wedge — two identical pages at different depths came out
    /// different sizes, so nothing could be compared and the field's shape was
    /// an artifact of the camera rather than of the data.
    ///
    /// Perspective stays available, on the SHELL and not on the arrangement,
    /// because it is exactly right for the panel-sequence and station-walk
    /// shells §18.1 reserves it for — there depth carries the sequence and
    /// foreshortening is the cue. Those shells are not built here.
    var projection: CanvasCameraProjection = .orthographic {
        didSet { if projection != oldValue { updateCamera() } }
    }

    /// Internal rather than private, as are `placeablesRoot` and `decorator`:
    /// the selection half of this renderer lives in
    /// `CanvasScene3DRenderer+Selection.swift` and Swift's `private` is
    /// FILE-scoped, so an extension in another file cannot see it.
    var placeablesById: [String: CanvasPlaceable] = [:]
    var selection: Set<String> = []

    /// WHAT each card is, in colour (§20.3 Colour by). Held for the same
    /// reason as `emphasis`: a card inserted or reskinned while a colouring is
    /// live must arrive already coloured.
    var tint: CanvasTint = .neutral

    /// Whether a card currently carries a page image — a textured card keeps
    /// its page, so the tint yields to legibility (see `CanvasTintPainter`).
    func isTextured(_ id: String) -> Bool {
        guard detailTier >= .thumbnail, let placeable = placeablesById[id] else { return false }
        return sourceId(of: placeable).flatMap { CanvasCardGeometry.knownAspect(forSourceId: $0) } != nil
    }

    /// Seconds a `.move` animates for, set per diff by `apply`. Internal, not
    /// private: `applyMove` lives in +Ops.swift and `private` is FILE-scoped.
    var moveDuration = CanvasMoveAnimation.feedbackDuration

    /// WHICH cards matter right now — a search's heat map or an entity
    /// highlight. Held so a card INSERTED while emphasis is live is painted on
    /// arrival instead of staying bright until the next emphasis change.
    var emphasis: CanvasEmphasis = .neutral

    private var appliedState = CanvasSceneState.empty

    // Orbit camera state (renderer-local, ported from the proven #3088 rig).
    var yaw: Float = 0
    var pitch: Float = 0.35
    var distance: Float = 6
    var lookAt = SIMD3<Float>(0, 0, 0)
    static let defaultDistance: Float = 6
    // internal: read by the +Camera extension file (split for file_length).
    /// Extent of one placeable in scene units — the basis for how close the
    /// camera may get before an item is legible (#4411).
    static let itemExtent: Float = 1

    /// Span of the current arrangement, refreshed whenever placeables change.
    /// The zoom-out bound derives from THIS rather than a constant, so "as far
    /// out as it goes" and "everything fits" are the same place.
    var arrangementSpan: Float = 1

    /// Set by the host when a scope opens: the FIRST reconcile that produces
    /// any content frames it, once, then clears the flag — the same shape the
    /// 2D renderer uses, for the same reason. Consumed inside `reconcile` so it
    /// cannot fire before the placeables it is meant to frame exist.
    var needsFitOnNextContent = false

    var detailTier: CanvasDetailTier = .thumbnail
    var onIntent: ((CanvasIntent) -> Void)?
    var isDragSuppressed: ((String) -> Bool)?
    /// The CURRENT library's storage service — the texture cache's fallback
    /// is the GLOBAL library, which made every other library's 3D canvas
    /// fail all 1,500 thumbnail loads silently (log audit 2026-08-19).
    var storageService: StorageService?

    /// Closer camera → larger reported zoom, so `CanvasDetailTier` swaps in
    /// thumbnails / full textures as the user flies in (same rule as 2D).
    var reportedZoomScale: Double { Double(Self.defaultDistance / distance) }

    init() {
        root.addChild(placeablesRoot)
        root.addChild(edgesRoot)
        root.addChild(decorator.root)
        updateCamera()
    }

    // MARK: - CanvasSceneRenderer

    func apply(_ ops: [CanvasSceneOp]) {
        // Cards moving TOGETHER are a transition to watch; one echoing in from
        // another window is feedback (R10 / §20.2).
        moveDuration = CanvasMoveAnimation.duration(for: ops)
        for operation in ops { applyOne(operation) }
        if !ops.isEmpty { refreshSelectionDecoration() }
    }

    func reconcile(to newState: CanvasSceneState) {
        apply(CanvasSceneDiff.compute(from: appliedState, to: newState))
        appliedState = newState
        refreshArrangementSpan()
        if needsFitOnNextContent, !placeablesById.isEmpty {
            needsFitOnNextContent = false
            fit()
        }
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
        guard let bounds = currentBounds else {
            lookAt = .zero
            arrangementSpan = Self.itemExtent
            distance = Self.defaultDistance
            updateCamera()
            return
        }
        lookAt = bounds.center
        // Before `setDistance`, which clamps against it.
        arrangementSpan = bounds.span
        setDistance(bounds.span * 1.4)
    }

    private var currentBounds: (center: SIMD3<Float>, span: Float)? {
        CanvasArrangementBounds.of(
            placeablesById.values.map { Canvas3DProjection.scenePosition($0.position) },
            itemExtent: Self.itemExtent
        )
    }

    /// Re-derive the zoom-out ceiling from the arrangement as it stands now.
    ///
    /// #4411's fix replaced the 2.2…16 constants with content-derived bounds
    /// but left `arrangementSpan` assigned in exactly one place — `fit()`,
    /// which had no caller. So the span stayed at one item's extent forever and
    /// `maxDistance` collapsed to `defaultDistance`: precisely where the camera
    /// starts. Zoom IN reached a page, and zoom OUT did nothing at all, which
    /// is a narrower ceiling than the constant it replaced.
    ///
    /// Deliberately does NOT re-clamp `distance`. Widening the range never
    /// invalidates where the camera already is, and narrowing it — items
    /// deleted — would yank the view without the user asking for it; the next
    /// pinch clamps into the new range on its own.
    private func refreshArrangementSpan() {
        arrangementSpan = currentBounds?.span ?? Self.itemExtent
    }

    // MARK: - Camera (view drives these from orbit/pan/zoom gestures)

    /// Orbit yaw/pitch by a per-frame screen delta (clamped pitch, no gimbal flip).
    func orbit(byScreenDelta delta: CGSize) {
        yaw += Float(delta.width) * 0.008
        pitch = min(max(pitch + Float(delta.height) * 0.008, -1.15), 1.15)
        updateCamera()
    }

    /// The world position at the camera's look-at target — where a newly-added
    /// item lands so it appears centred in front of the camera (#3090).
    var focusWorldPosition: SIMD3<Double> { Canvas3DProjection.worldPosition(lookAt) }

    /// Move a card to a world position IN PLACE (visual-only, no diff) — live
    /// drag feedback; the controller persists the snapped row on release.
    func liveMove(id: String, toWorld world: SIMD3<Double>) {
        placeablesRoot.findEntity(named: id)?.position = Canvas3DProjection.scenePosition(world)
        // The frame travels with the card, or dragging a selected card looks
        // like losing the selection.
        if selection.contains(id) { refreshSelectionDecoration() }
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

    var cameraRight: SIMD3<Float> { SIMD3<Float>(cos(yaw), 0, -sin(yaw)) }
    var cameraUp: SIMD3<Float> {
        SIMD3<Float>(-sin(yaw) * sin(pitch), cos(pitch), -cos(yaw) * sin(pitch))
    }

    // MARK: - Op application (granular; never a rebuild)

    // MARK: - Cards

    static let defaultCardSize = CGSize(width: 0.8, height: 0.6)

    func reskinCard(_ id: String) {
        guard let placeable = placeablesById[id] else { return }
        placeablesRoot.findEntity(named: id)?.removeFromParent()
        let card = makeCard(placeable)
        // A rebuilt card is a NEW entity, so it carries none of the old one's
        // components — without this, a card that reskins mid-search (its
        // thumbnail landing, a resize) would come back at full strength while
        // its dimmed neighbours stayed dim.
        CanvasEmphasisPainter.apply(emphasis, to: card, id: id)
        placeablesRoot.addChild(card)
    }

    // Internal, not private: the op-application extension (+Ops.swift) needs
    // it and Swift's `private` is FILE-scoped — the same trade documented on
    // CanvasSceneView's split state.
    func makeCard(_ placeable: CanvasPlaceable) -> ModelEntity {
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
        let mesh = MeshResource.generateBox(
            size: SIMD3<Float>(width, height, depth), cornerRadius: min(width, height) * 0.08
        )
        let entity = ModelEntity(
            mesh: mesh,
            materials: [SimpleMaterial(color: cardColor(for: placeable), isMetallic: false)]
        )
        entity.name = placeable.id
        entity.position = Canvas3DProjection.scenePosition(placeable.position)
        entity.components.set(InputTargetComponent())
        entity.components.set(CollisionComponent(shapes: [.generateBox(size: SIMD3<Float>(width, height, depth))]))
        entity.components.set(HoverEffectComponent())

        // No selection decoration on the card, deliberately — see `decorator`.
        if case .node(let node) = placeable.content,
           let sourceId = node.sourceId, !sourceId.isEmpty,
           node.nodeType == .source, detailTier >= .thumbnail {
            loadThumbnail(sourceId: sourceId, into: entity)
        }
        return entity
    }

    /// The colour a card is built with: the tint channel's answer when it has
    /// one, else the card's kind tint — which IS the default "colour by kind",
    /// not a competing encoding.
    func cardColor(for placeable: CanvasPlaceable) -> PlatformColor {
        tint.slot(for: placeable.id).map(CanvasTintPainter.color(forSlot:))
            ?? baseColor(for: placeable.content)
    }

    // Internal, not private: the op-application extension needs it to repaint
    // a card when the colouring changes, and Swift's `private` is FILE-scoped.
    func baseColor(for content: CanvasContent) -> PlatformColor {
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

    // Internal, not private: the op-application extension (+Ops.swift) needs
    // it and Swift's `private` is FILE-scoped — the same trade documented on
    // CanvasSceneView's split state.
    func rebuildEdges(_ edges: [CanvasEdge]) {
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
    private func makeConnector(
        from source: SIMD3<Float>, to target: SIMD3<Float>, style: CanvasEdgeStyle
    ) -> ModelEntity {
        let delta = target - source
        let length = max(simd_length(delta), 0.0001)
        let mesh = MeshResource.generateCylinder(height: length, radius: 0.008)
        let entity = ModelEntity(
            mesh: mesh, materials: [SimpleMaterial(color: connectorColor(style), isMetallic: false)]
        )
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
