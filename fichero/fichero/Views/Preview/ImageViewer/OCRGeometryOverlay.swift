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

    @State private var hoverPoint: CGPoint?

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

                // Hover-only tracking (2026-08-12: "no way to see what the
                // text is in each bbox"). AppKit tracking areas deliver
                // mouseMoved by geometry, independent of hit-testing, so this
                // reads the cursor WITHOUT ever entering event routing.
                #if os(macOS)
                HoverPositionReader { point in hoverPoint = point }
                    .frame(width: geo.size.width, height: geo.size.height)
                #endif

                if let hit = hoveredBox(at: hoverPoint, in: geo.size),
                   !hit.box.text.isEmpty {
                    Text(hit.box.text)
                        .font(.caption)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 3)
                        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 4))
                        .fixedSize()
                        .offset(x: hit.rect.minX, y: max(0, hit.rect.minY - 26))
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
        }
        // The layer is ON by default (#4418). On a dense page the boxes cover
        // most of the image, and each has an opaque `.background`, so an
        // interactive overlay would swallow every drag meant for pan or for
        // drawing a region — this layer must stay OUT of hit-testing. The
        // hover text above doesn't violate that: `HoverPositionReader`'s
        // NSView returns nil from hitTest (event-transparent) and reads the
        // cursor via an NSTrackingArea, which AppKit delivers by geometry
        // regardless of hit-testing.
        .allowsHitTesting(false)
    }

    private func hoveredBox(
        at point: CGPoint?, in size: CGSize
    ) -> (box: OCRGeometryBox, rect: CGRect)? {
        guard let point else { return nil }
        for box in boxes {
            if let rect = BoundingBoxGeometry.viewRect(
                normalized: box.bbox, in: size, visible: visible
            ), rect.insetBy(dx: -2, dy: -2).contains(point) {
                return (box, rect)
            }
        }
        return nil
    }
}

#if os(macOS)
/// Reads the cursor position over its bounds WITHOUT participating in event
/// routing: `hitTest` returns nil so clicks and drags pass straight through
/// to the scroll view below, while an `NSTrackingArea` still delivers
/// mouseMoved by geometry. This is the "hover-only hit region" the inert-layer
/// rule above calls for.
private struct HoverPositionReader: NSViewRepresentable {
    /// Point in this view's top-left-origin coordinates; nil on exit.
    let onMove: (CGPoint?) -> Void

    func makeNSView(context: Context) -> HoverTrackingNSView {
        let view = HoverTrackingNSView()
        view.onMove = onMove
        return view
    }

    func updateNSView(_ view: HoverTrackingNSView, context: Context) {
        view.onMove = onMove
    }

    final class HoverTrackingNSView: NSView {
        var onMove: ((CGPoint?) -> Void)?

        override var isFlipped: Bool { true }  // top-left origin, matching SwiftUI

        override func hitTest(_ point: NSPoint) -> NSView? { nil }

        override func updateTrackingAreas() {
            super.updateTrackingAreas()
            trackingAreas.forEach(removeTrackingArea)
            addTrackingArea(
                NSTrackingArea(
                    rect: bounds,
                    options: [.mouseMoved, .mouseEnteredAndExited, .activeInKeyWindow],
                    owner: self,
                    userInfo: nil
                )
            )
        }

        override func mouseMoved(with event: NSEvent) {
            onMove?(convert(event.locationInWindow, from: nil))
        }

        override func mouseExited(with event: NSEvent) {
            onMove?(nil)
        }
    }
}
#endif

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
