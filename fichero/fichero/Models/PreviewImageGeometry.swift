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

/// Pane point ↔ normalized image point, through ONE published geometry.
///
/// The pointer path maps clicks IN through this and the overlays map boxes
/// OUT through `BoundingBoxGeometry.viewRect` with the same two rects — so
/// "the click hits the box it visually covers" holds by construction rather
/// than by two derivations happening to agree (2026-09-04, wrong-line
/// select: the AppKit side re-derived the drawn rect at event time and the
/// two mappings disagreed by a constant offset in the wild while every
/// isolated round-trip test passed).
enum PreviewPointerMapping {
    /// `panePoint` is in the scroll view's top-left space — the space
    /// `drawnFrame` is measured in. Returns nil until a layout pass has
    /// measured; a nil is "drop the event", never "guess a frame".
    static func normalized(
        panePoint point: CGPoint, geometry: PreviewImageGeometry
    ) -> CGPoint? {
        guard geometry.isMeasured else { return nil }
        let drawn = geometry.drawnFrame
        let visible = geometry.visible
        return CGPoint(
            x: visible.minX + (point.x - drawn.minX) / drawn.width * visible.width,
            y: visible.minY + (point.y - drawn.minY) / drawn.height * visible.height
        )
    }
}
