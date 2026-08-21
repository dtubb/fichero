#if os(macOS)
import SwiftUI

extension ZoomableImagePreview {
    /// Both box overlays, framed to the DRAWN image rect — never the pane.
    /// Pane-spanning overlays put boxes in the letterbox (2026-08-12 bbox
    /// repro). `geometry.visible` and `geometry.drawnFrame` describe the same
    /// crop and arrive in one write, so the mapping stays consistent while
    /// panning — it used to be two independent writes, and the pair could
    /// disagree mid-gesture (2026-08-20 bbox review, D3).
    @ViewBuilder
    var boxOverlays: some View {
        // Nothing renders until a layout pass has measured BOTH rects
        // (2026-08-20 bbox review, D5). The old unit-rect fallback left the
        // overlay unframed before the first measurement — spanning the whole
        // pane — and mapped boxes against the full image, flashing them across
        // the pane on every image load. An unmeasured viewport is not a
        // viewport showing the whole image; drawing nothing for one frame is
        // the honest answer, and the Every Frame Perfect one.
        if geometry.isMeasured {
            ZStack(alignment: .topLeading) {
                // Saved bounding boxes + the region-draw layer (#2458).
                // Shown whenever there are boxes or the tool is armed.
                if !regionBoxes.isEmpty || !highlightBoxes.isEmpty || isDrawingRegion {
                    BoundingBoxOverlay(
                        boxes: regionBoxes + highlightBoxes,
                        visible: geometry.visible,
                        isDrawing: isDrawingRegion,
                        onCreate: { box in createAnnotation(box: box, tool: pendingAnnotationTool) }
                    )
                }
                // OCR text boxes from the transcription pass (#4309),
                // toggled from the reader toolbar.
                if ocrBoxesEnabled, let ocrGeometry {
                    OCRGeometryOverlay(
                        geometry: ocrGeometry,
                        visible: geometry.visible
                    )
                }
            }
            .frame(width: geometry.drawnFrame.width, height: geometry.drawnFrame.height)
            // Boxes never bleed past the drawn image into the letterbox or the
            // neighbouring panes (user, 2026-08-20: "they draw over the image
            // and sometimes into other views").
            .clipped()
            .offset(x: geometry.drawnFrame.minX, y: geometry.drawnFrame.minY)
        }
    }
}
#endif
