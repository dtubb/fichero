import FicheroAPIClient
import Foundation
import OSLog
import RealityKit
import simd
import SwiftUI

// MARK: - RealityKit ortho-2D renderer (#3083)

/// The 2D 'Canvas' renderer: a RealityKit scene with a native
/// `OrthographicCameraComponent` (macOS 15+) locked top-down, so it is a
/// true-flat plane with NO perspective. It is a thin skin over the #3103
/// contract — scene content is driven ONLY by `apply(_ ops:)` from
/// `CanvasSceneDiff` (never a rebuild), positions come pre-resolved in canonical
/// world space and are projected `(x, −y)` here, and it emits `CanvasIntent`s.
///
/// One RealityKit engine (SceneKit is deprecated on macOS 26): the perspective-3D
/// 'Space' renderer (#3104/#3090) is the SAME contract with a perspective camera.
///
/// #4192's text proposes SceneKit for the 2D map. The user corrected that on
/// 2026-07-28 — it rested on a misreading of what SceneKit is — so **2D stays
/// RealityKit and this renderer is where the Tinderbox-style map is built**.
/// Read the epic's SceneKit wording as superseded, not as work outstanding.
@MainActor
final class CanvasOrtho2DRenderer: CanvasSceneRenderer {
    // Internal, not private: the thumbnail extension file needs it and
    // Swift's `private` is FILE-scoped (same trade as +Selection).
    let log = Logger(subsystem: "app.fichero.fichero", category: "CanvasOrtho2DRenderer")

    /// Added to the `RealityView` content once, then mutated in place.
    let root = Entity()
    let placeablesRoot = Entity()
    private let edgesRoot = Entity()
    /// Selection decoration — frames, the set frame and resize handles.
    ///
    /// A SEPARATE object owning a SEPARATE root, never children of the cards,
    /// and that is the whole fix for #4409's blue flash: see
    /// `CanvasSelectionDecorator` for what the old card-owned arrangement cost.
    let decorator = CanvasSelectionDecorator(
        showsHandles: true, accentColor: .controlAccentColorCompat
    )
    let camera = Entity()

    /// Live placeable metadata (positions/content/size) so `.setEdges` can look
    /// up endpoints and reskins can rebuild a single card without a store
    /// round-trip.
    ///
    /// Internal rather than private, as are `selection` and the members below
    /// it: the selection / resize half of this renderer lives in
    /// `CanvasOrtho2DRenderer+Selection.swift` and Swift's `private` is
    /// FILE-scoped, so an extension in another file cannot see it. The same
    /// trade `LibraryView+CanvasModes.swift` made when #4353 forced that split.
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
    /// highlight. Held so a card inserted while emphasis is live is painted on
    /// arrival, not left bright until the next emphasis change.
    var emphasis: CanvasEmphasis = .neutral

    /// Live card size while a resize handle is being dragged — visual feedback
    /// only, cleared by the `.resize` op the release persists. Stored here
    /// because an extension cannot hold state; used from
    /// `CanvasOrtho2DRenderer+Selection.swift`.
    var liveSizeOverride: (id: String, size: CGSize)?
    /// The last state applied to the scene — the `from` side of every diff so a
    /// store change reconciles to a minimal op list instead of a rebuild.
    private var appliedState = CanvasSceneState.empty

    /// The ortho scale (world-units of vertical extent visible) at fit; the
    /// reported zoom scale is `default / current`, so zooming IN (smaller scale)
    /// reports a LARGER zoom to `CanvasDetailTier`.
    static let defaultOrthoScale: Float = 8
    private(set) var orthoScale: Float = defaultOrthoScale

    /// The detail tier the view derives from the reported zoom; gates thumbnail
    /// loads so a zoomed-out overview issues zero image requests.
    var detailTier: CanvasDetailTier = .thumbnail

    var onIntent: ((CanvasIntent) -> Void)?

    /// Set by the view: true while `id` is mid-drag, so a store-echo `.move` for
    /// it is skipped (don't-fight-the-gesture). Node drag lands in #3084; harmless
    /// now (always false), but the seam is here so the reconcile already honors it.
    var isDragSuppressed: ((String) -> Bool)?

    /// The CURRENT library's storage service, set by the hosting view — the
    /// texture cache's fallback is the GLOBAL library, which is the wrong
    /// library for every other canvas (user, live 2026-08-19).
    var storageService: StorageService?

    var reportedZoomScale: Double { Double(Self.defaultOrthoScale / orthoScale) }

    init() {
        root.addChild(placeablesRoot)
        root.addChild(edgesRoot)
        root.addChild(decorator.root)
        applyOrthoScale()
        // Top-down: camera on +Z looking down −Z at the z=0 content plane.
        camera.position = SIMD3<Float>(0, 0, 10)
    }

    // MARK: - CanvasSceneRenderer

    func apply(_ ops: [CanvasSceneOp]) {
        // Cards moving TOGETHER are a transition to watch; one echoing in from
        // another window is feedback (R10 / §20.2).
        moveDuration = CanvasMoveAnimation.duration(for: ops)
        for operation in ops { applyOne(operation) }
        // Decoration is derived from the cards, so it settles ONCE after the
        // whole op list rather than per-op: a batch that moves three selected
        // cards must not draw the set frame three times on its way to the
        // right answer.
        if !ops.isEmpty { refreshSelectionDecoration() }
    }

