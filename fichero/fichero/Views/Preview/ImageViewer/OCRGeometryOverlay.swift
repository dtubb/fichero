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
                    let wash = Color.accentColor.opacity(0.08)
                    // Inline text needs GROUND to read against (Daniel,
                    // 2026-08-31: "you need to fade, or make the word
                    // bounding box less transparent, so we can see it") —
                    // a theme-matched plate under each word. Lightened to 0.6
                    // (Daniel, 2026-09-01): the word has to be legible, but
                    // the SCAN underneath it has to stay checkable — that is
                    // the whole point of drawing the transcription in place.
                    let plate = (colorScheme == .dark ? Color.black : Color.white)
                        .opacity(InlineWordText.plateOpacity)
                    for box in boxes {
                        guard let rect = BoundingBoxGeometry.viewRect(
                            normalized: box.bbox, in: size, visible: visible
                        ) else { continue }
                        let path = Path(roundedRect: rect, cornerRadius: 1.5)
                        // How sure the machine is about WHERE this word is
                        // (2026-09-04). `confidence` had been decoded and read
                        // by nothing, so a 0.30 box was drawn exactly as
                        // firmly as a 1.0 one — over a library where most
                        // boxes are the former. Recessive stroke plus a dash,
                        // so an uncertain box is still findable and no longer
                        // an assertion. Opacity and dash are THIS axis;
                        // provenance (measured / aligned / interpolated) is a
                        // different one and keeps the channels it has left.
                        let uncertain = OCRBoxConfidence.isUncertain(box)
                        let stroke = Color.accentColor
                            .opacity(OCRBoxConfidence.strokeOpacity(box.confidence))
                        let drawsText = inlineTextEnabled && !box.text.isEmpty
                            && OCRBoxConfidence.drawsInlineText(box.confidence)
                        if drawsText {
                            context.fill(path, with: .color(plate))
                        } else {
                            context.fill(path, with: .color(wash))
                        }
                        context.stroke(
                            path,
                            with: .color(stroke),
                            style: StrokeStyle(
                                lineWidth: 1, dash: uncertain ? [3, 2] : []
                            )
                        )
                        // Inline text rides the SAME Canvas pass — the whole
                        // point of the 2026-08-28 one-Canvas fix was that a
                        // dense page must not become hundreds of laid-out
                        // views, and a per-word `Text` view would undo it.
                        if drawsText {
                            // FILL the box (Daniel, 2026-09-01). A fixed
                            // `.caption` overflowed a short box and rattled
                            // around in a tall one; the word should look like
                            // the word it replaces, so the size comes from the
                            // box itself.
                            context.draw(
                                InlineWordText.fitted(box.text, in: rect, context: context),
                                in: rect
                            )
                        }
                    }
                }
                .frame(width: geo.size.width, height: geo.size.height)
                .allowsHitTesting(false)
                .accessibilityHidden(boxes.isEmpty)
                .accessibilityLabel(Self.accessibilitySummary(for: boxes))

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

    /// What the layer says to VoiceOver. The per-box nodes went away with the
    /// one-Canvas fix (2026-08-28), so this ONE label is the whole layer's
    /// account of itself — and a count that hides how much of it is guesswork
    /// is the same omission the uniform stroke was.
    static func accessibilitySummary(for boxes: [OCRGeometryBox]) -> String {
        let base = "^[\(boxes.count) recognized text region](inflect: true)"
        guard let doubt = OCRBoxConfidence.summary(for: boxes) else { return base }
        return "\(base), \(doubt)"
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

// MARK: - Inline word text

/// Sizing for the transcription drawn INSIDE each word box.
///
/// File-scoped rather than static members on the view: a `View`'s statics
/// inherit the type's `@MainActor` isolation, and these are read from the
/// `Canvas` draw closure.
private enum InlineWordText {
    /// Plate under an inline word — theme-matched, deliberately translucent
    /// (Daniel, 2026-09-01): legible word, still-checkable scan underneath.
    static let plateOpacity: Double = 0.6
    /// Below this the glyphs are mush; above it a one-letter box shouts.
    static let minFontSize: CGFloat = 5
    static let maxFontSize: CGFloat = 64
    /// Leaves a hairline of plate above and below the cap height.
    static let heightFillRatio: CGFloat = 0.82

    /// Resolves `string` at the largest size that fits `rect` in BOTH axes:
    /// take the size from the box HEIGHT (clamped), measure, then shrink by
    /// the width-overflow ratio when the word is too long for its box.
    /// Up to two corrective passes (Daniel, 2026-09-02: "never has
    /// ellipses"): font metrics are not perfectly linear, so the single
    /// ratio pass could land a hair over the box and the draw truncated
    /// with "…" — the one thing an in-place word must never do.
    static func fitted(
        _ string: String, in rect: CGRect, context: GraphicsContext
    ) -> GraphicsContext.ResolvedText {
        let unbounded = CGSize(
            width: CGFloat.greatestFiniteMagnitude,
            height: CGFloat.greatestFiniteMagnitude
        )
        var size = clamp(rect.height * heightFillRatio)
        var resolved = context.resolve(Text(string).font(.system(size: size)))
        var measured = resolved.measure(in: unbounded)
        var passes = 0
        while measured.width > rect.width, measured.width > 0,
              size > minFontSize, passes < 3 {
            // 0.98: bias UNDER the box so metric nonlinearity can't push the
            // corrected size back over the edge it was correcting for.
            size = clamp(size * (rect.width / measured.width) * 0.98)
            resolved = context.resolve(Text(string).font(.system(size: size)))
            measured = resolved.measure(in: unbounded)
            passes += 1
        }
        return resolved
    }

    private static func clamp(_ value: CGFloat) -> CGFloat {
        min(max(value, minFontSize), maxFontSize)
    }
}
