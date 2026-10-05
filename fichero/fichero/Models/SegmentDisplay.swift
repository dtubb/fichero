import Foundation
import OSLog

/// The ONE shared function mapping a document's segments to today's
/// `OCRGeometry` draw model (source-model App slice A stage 1, #4954:
/// `source.app.overlays-draw-from-the-seam`). Both drawing paths — the image
/// overlay's `OCRGeometryOverlay` and the PDF path's `PDFPageWithToolbar` —
/// take their geometry from this, once wired (stage 2); no drawing code
/// changes and no new overlay view.
enum SegmentDisplay {
    private static let log = Logger(subsystem: "app.fichero.fichero", category: "SegmentDisplay")

    /// The pass the Preview draws on a page, its boxes, and the artifact it came from: what the image
    /// overlay, the PDF page, a reveal, a selection and the edit verbs all read (#5467). The id is
    /// load-bearing: the curation verbs address the artifact whose boxes are on screen (2026-08-29),
    /// so a loader that took the geometry from one pass and the id from another would point them at
    /// the wrong rows. The inspector's focused artifact, when it is this page's, is handed to
    /// `drawingOrder` -- the one place it counts.
    @MainActor
    static func selected(
        for documentId: String, store: SegmentStore
    ) -> Selected? {
        let focus = FocusedArtifact.shared
        return drawn(
            passes: store.passes(documentId: documentId),
            segments: store.segments(documentId: documentId),
            focusedArtifactId: focus.documentId == documentId ? focus.id : nil
        )
    }

    /// What the canvas draws and what it came from: the boxes, the artifact of the drawn pass (nil
    /// for an imported pass), and the pass itself.
    struct Selected {
        let geometry: OCRGeometry
        let artifactId: String?
        let passId: String
    }

    /// What a selection of the shown boxes is scoped to (#5152): the artifact the pass came from, or
    /// -- for a pass with no artifact, which is every IMPORTED pass -- the pass itself. Selection needs
    /// a scope (box indices mean nothing across two geometries), and requiring an ARTIFACT for it left
    /// an imported page's boxes drawn and unclickable. Only a scope: the edit verbs still need a real
    /// artifact id and keep taking it from `ocrGeometryArtifactId`.
    nonisolated static func selectionScope(artifactId: String?, passId: String?) -> String? {
        artifactId ?? passId.map { "pass:\($0)" }
    }

    /// The pure half of `selected(for:store:)`: the first pass in `drawingOrder` whose segments map to
    /// boxes. A pass whose `boxIndex` values are not exactly `0..<count` is refused by
    /// `geometry(from:...)` and passed over, never guessed at.
    nonisolated static func drawn(
        passes: [SegmentPassValue], segments: [Segment], focusedArtifactId: String? = nil
    ) -> Selected? {
        let segmentsByPass = Dictionary(grouping: segments, by: \.passId)
        for pass in drawingOrder(passes, segments: segments, focusedArtifactId: focusedArtifactId) {
            guard let passSegments = segmentsByPass[pass.id], !passSegments.isEmpty,
                  let geometry = geometry(
                      from: passSegments,
                      // `pass.name` is the ARTIFACT TYPE (e.g. "transcription"), not a provider name,
                      // as the artifact path always read it.
                      provider: pass.name,
                      model: pass.model,
                      renditionId: passSegments.first?.anchor.renditionId
                  ) else { continue }
            return Selected(geometry: geometry, artifactId: pass.sourceArtifactId, passId: pass.id)
        }
        return nil
    }

