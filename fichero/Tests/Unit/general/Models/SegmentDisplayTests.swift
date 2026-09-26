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
}
