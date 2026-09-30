@testable import Fichero
import FicheroAPIClient
import Testing

/// Gathered sets in the Segments pane (#4942). What breaks without these: a row that cannot open its
/// page, a judgement shown without who made it or how sure, or segments the reader may not see left
/// out without a word (#5180).
struct SegmentsGatherTests {
    private func segment(_ id: String, document: String, text: String?) -> Segment {
        Segment(
            id: id, provisional: false, documentId: document, passId: "p", kind: "line", kindRaw: nil,
            provenanceKind: .externalImport,
            anchor: SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: document)),
            baseline: nil, text: text, confidence: nil, sourceArtifactId: nil, boxIndex: nil, pageIndex: nil, metadata: nil
        )
    }

    @Test("a hand's rows are its segments' words, who judged and how sure; each opens its own page")
    func handRows() {
        let rows = SegmentsGathered.handRows([
            .init(id: "a1", handId: "h1", certainty: 0.8, judgedBy: "owner", fromFile: nil, segmentId: "l1"),
            .init(id: "a2", handId: "h1", certainty: nil, judgedBy: nil, fromFile: "file: 0065.xml", segmentId: "l9"),
            .init(id: "a3", handId: "h1", certainty: nil, judgedBy: "owner", fromFile: nil, segmentId: "gone")
        ], segments: ["l1": segment("l1", document: "p1", text: "ܐܒܪܗܡ"), "l9": segment("l9", document: "p2", text: "ܝܥܩܘܒ")])
        // A segment's words are always bidi-isolated in its label (#5199), so a right-to-left word
        // cannot reorder the "Line ·" around it.
        #expect(rows.map(\.title) == ["Line · \u{2068}ܐܒܪܗܡ\u{2069}", "Line · \u{2068}ܝܥܩܘܒ\u{2069}", "Segment 3"])
        #expect(rows.map(\.documentId) == ["p1", "p2", nil])
        #expect(rows.map(\.detail) == ["judged by owner · sure 80%", "from the file 0065.xml",
                                       "judged by owner · its segment could not be read"])
    }

    @Test("a sign's rows say how often it occurs in each segment")
    func signRows() {
        let rows = SegmentsGathered.signRows([
            .init(representationId: "r1", segmentId: "l1", documentId: "p1", count: 1),
            .init(representationId: "r2", segmentId: "l2", documentId: "p1", count: 3)
        ], segments: ["l1": segment("l1", document: "p1", text: "a \u{F1AC}")])
        #expect(rows.map(\.detail) == ["once", "3 times"])
        #expect(rows.map(\.documentId) == ["p1", "p1"])
    }

    @Test("what the reader may not see is counted and said, never silently missing")
    func withheldIsSaid() {
        #expect(SegmentsGathered.withheldNote(0) == nil)
        #expect(SegmentsGathered.withheldNote(1) == "1 more on a page you may not read")
        #expect(SegmentsGathered.withheldNote(4) == "4 more on pages you may not read")
        #expect(SegmentsGather.hand(id: "h", label: "hand B").title == "Everything in hand B")
        #expect(SegmentsGather.sign(id: "s", name: "MUFI abbreviation sign").title == "Every instance of MUFI abbreviation sign")
    }
}
