@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// source-model App slice A stage 1 (#4954): `SegmentDisplay.geometry(from:...)`
/// is the ONE shared function mapping a chosen pass's segments to today's
/// `OCRGeometry` draw model — `source.app.overlays-draw-from-the-seam`.
/// `geometry(for:store:)` (the `@MainActor` store-reading wrapper) is not
/// tested here — it needs a `SegmentStore`, and this slice never mounts a
/// view or wires a store to a real overlay; the `nonisolated`, pure halves
/// (`geometry(passes:segments:)` and `geometry(from:...)`) are what stage 1
/// can prove, and are exactly what stage 2 will call once wired.
struct SegmentDisplayTests {

    private func segment(
        id: String,
        passId: String = "legacy:a1",
        boxIndex: Int?,
        rect: [Double]?,
        text: String? = nil,
        humanCurated: Bool = false
    ) -> Segment {
        Segment(
            id: id, provisional: true, documentId: "doc-1", passId: passId,
            kind: "word", kindRaw: nil,
            provenanceKind: humanCurated ? .human : .workflow,
            anchor: SourceAnchorValue(
                generated: Components.Schemas.SourceAnchorOutput(documentId: "doc-1", rect: rect)
            ),
            baseline: nil, text: text, confidence: nil,
            sourceArtifactId: "a1", boxIndex: boxIndex, pageIndex: nil, metadata: nil
        )
    }

    @Test("segments map to boxes ordered by boxIndex, so index-based selection keeps meaning the same box")
    func orderedByBoxIndex() {
        let segments = [
            segment(id: "s2", boxIndex: 2, rect: [0, 0, 1, 1], text: "third"),
            segment(id: "s0", boxIndex: 0, rect: [0, 0, 1, 1], text: "first"),
            segment(id: "s1", boxIndex: 1, rect: [0, 0, 1, 1], text: "second")
        ]
        let geometry = SegmentDisplay.geometry(from: segments, provider: "transcription", model: nil, renditionId: nil)
        #expect(geometry?.boxes.map(\.text) == ["first", "second", "third"])
    }

