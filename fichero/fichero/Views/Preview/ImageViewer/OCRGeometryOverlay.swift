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

    /// Draw each word's recognised text INSIDE its box (Daniel, 2026-08-31).
    /// The hover readout answers "what does this ONE box say"; this answers
    /// "what does the machine think the whole page says" without leaving the
    /// image — which is the only way to see a bad page at a glance.
    @AppStorage("imagePreview.inlineTextEnabled") private var inlineTextEnabled = false

    @State private var hoverPoint: CGPoint?
    @Environment(\.colorScheme) private var colorScheme

    /// Words when the pass produced them; lines otherwise (never both at
    /// once — nested rectangles read as clutter, not structure). The ladder
    /// lives on `OCRGeometry.displayIndexedBoxes` so the interactive region
    /// layer hit-tests EXACTLY the boxes this canvas draws (2026-08-29).
    private var boxes: [OCRGeometryBox] {
        geometry.displayIndexedBoxes.map(\.box)
    }

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .topLeading) {
                // ONE Canvas, not one view per box (2026-08-28). This was a
                // `ForEach` building a RoundedRectangle with stroke,
                // background, frame, offset and an accessibility node PER BOX
                // — hundreds of views on a dense page, all re-laid-out every
                // frame because `geo.size` changes as you scroll or zoom.
                // Daniel: "when there are a lot of bounding boxes on words in
                // preview, scrolling is really slow if two fingers are used to
                // drag." A Canvas draws the same rectangles in a single pass
                // with no layout and no accessibility tree.
                //
                // Per-box VoiceOver labels go with it, deliberately: arrowing
                // through 400 unlabelled rectangles was never usable. The
                // hover readout still speaks individual words, and the layer
                // carries a summary instead.
                Canvas { context, size in
                    let stroke = Color.accentColor.opacity(0.8)
                    let wash = Color.accentColor.opacity(0.08)
                    // Inline text needs GROUND to read against (Daniel,
                    // 2026-08-31: "you need to fade, or make the word
                    // bounding box less transparent, so we can see it") —
                    // a mostly-opaque theme-matched plate under each word.
                    let plate = (colorScheme == .dark ? Color.black : Color.white)
                        .opacity(0.78)
                    for box in boxes {
                        guard let rect = BoundingBoxGeometry.viewRect(
                            normalized: box.bbox, in: size, visible: visible
                        ) else { continue }
                        let path = Path(roundedRect: rect, cornerRadius: 1.5)
                        if inlineTextEnabled, !box.text.isEmpty {
                            context.fill(path, with: .color(plate))
                        } else {
                            context.fill(path, with: .color(wash))
                        }
                        context.stroke(path, with: .color(stroke), lineWidth: 1)
                        // Inline text rides the SAME Canvas pass — the whole
                        // point of the 2026-08-28 one-Canvas fix was that a
                        // dense page must not become hundreds of laid-out
                        // views, and a per-word `Text` view would undo it.
                        if inlineTextEnabled, !box.text.isEmpty {
                            context.draw(Text(box.text).font(.caption), in: rect)
                        }
                    }
                }
                .frame(width: geo.size.width, height: geo.size.height)
                .allowsHitTesting(false)
                .accessibilityHidden(boxes.isEmpty)
                .accessibilityLabel("^[\(boxes.count) recognized text region](inflect: true)")

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
        ocrGeometryArtifactId = nil
        // Loads regardless of the boxes TOGGLE (2026-08-23): the reader's
        // word-selection linking needs the geometry even when the full box
        // layer is off — the toggle gates drawing that layer, not knowing.
        guard let documentId, let artifactService else { return }
        do {
            // The probe itself lives on OCRGeometrySelection so the PDF surface
            // shares this exact decision rather than reimplementing it (#4418).
            // The artifact id rides along (2026-08-29): the curation verbs
            // must address the artifact whose boxes are on screen.
            let selected = try await OCRGeometrySelection.loadSelected(
                documentId: documentId,
                using: artifactService
            )
            ocrGeometry = selected?.geometry
            ocrGeometryArtifactId = selected?.artifactId
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
