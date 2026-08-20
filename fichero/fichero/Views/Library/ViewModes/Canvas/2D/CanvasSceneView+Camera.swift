import RealityKit
import SwiftUI

// MARK: - Camera inputs (split from CanvasSceneView for type_body_length,
// 2026-08-20 — same members, only the file moved)

extension CanvasSceneView {
    /// Pan from a scroll delta (#4408).
    ///
    /// Scroll deltas are already per-event, so unlike a drag translation there
    /// is no baseline to subtract — but the conversion to world units is the
    /// SAME `cameraPanDelta` the drag uses, so both inputs stay calibrated
    /// together and tuning one tunes both.
    func scrollPanCamera(by delta: CGSize, in size: CGSize) {
        renderer.panCamera(
            worldDelta: Canvas2DProjection.cameraPanDelta(
                screenTranslation: delta,
                orthoScale: renderer.orthoScale,
                viewHeight: size.height
            )
        )
    }

    /// Advance the camera by the delta since the last pan event — `translation`
    /// is cumulative, so the baseline turns it into a per-event step.
    func panCamera(by translation: CGSize, in size: CGSize) {
        let delta = CGSize(
            width: translation.width - panBaseline.width,
            height: translation.height - panBaseline.height
        )
        panBaseline = translation
        // ponytail: shares Canvas2DProjection.worldPerPoint with drag +
        // marquee — the ONE calibration knob to tune against the built app.
        renderer.panCamera(
            worldDelta: Canvas2DProjection.cameraPanDelta(
                screenTranslation: delta,
                orthoScale: renderer.orthoScale,
                viewHeight: size.height
            )
        )
    }

    /// Visible affordance for pan mode: an open hand while Space is held, so the
    /// modifier is discoverable rather than folklore (#4290). Mirrors the divider
    /// cursor idiom in `ContentViewHelperViews`.
    func applyPanCursor(_ held: Bool) {
        #if canImport(AppKit)
        if held {
            NSCursor.openHand.set()
        } else {
            NSCursor.arrow.set()
        }
        #endif
    }

    /// Pinch zooms the ortho camera: magnify > 1 → zoom IN → smaller ortho scale.
    var zoom: some Gesture {
        MagnificationGesture()
            .onChanged { value in
                if zoomBaseline == 0 { zoomBaseline = renderer.orthoScale }
                renderer.setOrthoScale(
                    Canvas2DProjection.orthoScale(zoomBaseline: zoomBaseline, magnification: value)
                )
            }
            .onEnded { _ in zoomBaseline = 0 }
    }
}