    /// Set by the host when a scope opens: the FIRST reconcile that produces any
    /// content fits the camera to it, once, then clears the flag.
    ///
    /// The default grid (#4290) is anchored at the world origin and marches right
    /// and down, so without this the camera — parked at `(0, 0)` — showed one
    /// quadrant of the board and the rest sat off-screen. Consumed inside
    /// `reconcile` rather than driven from the view so it cannot fire before the
    /// placeables it is meant to frame exist.
    var needsFitOnNextContent = false

    /// Reconcile the live scene to `newState` via the minimal diff against the
    /// last applied state — the view calls this whenever the resolved scene
    /// changes (a store patch, a selection change). Never rebuilds.
    func reconcile(to newState: CanvasSceneState) {
        apply(CanvasSceneDiff.compute(from: appliedState, to: newState))
        appliedState = newState
        if needsFitOnNextContent, !placeablesById.isEmpty {
            needsFitOnNextContent = false
            fit()
        }
    }

    /// Drag-onto-item target picking lands in #3086 (needs a scene raycast); tap
    /// and pan use RealityKit's own entity targeting, so this is nil until then.
    func placeableId(at viewPoint: CGPoint) -> String? { nil }

    func focus(on id: String) {
        guard let placeable = placeablesById[id] else { return }
        let point = Canvas2DProjection.scenePosition(placeable.position)
        camera.position = SIMD3<Float>(point.x, point.y, camera.position.z)
    }

    func fit() {
        let points = placeablesById.values.map { Canvas2DProjection.scenePosition($0.position) }
        guard !points.isEmpty else {
            camera.position = SIMD3<Float>(0, 0, camera.position.z)
            setOrthoScale(Self.defaultOrthoScale)
            return
        }
        let xValues = points.map(\.x), yValues = points.map(\.y)
        camera.position = SIMD3<Float>(
            (xValues.min()! + xValues.max()!) / 2,
            (yValues.min()! + yValues.max()!) / 2,
            camera.position.z
        )
        // Spans are CENTRE-to-centre, so add a cell of margin — otherwise the
        // outermost cards are half off-screen, and a single-card scope frames a
        // span of 0 (#4290).
        let margin = Float(CanvasGridPlacement.cellWidth)
        let span = max(xValues.max()! - xValues.min()!, yValues.max()! - yValues.min()!) + margin
        setOrthoScale(span * 0.6)
    }

    // MARK: - Camera control (view drives these from gestures)

    func setOrthoScale(_ scale: Float) {
        orthoScale = min(max(scale, 0.1), 200)  // 0.5→0.1 (2026-08-22): zoom close enough to read
        applyOrthoScale()
        // Zoom-constant selection chrome (#4601): redraw at the new ratio.
        refreshSelectionDecoration()
    }

    // MARK: - Drag + marquee (#3084)

    /// Move a card to a world position IN PLACE, no animation and WITHOUT
    /// touching `placeablesById`/`appliedState` — pure visual feedback while a
    /// drag is live. The controller persists the snapped row on release, and the
    /// resulting reconcile settles the card at its final (snapped) spot.
    func liveMove(id: String, toWorld world: SIMD3<Double>) {
        placeablesRoot.findEntity(named: id)?.position = Canvas2DProjection.scenePosition(world)
        // The frame belongs to the card, so it travels with it mid-drag —
        // otherwise dragging a selected card leaves its selection behind,
        // which reads as the selection having been lost.
        if selection.contains(id) { refreshSelectionDecoration() }
    }

    /// The placeable dropped ONTO at `world` (nearest by world proximity,
    /// excluding the dragged id) — drag-onto target resolution (#3086), the same
    /// resolver the 3D renderer uses.
    func dropTargetId(nearWorld world: SIMD3<Double>, excluding: String) -> String? {
        CanvasDropResolver.nearestId(
            to: world,
            among: placeablesById.map { (id: $0.key, position: $0.value.position) },
            excluding: excluding
        )
    }

    private var hoverTargetId: String?

    /// Highlight the current drop target while dragging over it (#3086) — a cheap
    /// scale bump, cleared on nil. No ring geometry (bounded).
    func setHoverTarget(_ id: String?) {
        guard id != hoverTargetId else { return }
        if let previous = hoverTargetId { placeablesRoot.findEntity(named: previous)?.scale = .one }
        hoverTargetId = id
        if let id { placeablesRoot.findEntity(named: id)?.scale = SIMD3<Float>(repeating: 1.12) }
    }

    /// The placeables whose projected screen point falls inside `rect` — the
    /// marquee hit-test. Uses the SAME `worldPerPoint` calibration as pan/drag,
    /// so tuning one tunes all three.
    func placeableIds(inScreenRect rect: CGRect, viewSize: CGSize) -> Set<String> {
        var result: Set<String> = []
        for (id, placeable) in placeablesById {
            let scene = Canvas2DProjection.scenePosition(placeable.position)
            let point = Canvas2DProjection.screenPoint(
                scene: scene,
                cameraX: camera.position.x,
                cameraY: camera.position.y,
                orthoScale: orthoScale,
                viewSize: viewSize
            )
            if rect.contains(point) { result.insert(id) }
        }
        return result
    }