    /// Review fix #1, second design: an unset rect is never dropped and
    /// never invented — it becomes the same zero-size shape today's
    /// artifact path already produces for a real zero-width box, so this
    /// segment's position in `boxes` (and every later segment's) is
    /// undisturbed.
    @Test("a segment with an unset rect maps to a zero-size box, not a dropped one and not an invented rect")
    func unsetRectBecomesZeroSizeBox() throws {
        let segments = [
            segment(id: "good", boxIndex: 0, rect: [0.1, 0.1, 0.2, 0.2], text: "kept"),
            segment(id: "degenerate", boxIndex: 1, rect: nil, text: "still here")
        ]
        // F18 (test audit): a plain #expect(count == n) followed by a
        // subscript traps the whole test process, not just this test, if the
        // count regresses. `try #require` fails THIS test instead.
        let geometry = try #require(
            SegmentDisplay.geometry(from: segments, provider: "transcription", model: nil, renditionId: nil)
        )
        try #require(geometry.boxes.count == 2)
        #expect(geometry.boxes[1].bbox == [0, 0, 0, 0])
        #expect(geometry.boxes[1].text == "still here")
    }

    /// Review fix #1, second design: position in `boxes` IS the engine's
    /// index — the invariant `displayIndexedBoxes` and every curation
    /// call site already rely on. An undrawable middle segment STAYS in
    /// the list, at ITS OWN `boxIndex` position, as a zero-size
    /// placeholder box — never dropped, so the box after it keeps its
    /// place (2) and its own array offset, both at once.
    @Test("an undrawable segment stays in the list as a zero-size placeholder at its own boxIndex, so no later box shifts")
    func undrawableSegmentStaysAsZeroSizePlaceholder() throws {
        let segments = [
            segment(id: "s0", boxIndex: 0, rect: [0, 0, 1, 1], text: "first"),
            segment(id: "s1", boxIndex: 1, rect: nil, text: "dropped"),
            segment(id: "s2", boxIndex: 2, rect: [0, 0, 1, 1], text: "third")
        ]
        // F18: require the count before subscripting — see unsetRectBecomesZeroSizeBox.
        let geometry = try #require(
            SegmentDisplay.geometry(from: segments, provider: "transcription", model: nil, renditionId: nil)
        )
        try #require(geometry.boxes.count == 3)
        #expect(geometry.boxes[1].bbox == [0, 0, 0, 0])
        #expect(geometry.boxes[2].text == "third")
        // Position IS the index: the third segment sits at array offset 2,
        // matching its own boxIndex, exactly as displayIndexedBoxes expects.
        try #require(geometry.displayIndexedBoxes.count == 3)
        #expect(geometry.displayIndexedBoxes[2].index == 2)
        #expect(geometry.displayIndexedBoxes[2].box.text == "third")
    }

    /// Review fix #1: two segments of one pass sharing a `boxIndex` is
    /// refused outright, never silently resolved by picking one — the
    /// index would then address the wrong box for one of them.
    @Test("two segments of one pass sharing a boxIndex refuses the whole pass, rather than guessing")
    func duplicateBoxIndexRefusesThePass() {
        let segments = [
            segment(id: "s0", boxIndex: 0, rect: [0, 0, 1, 1], text: "a"),
            segment(id: "s0-dup", boxIndex: 0, rect: [0, 0, 1, 1], text: "b")
        ]
        let geometry = SegmentDisplay.geometry(from: segments, provider: "transcription", model: nil, renditionId: nil)
        #expect(geometry == nil)
    }

    /// The other half of "exactly 0..<count": a gap (0, 2 for two segments,
    /// skipping 1) refuses just as a repeat does — a missing index is
    /// evidence the engine's answer for this pass is incomplete, not
    /// something to silently renumber around.
    @Test("a gap in a pass's boxIndex values refuses the whole pass, rather than renumbering")
    func gapInBoxIndexRefusesThePass() {
        let segments = [
            segment(id: "s0", boxIndex: 0, rect: [0, 0, 1, 1], text: "a"),
            segment(id: "s2", boxIndex: 2, rect: [0, 0, 1, 1], text: "b")
        ]
        let geometry = SegmentDisplay.geometry(from: segments, provider: "transcription", model: nil, renditionId: nil)
        #expect(geometry == nil)
    }

    /// A pass refused for a bad `boxIndex` set is skipped, exactly like an
    /// empty pass — `geometry(passes:segments:)` falls through to the next
    /// candidate rather than returning nil outright when a better pass
    /// exists.
    @Test("geometry(passes:segments:) skips a pass refused for duplicate boxIndex and falls through to the next")
    func passSelectionSkipsARefusedPass() {
        let passes = [
            SegmentPassValue(
                id: "bad", provisional: true, documentId: "doc-1", name: "regions",
                provenanceKind: .workflow, provider: nil, model: nil, runId: nil,
                createdAt: Date(timeIntervalSince1970: 100), text: nil,
                sourceArtifactId: "bad", artifactType: "regions"
            ),
            SegmentPassValue(
                id: "good", provisional: true, documentId: "doc-1", name: "transcription",
                provenanceKind: .workflow, provider: nil, model: nil, runId: nil,
                createdAt: Date(timeIntervalSince1970: 0), text: nil,
                sourceArtifactId: "good", artifactType: "transcription"
            )
        ]
        let segments = [
            segment(id: "bad-0", passId: "bad", boxIndex: 0, rect: [0, 0, 1, 1], text: "dup-a"),
            segment(id: "bad-1", passId: "bad", boxIndex: 0, rect: [0, 0, 1, 1], text: "dup-b"),
            segment(id: "good-0", passId: "good", boxIndex: 0, rect: [0, 0, 1, 1], text: "fine")
        ]
        let geometry = SegmentDisplay.geometry(passes: passes, segments: segments)
        #expect(geometry?.boxes.map(\.text) == ["fine"])
    }

    @Test("a hand-curated segment maps to a box whose isHandDrawn is true, preserving today's curation styling")
    func handCuratedSegmentMapsToHandDrawnBox() {
        let segments = [segment(id: "s0", boxIndex: 0, rect: [0, 0, 1, 1], humanCurated: true)]
        let geometry = SegmentDisplay.geometry(from: segments, provider: "regions", model: nil, renditionId: nil)
        #expect(geometry?.boxes.first?.isHandDrawn == true)
    }

    @Test("a machine segment maps to a box whose isHandDrawn is false")
    func machineSegmentMapsToNotHandDrawnBox() {
        let segments = [segment(id: "s0", boxIndex: 0, rect: [0, 0, 1, 1], humanCurated: false)]
        let geometry = SegmentDisplay.geometry(from: segments, provider: "transcription", model: nil, renditionId: nil)
        #expect(geometry?.boxes.first?.isHandDrawn == false)
    }

    @Test("renditionId and provider/model survive onto the mapped OCRGeometry, unchanged")
    func passMetadataSurvives() {
        let segments = [segment(id: "s0", boxIndex: 0, rect: [0, 0, 1, 1])]
        let geometry = SegmentDisplay.geometry(from: segments, provider: "transcription", model: "sonnet-5.1", renditionId: "r7")
        #expect(geometry?.provider == "transcription")
        #expect(geometry?.model == "sonnet-5.1")
        #expect(geometry?.renditionId == "r7")
    }

    // MARK: - Before/after equivalence (source.app.overlays-draw-from-the-seam)
    //
    // The behaviour's acceptance is "the same drawing code as today and no new
    // overlay; a page looks the same before and after the switch". The screen half
    // is a click-around leg no unit test can make. The half a unit test CAN make is
    // the one that would break it: for the same page, the boxes the artifact path
    // yields today and the boxes the seam yields must be the same set, field by
    // field — because both are handed to the same `Canvas` draw closure.
    //
    // Built by taking one page's boxes as today's path yields them, turning the same
    // boxes into segments, and mapping those through `SegmentDisplay`. If they
    // diverge, the seam is the specified one and the views are what move — but nobody
    // should discover that on a screen.

    /// One box as TODAY's path yields it. `OCRGeometry(generated:)` passes the
    /// artifact's own `provider`/`source` straight through, so building the app model
    /// directly is the same value by a shorter route — and avoids asserting against a
    /// generated initialiser this test would otherwise have to guess at.
    private func todaysBox(
        text: String, bbox: [Double], level: String = "word",
        confidence: Double? = nil, provider: String? = nil, source: String? = nil
    ) -> OCRGeometryBox {
        OCRGeometryBox(
            text: text, bbox: bbox, level: level, confidence: confidence,
            pageIndex: nil, charStart: nil, charEnd: nil,
            provider: provider, source: source
        )
    }

    @Test("the seam yields the same boxes as today's artifact path, field for field")
    func seamMatchesTheArtifactPathForTheSamePage() throws {
        let today = [
            todaysBox(text: "hola", bbox: [0.1, 0.1, 0.2, 0.05], confidence: 0.9),
            todaysBox(text: "mundo", bbox: [0.4, 0.1, 0.25, 0.05], confidence: 0.8),
            // A hand-corrected box: today's path carries provider/source through and
            // the seam RE-DERIVES them from provenanceKind. `isHandDrawn` must agree
            // either way, or curation styling changes the day the seam is wired.
            todaysBox(text: "tercero", bbox: [0.1, 0.3, 0.3, 0.05],
                      provider: "user", source: "manual"),
        ]

        let asSegments = today.enumerated().map { index, box in
            segment(
                id: "seg-\(index)", boxIndex: index, rect: box.bbox, text: box.text,
                humanCurated: box.isHandDrawn
            )
        }
        let throughTheSeam = try #require(
            SegmentDisplay.geometry(
                from: asSegments, provider: "kraken", model: "mccatmus", renditionId: nil
            )
        )

        #expect(throughTheSeam.boxes.count == today.count)
        for (seam, artifact) in zip(throughTheSeam.boxes, today) {
            #expect(seam.text == artifact.text)
            #expect(seam.bbox == artifact.bbox)
            #expect(seam.level == artifact.level)
            // The one that matters for appearance: the same boxes are styled as
            // hand-drawn on both paths.
            #expect(seam.isHandDrawn == artifact.isHandDrawn)
        }
        #expect(throughTheSeam.provider == "kraken")
        #expect(throughTheSeam.model == "mccatmus")
    }

    @Test("an undrawable segment adds a box today's path would not have, and it draws nothing")
    func theOneDifferenceIsThePlaceholderAndItIsInvisible() throws {
        // The known, intended divergence, stated rather than discovered: a segment
        // with no rect has no counterpart in an artifact's boxes, and the seam keeps
        // it as a zero-size placeholder so no later box's INDEX shifts
        // (`source.app.index-is-the-engines`). A zero-area box paints nothing —
        // `OCRGeometryOverlay` fills a `Path(roundedRect:)` of zero area — so the
        // page still looks the same, which is what the behaviour asks.
        let geometry = try #require(
            SegmentDisplay.geometry(
                from: [
                    segment(id: "seg-0", boxIndex: 0, rect: [0.1, 0.1, 0.2, 0.05], text: "hola"),
                    segment(id: "seg-1", boxIndex: 1, rect: nil, text: "shapeless"),
                    segment(id: "seg-2", boxIndex: 2, rect: [0.4, 0.1, 0.2, 0.05], text: "mundo"),
                ],
                provider: "kraken", model: nil, renditionId: nil
            )
        )

        #expect(geometry.boxes.count == 3, "the placeholder stays, or seg-2 moves to index 1")
        #expect(geometry.boxes[1].bbox == [0, 0, 0, 0])
        #expect(geometry.boxes[2].text == "mundo", "the box AFTER the placeholder keeps its index")
    }
}
