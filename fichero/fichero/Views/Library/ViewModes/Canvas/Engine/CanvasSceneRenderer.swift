import CoreGraphics
import Foundation

// MARK: - Renderer protocol (#3103)

/// What both the ortho-2D and perspective-3D RealityKit renderers implement. The
/// contract fixes the MEANING (ops, hit-testing, camera intents, zoom); the
/// projection and camera *implementation* stay renderer-local (2D ortho pan/zoom
/// vs 3D orbit/pan/zoom). A renderer is a thin skin over `CanvasSceneState`.
@MainActor
protocol CanvasSceneRenderer: AnyObject {
    /// Apply granular scene ops to the live scene — never rebuild it.
    func apply(_ ops: [CanvasSceneOp])

    /// The placeable id under a view-space point (hit-test), or nil for empty
    /// space. Drives tap-select and drag-onto-item target resolution.
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
