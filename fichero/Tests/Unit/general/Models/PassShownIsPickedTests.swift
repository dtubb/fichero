@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// The page shows the pass a person picks (#6670, `source.editor.pass-shown-is-picked`). The owner's page: a pass a
/// person had edited is the working pass, and a newer Kraken run's pass, ranked below it, was listed in the Inspector
/// and never drawn. Picking the Kraken pass in the Pass menu draws and lists it at once, without promoting it.
struct PassShownIsPickedTests {
    private let format = Date.FormatStyle(date: .abbreviated, time: .omitted, locale: Locale(identifier: "en_US"),
                                          timeZone: TimeZone(identifier: "UTC") ?? .current)

    private func pass(
        _ id: String, model: String, rank: Int?, drawn: Bool = false, basis: String? = nil
    ) -> SegmentPassValue {
        var made = SegmentPassValue(
            id: id, provisional: false, documentId: "p1", name: "text_geometry", provenanceKind: .workflow,
            provider: nil, model: model, runId: nil, createdAt: Date(timeIntervalSince1970: 1_762_560_000), text: nil,
            sourceArtifactId: "artifact-\(id)", artifactType: nil
        )
        made.rank = rank
        made.drawn = drawn
        made.working = rank == 0
        made.workingBasis = rank == 0 ? (basis ?? "human-touched") : nil
        return made
    }

    private func line(_ id: String, pass passId: String, index: Int) -> Segment {
        var anchor = SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "p1"))
        anchor.rect = [0.1, 0.1 + Double(index) * 0.05, 0.6, 0.04]
        return Segment(
            id: id, provisional: false, documentId: "p1", passId: passId,
            kind: "line", kindRaw: nil, provenanceKind: .workflow,
            anchor: anchor, baseline: nil, text: "line \(index)", confidence: nil, sourceArtifactId: nil,
            boxIndex: index, pageIndex: nil, metadata: nil
        )
    }

    private var passes: [SegmentPassValue] {
        [pass("edited", model: "apple-vision", rank: 0, drawn: true), pass("kraken", model: "kraken", rank: 1)]
    }

    private var segments: [Segment] {
        [
            line("e0", pass: "edited", index: 0),
            line("k0", pass: "kraken", index: 0),
            line("k1", pass: "kraken", index: 1)
        ]
    }

    @Test("source.editor.pass-shown-is-picked: nothing picked, the working pass is shown and drawn")
    func nothingPickedShowsTheWorkingPass() {
        #expect(PassChoice.shown(passes: passes, pickedId: nil)?.id == "edited")
        #expect(SegmentDisplay.drawn(passes: passes, segments: segments)?.passId == "edited")
    }

    @Test("source.editor.pass-shown-is-picked: the Kraken pass picked is shown and drawn, ahead of the working pass")
    func aPickedPassIsDrawn() throws {
        #expect(PassChoice.shown(passes: passes, pickedId: "kraken")?.id == "kraken")
        let drawn = try #require(SegmentDisplay.drawn(passes: passes, segments: segments, pickedPassId: "kraken"))
        #expect(drawn.passId == "kraken")
        #expect(drawn.geometry.boxes.count == 2)
    }

    @Test("source.editor.pass-shown-is-picked: a picked pass the page no longer has falls back to the working pass")
    func aGonePickFallsBack() {
        #expect(PassChoice.shown(passes: passes, pickedId: "deleted")?.id == "edited")
        #expect(SegmentDisplay.drawn(passes: passes, segments: segments, pickedPassId: "deleted")?.passId == "edited")
    }

    @Test("source.editor.pass-shown-is-picked: the working pass first, promoted or default; the shown one ticked")
    func theMenu() {
        let items = PassChoice.items(passes: passes.reversed(), pickedId: "kraken", format: format)
        #expect(items.map(\.title) == ["apple-vision, Nov 8, 2025 · default", "kraken, Nov 8, 2025"])
        #expect(items.map(\.isShown) == [false, true])
        let promoted = [
            pass("edited", model: "apple-vision", rank: 0, basis: "chosen"), pass("kraken", model: "kraken", rank: 1)
        ]
        #expect(PassChoice.items(passes: promoted, pickedId: nil, format: format).first?.title
            == "apple-vision, Nov 8, 2025 · promoted")
    }

    /// #6422: the order a list shows reshades and renumbers the Preview's lines; with none, the as-written order.
    @Test("source.editor.colour.reading-order-gradient: the order shown reshades and renumbers the drawn lines")
    func theOrderShownReshades() throws {
        let written = try #require(SegmentDisplay.drawn(passes: passes, segments: segments, pickedPassId: "kraken"))
        #expect(written.geometry.boxes.map(\.orderNumber) == [1, 2])
        let reordered = try #require(SegmentDisplay.drawn(
            passes: passes, segments: segments, pickedPassId: "kraken", readingOrder: ["k1", "k0"]
        ))
        #expect(reordered.geometry.boxes.map(\.orderNumber) == [2, 1])
        let strengths = { (geometry: OCRGeometry) in geometry.boxes.compactMap { $0.tone?.strength } }
        #expect(strengths(reordered.geometry) == strengths(written.geometry).reversed())
    }

    @Test("source.editor.pass-shown-is-picked: one pass, no menu")
    func onePassNoChoice() {
        #expect(PassChoice.offersChoice(passes))
        #expect(!PassChoice.offersChoice(Array(passes.prefix(1))))
    }
}
