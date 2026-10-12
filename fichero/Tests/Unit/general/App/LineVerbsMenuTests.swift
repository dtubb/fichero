import FicheroAPIClient
import Foundation
@testable import Fichero
import Testing

/// #5652 slice 4, group 3: Correct This Line…, Open (a segment that holds others) and Create Named Order are one item
/// each, which the Reader's line rows, the Order list and the Segments pictures render on their own row, and Page ›
/// Segments renders on the focused list's selection (`LineVerbsTarget`). What breaks without these: Page › Segments
/// offering to correct a region, an item on with nothing to act on (or off with no word), or a press that reaches
/// the wrong row.
@MainActor
@Suite("A line's and a segment's verbs, one component each (#5652 slice 4)")
struct LineVerbsMenuTests {
    private func segment(_ id: String, kind: String) -> Segment {
        let anchor = SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "p1"))
        return Segment(
            id: id, provisional: false, documentId: "p1", passId: "p", kind: kind, kindRaw: nil,
            parentSegmentId: nil, provenanceKind: .externalImport, anchor: anchor, baseline: nil,
            text: "enel tþo q́ el escriuio", confidence: nil, sourceArtifactId: nil, boxIndex: 0, pageIndex: nil,
            metadata: nil
        )
    }

    @Test("Correct This Line… acts on one selected line, and says why on anything else")
    func correctReasons() {
        #expect(LineVerbs.correctReason(nil) == "Select a line in the Reader or the Order list")
        let line = segment("l1", kind: "line")
        #expect(LineVerbs.correctReason(LineVerbsTarget(segment: line, correct: {})) == nil)
        #expect(LineVerbs.correctReason(LineVerbsTarget(segment: segment("r1", kind: "region"), correct: {}))
            == "Only a line can be corrected")
        #expect(LineVerbs.correctReason(LineVerbsTarget(segment: line)) == "Select the line in the Reader or the Order list")
    }

    @Test("Open acts on a segment that holds others; Create Named Order only while the page has none")
    func openAndCreateReasons() {
        #expect(LineVerbs.openReason(nil) == "Select a segment that holds others")
        let region = segment("r1", kind: "region")
        #expect(LineVerbs.openReason(LineVerbsTarget(segment: region, open: {})) == nil)
        #expect(LineVerbs.openReason(LineVerbsTarget(segment: region)) == "This segment holds nothing to open")
        #expect(LineVerbs.createNamedOrderReason(LineVerbsTarget(createNamedOrder: {})) == nil)
        #expect(LineVerbs.createNamedOrderReason(LineVerbsTarget())
            == "Show a page with no named order in the Order list")
    }

    @Test("the press reaches the row's own action")
    func pressReachesTheRow() {
        var calls: [String] = []
        let target = LineVerbsTarget(
            segment: segment("l1", kind: "line"), correct: { calls.append("correct") }, open: { calls.append("open") },
            createNamedOrder: { calls.append("order") }
        )
        target.correct?()
        target.open?()
        target.createNamedOrder?()
        #expect(calls == ["correct", "open", "order"])
    }

    @Test("the target compares by what the menu shows, so a re-render of the same selection does not republish")
    func equality() {
        let line = segment("l1", kind: "line")
        #expect(LineVerbsTarget(segment: line, correct: {}) == LineVerbsTarget(segment: line, correct: {}))
        #expect(LineVerbsTarget(segment: line, correct: {}) != LineVerbsTarget(segment: line))
        #expect(LineVerbsTarget(segment: line) != LineVerbsTarget(segment: segment("l2", kind: "line")))
    }

    @Test("titles keep their words; the one that asks for more has the ellipsis")
    func titles() {
        #expect(LineVerbs.correctTitle == "Correct This Line…")
        #expect(LineVerbs.createNamedOrderTitle == "Create Named Order")
    }
}