    private func applyOrthoScale() {
        var ortho = OrthographicCameraComponent()
        ortho.scale = orthoScale
        camera.components.set(ortho)
    }

    // MARK: - Op application (granular; never a rebuild)

    // MARK: - Cards

    static let defaultCardSize = CGSize(width: 1.0, height: 0.75)

    // Internal, not private: `reskinCard` lives in the +Thumbnails file (this
    // one is at its file_length ceiling) and Swift's `private` is FILE-scoped.
    func makeCard(_ placeable: CanvasPlaceable) -> ModelEntity {
        let (width, height) = cardDimensions(placeable)
        let mesh = MeshResource.generatePlane(width: width, height: height, cornerRadius: min(width, height) * 0.08)
        let entity = ModelEntity(mesh: mesh, materials: [UnlitMaterial(color: cardColor(for: placeable))])
        entity.name = placeable.id
        entity.position = Canvas2DProjection.scenePosition(placeable.position)
        entity.components.set(InputTargetComponent())
        entity.components.set(CollisionComponent(shapes: [.generateBox(size: SIMD3<Float>(width, height, 0.02))]))
        entity.components.set(HoverEffectComponent())

        // NO selection decoration here, deliberately: a card that knows whether
        // it is selected must be rebuilt when that changes, and rebuilding a
        // textured card is #4409's blue flash. `CanvasSelectionVisualGuardTests`
        // pins this absence.
        if case .node(let node) = placeable.content,
           let sourceId = node.sourceId, !sourceId.isEmpty,
           node.nodeType == .source, detailTier >= .thumbnail {
            loadThumbnail(sourceId: sourceId, into: entity)
        }
        return entity
    }

    // Internal, not `private`: +Selection.swift calls it, and `private` is
    // FILE-scoped, so a type split across sibling files loses access.
    /// The page-image source id for a source-node placeable, nil otherwise.
    func sourceId(of placeable: CanvasPlaceable) -> String? {
        guard case .node(let node) = placeable.content,
              node.nodeType == .source,
              let sourceId = node.sourceId, !sourceId.isEmpty else { return nil }
        return sourceId
    }

    /// Load the page thumbnail through the storage service (never raw URLSession)
    /// and swap it onto the card when ready — mirrors the 3D texture path.
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
        case .node(let node):
            return SpaceTheme.materialColor(for: node.nodeType)
        case .item(let item):
            return Self.itemColor(for: item.kind)
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

    // MARK: - Edges (rebuilt wholesale — few and cheap, per the contract)

    // Internal, not private: the op-application extension (+Ops.swift) needs
    // it and Swift's `private` is FILE-scoped — the same trade documented on
    // CanvasSceneView's split state.
    func rebuildEdges(_ edges: [CanvasEdge]) {
        edgesRoot.children.forEach { $0.removeFromParent() }
        for edge in edges {
            guard
                let source = placeablesById[edge.sourceId].map({ Canvas2DProjection.scenePosition($0.position) }),
                let target = placeablesById[edge.targetId].map({ Canvas2DProjection.scenePosition($0.position) })
            else { continue }
            edgesRoot.addChild(makeConnector(from: source, to: target, style: edge.style))
        }
    }

    /// A thin FLAT rectangle in the z=0 plane between two points — the RealityKit
    /// twin of the 2D `Path` stroke (no 3D tube; true-flat for the ortho camera).
    private func makeConnector(
        from source: SIMD3<Float>, to target: SIMD3<Float>, style: CanvasEdgeStyle
    ) -> ModelEntity {
        let delta = SIMD2<Float>(target.x - source.x, target.y - source.y)
        let length = max(simd_length(delta), 0.0001)
        let thickness: Float = 0.02
        let mesh = MeshResource.generatePlane(width: length, height: thickness)
        let entity = ModelEntity(mesh: mesh, materials: [UnlitMaterial(color: connectorColor(style))])
        entity.position = SIMD3<Float>((source.x + target.x) / 2, (source.y + target.y) / 2, -0.02)
        entity.orientation = simd_quatf(angle: atan2(delta.y, delta.x), axis: SIMD3<Float>(0, 0, 1))
        return entity
    }

    private func connectorColor(_ style: CanvasEdgeStyle) -> PlatformColor {
        switch style {
        case .connection(let linkType): SpaceTheme.materialColor(for: linkType, alpha: 0.7)
        case .userLink: .systemGray
        }
    }
}

// MARK: - Accent colour shim

private extension PlatformColor {
    /// Cross-platform accent for the selection ring (`controlAccentColor` is
    /// macOS-only; iOS uses the tint).
    static var controlAccentColorCompat: PlatformColor {
        #if canImport(AppKit)
        return .controlAccentColor
        #else
        return .tintColor
        #endif
    }
}
