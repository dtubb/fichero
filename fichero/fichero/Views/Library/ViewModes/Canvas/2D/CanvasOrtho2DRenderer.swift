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
    private let log = Logger(subsystem: "app.fichero.fichero", category: "CanvasOrtho2DRenderer")

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
        orthoScale = min(max(scale, 0.5), 200)
        applyOrthoScale()
    }

    /// Pan the camera across its plane by a world-space delta.
    func panCamera(worldDelta: SIMD2<Float>) {
        camera.position += SIMD3<Float>(worldDelta.x, worldDelta.y, 0)
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

    private func applyOne(_ operation: CanvasSceneOp) {
        switch operation {
        case .insert(let placeable):
            placeablesById[placeable.id] = placeable
            placeablesRoot.addChild(makeCard(placeable))
        case .move(let id, let position):
            // Don't fight a local drag (#3084): a store echo for the id being
            // dragged is skipped; every other move animates to the new spot so a
            // cross-window / agent move glides rather than jumps (issue point 3).
            guard isDragSuppressed?(id) != true else { return }
            placeablesById[id]?.position = position
            if let entity = placeablesRoot.findEntity(named: id) {
                var transform = entity.transform
                transform.translation = Canvas2DProjection.scenePosition(position)
                entity.move(to: transform, relativeTo: entity.parent, duration: 0.18)
            }
        case .resize(let id, let size):
            placeablesById[id]?.size = size
            // Mesh + collision IN PLACE, keeping the materials — a `reskinCard`
            // here would drop the loaded page texture and flash the base colour
            // for exactly the same reason selection used to (#4409).
            resizeCardInPlace(id)
        case .updateContent(let id):
            reskinCard(id)
        case .remove(let id):
            placeablesById[id] = nil
            placeablesRoot.findEntity(named: id)?.removeFromParent()
        case .setEdges(let edges):
            rebuildEdges(edges)
        case .setSelection(let newSelection):
            // NOTHING happens to the cards. This used to `reskinCard` every id
            // in the symmetric difference — destroying and rebuilding a
            // textured card to add or remove a decoration — which is #4409's
            // blue flash and the no-wholesale-re-render rule broken at card
            // granularity. `refreshSelectionDecoration` (called once by
            // `apply`) redraws the frames instead.
            selection = newSelection
        }
    }

    // MARK: - Cards

    static let defaultCardSize = CGSize(width: 1.0, height: 0.75)

    private func reskinCard(_ id: String) {
        guard let placeable = placeablesById[id] else { return }
        placeablesRoot.findEntity(named: id)?.removeFromParent()
        placeablesRoot.addChild(makeCard(placeable))
    }

    private func makeCard(_ placeable: CanvasPlaceable) -> ModelEntity {
        let (width, height) = cardDimensions(placeable)
        let mesh = MeshResource.generatePlane(width: width, height: height, cornerRadius: min(width, height) * 0.08)
        let entity = ModelEntity(mesh: mesh, materials: [UnlitMaterial(color: baseColor(for: placeable.content))])
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
    private func loadThumbnail(sourceId: String, into entity: ModelEntity) {
        Task { @MainActor in
            do {
                let texture = try await SpaceTextureCache.shared.texture(forSourceId: sourceId)
                // First load: memoize the true aspect and rebuild the card
                // once (#4193) — makeCard reads the memo, so the rebuilt card
                // (mesh, collision, selection ring) takes the page's real
                // shape and later reskins keep it. The rebuild's own reload
                // is a cache hit that records no change, so this terminates.
                if CanvasCardGeometry.recordAspect(of: texture, forSourceId: sourceId) {
                    reskinCard(entity.name)
                } else {
                    entity.model?.materials = [UnlitMaterial(texture: texture)]
                }
            } catch {
                log.debug("canvas thumbnail load failed for \(sourceId, privacy: .public)")
            }
        }
    }

    private func baseColor(for content: CanvasContent) -> PlatformColor {
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

    private func rebuildEdges(_ edges: [CanvasEdge]) {
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
    private func makeConnector(from source: SIMD3<Float>, to target: SIMD3<Float>, style: CanvasEdgeStyle) -> ModelEntity {
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
