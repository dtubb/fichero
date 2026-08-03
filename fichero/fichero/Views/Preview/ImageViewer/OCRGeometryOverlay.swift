import SwiftUI

/// Draws the transcription's word/line boxes over the page image (#4309).
///
/// A sibling of `BoundingBoxOverlay` (user annotation regions): this layer
/// renders the OCR geometry captured on the vision pass — normalized
/// top-left-origin `[x, y, w, h]` rects — inside the currently visible
/// zoom/pan window — showing where the transcription believes text is, which
/// is what makes it checkable rather than merely trusted.
struct OCRGeometryOverlay: View {
    let geometry: OCRGeometry
    /// Normalized sub-rect of the image currently visible (zoom/pan window).
    let visible: CGRect

    /// Words when the pass produced them; lines otherwise (never both at
    /// once — nested rectangles read as clutter, not structure).
    private var boxes: [OCRGeometryBox] {
        let words = geometry.wordBoxes
        return words.isEmpty ? geometry.lineBoxes : words
    }

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .topLeading) {
                ForEach(boxes) { box in
                    if let rect = BoundingBoxGeometry.viewRect(
                        normalized: box.bbox, in: geo.size, visible: visible
                    ) {
                        RoundedRectangle(cornerRadius: 1.5)
                            .stroke(Color.accentColor.opacity(0.8), lineWidth: 1)
                            .background(Color.accentColor.opacity(0.08))
                            .frame(width: rect.width, height: rect.height)
                            .offset(x: rect.minX, y: rect.minY)
                            .accessibilityLabel("Recognized text: \(box.text)")
                    }
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
        }
        // The layer is now ON by default (#4418), which changes what
        // hit-testing costs. On a dense page the boxes cover most of the
        // image, and each one has an opaque `.background`, so an interactive
        // overlay would swallow every drag meant for pan or for drawing a
        // region — on exactly the transcribed pages where both matter most.
        // Its sibling `BoundingBoxOverlay` sidesteps this by only mounting
        // when armed; this layer is always mounted, so it must be inert.
        //
        // The cost is the hover tooltip that showed a box's recognised text.
        // Worth it: the boxes' POSITIONS are what make a transcription
        // checkable — where Vision found text and where it found none — and
        // the recognised text itself is already in the reader beside the page.
        // The accessibility labels below survive, so VoiceOver still reads it.
        //
        // ponytail: inert layer. If the tooltip is wanted back, it needs a
        // hover-only hit region (`.contentShape(.hoverEffect, …)`) rather than
        // flipping this to true, which is where the drag-swallowing came from.
        .allowsHitTesting(false)
    }
}

#if os(macOS)
extension ZoomableImagePreview {
    /// Fetch this page's typed geometry (#4309, repaired by #4418).
    ///
    /// List first (lean payload), then the single GET which carries geometry.
    /// Which artifact wins is `OCRGeometrySelection`'s decision, not this
    /// function's — see there for why it cannot be "the newest transcription"
    /// and cannot be "the text_geometry one" either.
    ///
    /// Probes candidates best-first and stops at the first that actually
    /// carries boxes, because an artifact of the right type can still be empty:
    /// the importer writes a zero-box `text_geometry` artifact for every
    /// scanned page on purpose.
    ///
    /// Lives here so the (large) preview struct body stays under the
    /// type-body-length budget.
    func loadOCRGeometry() async {
        ocrGeometry = nil
        guard ocrBoxesEnabled, let documentId, let artifactService else { return }
        do {
            // The probe itself lives on OCRGeometrySelection so the PDF surface
            // shares this exact decision rather than reimplementing it (#4418).
            ocrGeometry = try await OCRGeometrySelection.load(
                documentId: documentId,
                using: artifactService
            )
        } catch {
            // Surface in the log, render nothing — the toggle stays honest
            // (no boxes ≠ silent success).
            Self.logger.error(
                "OCR geometry load failed for \(documentId): \(String(describing: error))"
            )
        }
    }
}
#endif