    /// The ONE order the Preview tries a page's passes in (#5467). The app ranks nothing itself:
    ///
    /// 1. **the inspector's focused artifact**, when this page has a pass from it with a shape to draw
    ///    (ruled 2026-08-27: clicking a result in the Inspector shows its boxes). A REORDER, never a
    ///    filter: a focused pass with nothing usable falls through to the rest.
    /// 2. **the engine's drawn pass** (`PassRead.drawn`, `resolve_drawn_pass`): the working pass when it
    ///    has shapes, else the next pass in the engine's ranking that has them
    ///    (`ui.preview.draws-a-pass-with-shapes`, ruled 2026-10-04).
    /// 3. every other pass by the engine's `rank` (0 is the working pass), so a page with no shapes at
    ///    all still selects its working pass's lines. A pass the ranking does not hold comes last, in
    ///    the order served.
    ///
    /// A georeferencing pass holds control points, not the page's text (#5122): never drawn.
    nonisolated static func drawingOrder(
        _ passes: [SegmentPassValue], segments: [Segment], focusedArtifactId: String? = nil
    ) -> [SegmentPassValue] {
        let text = passes.filter { !$0.isGeoreferencing }
        let shapedPassIds = Set(segments.filter(hasShape).map(\.passId))
        let focused = focusedArtifactId.map { id in
            text.filter { $0.sourceArtifactId == id && shapedPassIds.contains($0.id) }
        } ?? []
        let rest = text.enumerated().sorted { lhs, rhs in
            if lhs.element.drawn != rhs.element.drawn { return lhs.element.drawn }
            switch (lhs.element.rank, rhs.element.rank) {
            case let (left?, right?) where left != right: return left < right
            case (.some, nil): return true
            case (nil, .some): return false
            default: return lhs.offset < rhs.offset
            }
        }.map(\.element)
        let focusedIds = Set(focused.map(\.id))
        return focused + rest.filter { !focusedIds.contains($0.id) }
    }

    /// Whether a segment has a place on the image to draw: not one whose file stated no place (the
    /// engine's `shape: unstated`, stored on a whole-page rect only because a segment must be
    /// somewhere), and not one with neither a box nor a drawn shape.
    nonisolated static func hasShape(_ segment: Segment) -> Bool {
        guard !segment.shapeIsUnstated else { return false }
        return segment.anchor.rect != nil || !SegmentShapes.drawn(for: segment).isEmpty
    }

