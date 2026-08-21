import CoreGraphics

/// The image's on-screen geometry for ONE layout pass: the normalized window
/// of the image currently visible, and where that image is actually drawn in
/// the pane.
///
/// These two rects describe the same crop and are only meaningful together —
/// `BoundingBoxOverlay` frames itself to `drawnFrame` while mapping boxes
/// through `visible`, so a frame rendered from a NEW `visible` and a STALE
/// `drawnFrame` puts every box in the wrong place. They used to travel as two
/// separate `@MainActor` writes, which let SwiftUI observe exactly that
/// mismatched pair on any frame during a pinch or scroll (2026-08-20 bbox
/// review, defect D3). Carrying them in one value makes the mismatch
/// unrepresentable in transit.
///
/// Kept free of SwiftUI/AppKit so the measurement rule is unit-testable
/// without a running view — the same reason `BoundingBoxGeometry` is pure.
struct PreviewImageGeometry: Equatable {
    /// Normalized (0…1) sub-rect of the image currently on screen.
    var visible: CGRect
    /// The image's drawn rect within the pane, top-left origin. Overlays frame
    /// to THIS, never the whole pane — at fit-with-letterbox a pane-spanning
    /// overlay draws normalized geometry into the gray margins.
    var drawnFrame: CGRect

    init(visible: CGRect = .zero, drawnFrame: CGRect = .zero) {
        self.visible = visible
        self.drawnFrame = drawnFrame
    }

    /// Nothing has been measured yet. Distinct from a legitimately empty
    /// viewport: overlays must render NOTHING in this state rather than
    /// falling back to the unit rect, which spans the whole pane and flashes
    /// boxes across it before the first layout pass (defect D5).
    static let unmeasured = PreviewImageGeometry()

    /// True once a layout pass has produced both rects with positive area.
    ///
    /// Both are required. A measured `visible` with an unmeasured `drawnFrame`
    /// would still frame the overlay to nothing, and an unmeasured `visible`
    /// gives the mapping a zero-width divisor.
    var isMeasured: Bool {
        visible.width > 0 && visible.height > 0
            && drawnFrame.width > 0 && drawnFrame.height > 0
    }
}
