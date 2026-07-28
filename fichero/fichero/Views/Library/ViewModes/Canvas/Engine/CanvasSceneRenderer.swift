import CoreGraphics
import Foundation

// MARK: - Renderer protocol (#3103)

/// What every canvas renderer implements. The contract fixes the MEANING (ops,
/// reconcile, hit-testing, drag feedback, camera intents, zoom); the projection
/// and camera *implementation* stay renderer-local (2D ortho pan/zoom vs 3D
/// orbit/pan/zoom). A renderer is a thin skin over `CanvasSceneState`.
///
/// The reconcile/drag members below were already implemented IDENTICALLY by both
/// renderers and reached concretely by both hosts; declaring them here describes
/// what was already true rather than imposing a shape (#4192). It matters
/// because a partial contract with a concrete back-channel makes a third
/// renderer expensive — and cheap conformers are the whole mitigation for
/// SceneKit's maintenance status.
/// What the protocol deliberately does NOT carry: the object a renderer hands
/// its view layer. RealityKit gives `RealityView` an `Entity`; SceneKit puts an
/// `SCNScene` inside an `SCNView`. There is no common supertype worth inventing,
/// so **view hosting stays concrete per renderer, permanently** — each renderer
/// pairs with its own thin host view. This asymmetry is a boundary with a
/// reason, not an oversight to be tidied away later. (#4192)
@MainActor
protocol CanvasSceneRenderer: AnyObject {
    /// Apply granular scene ops to the live scene — never rebuild it.
    func apply(_ ops: [CanvasSceneOp])

    /// Reconcile the live scene to `newState` via the minimal diff against the
    /// last applied state. Never rebuilds — the renderer owns the `from` side.
    func reconcile(to newState: CanvasSceneState)

    /// How much of a card to draw, derived by the host from `reportedZoomScale`.
    /// Gates thumbnail fetches so a zoomed-out overview issues zero requests.
    var detailTier: CanvasDetailTier { get set }

    /// True while the host is mid-drag on `id`, so a store-echo `.move` for it
    /// is skipped — don't-fight-the-gesture.
    var isDragSuppressed: ((String) -> Bool)? { get set }

    /// Move a card to a world position IN PLACE — pure visual feedback while a
    /// drag is live, without touching the applied state.
    func liveMove(id: String, toWorld world: SIMD3<Double>)

    /// The placeable dropped ONTO at `world` (nearest by world proximity,
    /// excluding the dragged id), or nil for empty space.
    func dropTargetId(nearWorld world: SIMD3<Double>, excluding: String) -> String?

    /// Highlight the current drop target while dragging over it; nil clears.
    func setHoverTarget(_ id: String?)

    /// The placeable id under a view-space point (hit-test), or nil for empty
    /// space. Drives tap-select and drag-onto-item target resolution.
    ///
    /// Both RealityKit renderers return nil: their hosts pick the drag/tap
    /// subject with `.targetedToAnyEntity()` and never call this. It is the seam
    /// a host WITHOUT entity targeting hit-tests through, so returning nil means
    /// "this renderer doesn't hit-test" rather than "there is nothing there".
    func placeableId(at viewPoint: CGPoint) -> String?

    /// Animate the camera to frame a placeable.
    func focus(on id: String)

    /// Frame the whole scene.
    func fit()

    /// Current zoom scale (1.0 = fit) — feeds `CanvasDetailTier.forZoomScale`.
    var reportedZoomScale: Double { get }

    /// Where the renderer emits user intents (tap / drag / add / …). The
    /// `CanvasInteractionController` owns the semantics; the renderer only emits.
    var onIntent: ((CanvasIntent) -> Void)? { get set }
}
