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

    /// The `@MainActor` half: reads the store (which is main-actor-isolated
    /// — `SegmentStore` is `@Observable` on the main actor) and hands plain
    /// values to the `nonisolated` pure function below. Splitting it this
    /// way, rather than marking this whole thing `nonisolated`, is the fix
    /// for the stage-1 build failure: a `nonisolated` function cannot call
    /// `store.passes(documentId:)`/`store.segments(documentId:)` from a
    /// synchronous context — they are main-actor-isolated methods.
    @MainActor
    static func geometry(for documentId: String, store: SegmentStore) -> OCRGeometry? {
        geometry(passes: store.passes(documentId: documentId), segments: store.segments(documentId: documentId))
    }

    /// Picks the winning pass (via `OCRGeometrySelection.rankedPasses`,
    /// skipping any pass whose segments list is empty — the same "probe and
    /// stop at the first that carries boxes" rule `loadSelected` applies
    /// today, just over data already in hand: one engine call already
    /// returned everything, so no per-pass fetch is needed), then maps that
    /// pass's segments to `OCRGeometry`. A pass whose segments are refused
    /// by `geometry(from:...)` (its `boxIndex` values are not exactly
    /// `0..<count`) is skipped, same as an empty pass — never the crash,
    /// never a guess.
    ///
    /// Pure and `nonisolated`: takes plain values, no store, no actor — the
    /// half a test can call directly.
    ///
    /// Deliberately narrower than `OCRGeometrySelection.loadSelected` for
    /// stage 1: no per-window "inspector selection outranks the ladder"
    /// override (`FocusedArtifact`) yet — nothing calls this from a real
    /// overlay until stage 2, so adding that override now would be
    /// untestable and untested. It is the acknowledged gap when this
    /// function is actually wired in.
    nonisolated static func geometry(passes: [SegmentPassValue], segments: [Segment]) -> OCRGeometry? {
        let ranked = OCRGeometrySelection.rankedPasses(passes, segments: segments)
        let segmentsByPass = Dictionary(grouping: segments, by: \.passId)
        for pass in ranked {
            guard let passSegments = segmentsByPass[pass.id], !passSegments.isEmpty else { continue }
            guard let geometry = geometry(
                from: passSegments,
                // `pass.name` is the ARTIFACT TYPE (e.g. "transcription"),
                // not a provider name — same as today's artifact path
                // (`OCRGeometry.init(generated:)` reads the artifact's own
                // `provider`). `PassRead.provider` is landing from the
                // engine but is not yet populated end-to-end; team-lead:
                // hold this until the regenerated client carries live
                // values, then switch to `pass.provider`.
                provider: pass.name,
                model: pass.model,
                renditionId: passSegments.first?.anchor.renditionId
            ) else { continue }
            return geometry
        }
        return nil
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
            log.error("refusing pass \(segments.first?.passId ?? "?", privacy: .public): \(segments.count, privacy: .public) segments' boxIndex values are not exactly 0..<count")
            return nil
        }
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
                    bbox: segment.anchor.rect ?? [0, 0, 0, 0],
                    level: segment.kind,
                    confidence: segment.confidence,
                    pageIndex: nil,
                    charStart: segment.anchor.charStart,
                    charEnd: segment.anchor.charEnd,
                    provider: segment.isHandCurated ? "user" : nil,
                    source: segment.isHandCurated ? "manual" : nil
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
