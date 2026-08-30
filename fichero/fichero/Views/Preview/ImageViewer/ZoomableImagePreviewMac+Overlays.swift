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
                // Entry-source highlight FIRST — a soft wash BEHIND the word
                // boxes, visually distinct from annotation regions (Daniel,
                // 2026-08-21: "wrong color… it should be behind words").
                // Where it lands is the anchor DATA's problem (Step-4
                // re-anchor); how it reads is this layer's.
                ForEach(Array(highlightBoxes.enumerated()), id: \.offset) { _, box in
                    if let rect = BoundingBoxGeometry.viewRect(
                        normalized: box,
                        in: geometry.drawnFrame.size,
                        visible: geometry.visible
                    ) {
                        RoundedRectangle(cornerRadius: 3)
                            .fill(Color.yellow.opacity(0.22))
                            .frame(width: rect.width, height: rect.height)
                            .offset(x: rect.minX, y: rect.minY)
                            .allowsHitTesting(false)
                    }
                }
                // Words lit by the READER's text selection (2026-08-23
                // linking) — sharper than the entry wash so the specific
                // words read against it.
                ForEach(Array(linkedSelectionBoxes.enumerated()), id: \.offset) { _, box in
                    if let rect = BoundingBoxGeometry.viewRect(
                        normalized: box,
                        in: geometry.drawnFrame.size,
                        visible: geometry.visible
                    ) {
                        RoundedRectangle(cornerRadius: 2)
                            .fill(Color.accentColor.opacity(0.28))
                            .frame(width: rect.width, height: rect.height)
                            .offset(x: rect.minX, y: rect.minY)
                            .allowsHitTesting(false)
                    }
                }
                // Saved bounding boxes + the region-draw layer (#2458).
                // Shown whenever there are boxes or the tool is armed.
                if !regionBoxes.isEmpty || isDrawingRegion {
                    BoundingBoxOverlay(
                        boxes: regionBoxes,
                        visible: geometry.visible,
                        isDrawing: isDrawingRegion,
                        onCreate: { box in createAnnotation(box: box, tool: pendingAnnotationTool) }
                    )
                }
                // OCR text boxes from the transcription pass (#4309),
                // toggled from the reader toolbar. FRAME GATE (2026-08-23,
                // entry-scoped runs): a box set naming a rendition_id was
                // measured on THAT rendition's pixels — drawing it over any
                // other image places plausible boxes in the wrong frame, the
                // same defect class as the misplaced spread band. nil means
                // the document's own image; non-nil draws only when that
                // exact rendition is what's on screen.
                if ocrBoxesEnabled, let ocrGeometry,
                   geometryFrameMatchesDisplay(ocrGeometry) {
                    OCRGeometryOverlay(
                        geometry: ocrGeometry,
                        visible: geometry.visible
                    )
                }
                // Regions as first-class (2026-08-29): the INTERACTIVE layer
                // — click-to-select, ⇧-click, drag-to-move, rubber-band add,
                // marquee display. Above the inert canvas; builds views only
                // for the few SELECTED boxes, so the one-Canvas perf fix
                // stands.
                regionInteractionLayer
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

extension ZoomableImagePreview {
    // Moved from the main file 2026-08-23 (file/type length): same member.
    var readerToolbar: some View {
        ReaderToolbar(
            pageNav: imagePageNav,
            renditionNav: renditionNav,
            scalePercent: Int(scale * 100),
            zoomIn: zoomIn,
            zoomOut: zoomOut,
            fitToWindow: fitToWindow,
            actualSize: actualSize,
            magnifierEnabled: $magnifierEnabled,
            textBoxesEnabled: $ocrBoxesEnabled,
            loupeEnabled: $loupeEnabled,
            loupeLocked: $loupeLocked,
            loupeMagnification: $loupeMagnification,
            isEditing: isEditing,
            onAnnotate: requestAnnotation
        )
    }
}

#endif