    /// The pure mapping half, pulled out so a test can feed it a fixed
    /// segment list without picking a pass first.
    ///
    /// **Position in the returned `boxes` array IS the engine's index** —
    /// the same invariant every existing reader already relies on
    /// (`displayIndexedBoxes`, and a dozen call sites in
    /// `RegionInteractionLayer`/`ZoomableImagePreviewMac+Regions` that send
    /// an ARRAY OFFSET straight to `PUT …/regions`). This function does
    /// NOT introduce a second index space (an earlier draft of this stage
    /// gave `OCRGeometryBox` its own `engineIndex` field; a second review
    /// caught that every one of those dozen readers still uses the array
    /// offset, so a dropped box would desync exactly the readers this was
    /// meant to protect — reverted). Instead:
    ///
    /// * an undrawable segment (`anchor.rect` unset) STAYS in the list, at
    ///   its own `boxIndex` position, as a **zero-size placeholder box**
    ///   (`bbox: [0, 0, 0, 0]`) — exactly the shape today's artifact path
    ///   already produces for a genuine zero-width box, and already relies
    ///   on being harmless: `OCRGeometryOverlay`'s `Canvas` fills/strokes a
    ///   `Path(roundedRect:)` of zero area, which paints nothing visible
    ///   (`BoundingBoxGeometry.viewRect` does not special-case a zero
    ///   `bbox[2]`/`bbox[3]`, so this is the same code path a real
    ///   zero-width box already takes, not a new one). Hit-testing
    ///   (`RegionHitTesting.pick`, `OCRGeometryOverlay.hoveredBox`) insets
    ///   by 2pt, so a placeholder IS technically hoverable in a tiny 4×4pt
    ///   region at its `[0, 0]` origin and would win any tie (zero area is
    ///   always the smallest) — the same accepted quirk today's zero-width
    ///   boxes already have; not introduced here, not fixed here.
    ///   **Stage-2 follow-up** (named, not fixed, here): once this is
    ///   actually wired to an overlay, a shapeless segment's placeholder
    ///   sits at the page's top-left corner and is hoverable there. Stage 2
    ///   should make hit-testing skip zero-area boxes outright, or place
    ///   nothing hoverable for one.
    /// * a pass's `boxIndex` values must be exactly `0..<segments.count` —
    ///   no gap (a missing index silently shifts nothing, but IS evidence
    ///   the engine's answer for this pass is incomplete) and no repeat.
    ///   Anything else REFUSES the whole pass (returns `nil`, logs) rather
    ///   than guessing an order — the same "refuse, don't guess" rule as
    ///   the duplicate case it subsumes.
    nonisolated static func geometry(
        from segments: [Segment],
        provider: String,
        model: String?,
        renditionId: String?
    ) -> OCRGeometry? {
        guard Set(segments.compactMap(\.boxIndex)) == Set(0..<segments.count) else {
            log.error("""
                refusing pass \(segments.first?.passId ?? "?", privacy: .public): \
                \(segments.count, privacy: .public) segments' boxIndex values are not exactly 0..<count
                """)
            return nil
        }
        // ponytail: the pass's as-written order (`boxIndex`), not a named order the Segments pane may have
        // chosen -- `ReadingOrderStore` is per pane and the Preview holds none. Reading a chosen order here
        // needs the pane's order id beside the document; until then a reordered named order does not reshade.
        let tones = RegionColours.tones(of: segments)
        let boxes: [OCRGeometryBox] = segments
            .sorted { ($0.boxIndex ?? 0) < ($1.boxIndex ?? 0) }
            .map { segment in
                // `provider`/`source` here are not a raw pass-through — `Segment`
                // doesn't carry the box's original values (only the engine's
                // already-resolved `provenanceKind`). Setting `provider: "user"`
                // when `isHandCurated` is true is a HONEST re-derivation, not an
                // invention: it makes the mapped `OCRGeometryBox.isHandDrawn`
                // (`provider == "user" || source == "manual"`) evaluate to
                // exactly `segment.isHandCurated`, which is what every existing
                // reader of `.isHandDrawn` downstream (curation styling, the
                // ranking artifact path) already expects to keep working
                // unchanged. Never set when false — an un-curated box gets `nil`
                // for both, same as today. (Stage 2 follow-up per review: give
                // the draw model `isHandDrawn` as a stored boolean directly and
                // drop this two-string reconstruction.)
                OCRGeometryBox(
                    text: segment.text ?? "",
                    // An UNSTATED shape is the same zero-size placeholder as an unset rect: kept in
                    // its place so no later box shifts, never drawn as the page-sized rectangle the
                    // engine stores it on.
                    // A drawn polygon or baseline may state no rect: it is drawn and clicked by its
                    // shapes' bounds (`SegmentShapes.displayBox`), a flat baseline kept clickable.
                    bbox: segment.shapeIsUnstated
                        ? [0, 0, 0, 0] : (segment.anchor.rect ?? SegmentShapes.displayBox(for: segment) ?? [0, 0, 0, 0]),
                    level: segment.kind,
                    confidence: segment.confidence,
                    pageIndex: nil,
                    charStart: segment.anchor.charStart,
                    charEnd: segment.anchor.charEnd,
                    provider: segment.isHandCurated ? "user" : nil,
                    source: segment.isHandCurated ? "manual" : nil,
                    shapes: SegmentShapes.drawn(for: segment),
                    noReading: SegmentsPane.lacksReading(segment),
                    segmentId: segment.id,
                    tone: tones[segment.id]
                )
            }
        return OCRGeometry(
            text: boxes.map(\.text).joined(separator: " "),
            provider: provider,
            model: model,
            boxes: boxes,
            renditionId: renditionId
        )
    }
}
