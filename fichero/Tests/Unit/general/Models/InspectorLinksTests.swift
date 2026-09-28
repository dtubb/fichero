@testable import Fichero
import FicheroAPIClient
import Testing

/// The Inspector's Links section (5.7, #5164). What breaks without these: a link shown by an id, a
/// Link menu that links a segment to itself or guesses which of three to join, or certainty lost.
struct InspectorLinksTests {
    private func segment(_ id: String, kind: String, text: String?) -> Segment {
        Segment(
            id: id, provisional: false, documentId: "p1", passId: "p", kind: kind, kindRaw: nil,
            provenanceKind: .externalImport,
            anchor: SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "p1")),
            baseline: nil, text: text, confidence: nil, sourceArtifactId: nil, boxIndex: nil, pageIndex: nil, metadata: nil
        )
    }

    @Test("each link reads as a sentence from this end, naming the other end from the page")
    func rowsReadFromThisEnd() {
        let long = String(repeating: "ܐ", count: 45)
        let rows = InspectorLinks.rows([
            .init(id: "k1", linkType: "continues", label: "Is continued by", otherKind: "segment", otherId: "l2",
                  inbound: true, certainty: 0.9, note: "the sentence runs on"),
            .init(id: "k2", linkType: "glosses", label: "Glosses", otherKind: "segment", otherId: "elsewhere",
                  inbound: false),
            .init(id: "k3", linkType: "names", label: "Names", otherKind: "canvas_item", otherId: "c1", inbound: false)
        ], segments: [segment("l2", kind: "line", text: long)])
        #expect(rows.map(\.sentence) == ["Is continued by", "Glosses", "Names"])
        #expect(rows[0].other == "Line · " + String(repeating: "ܐ", count: 40) + "…")
        #expect(rows[0].detail == "sure 90% · the sentence runs on")
        #expect(rows[1].other == "a segment on another page" && rows[1].detail.isEmpty)
        #expect(rows[2].other == "a canvas item")
    }

    @Test("the Link menu needs exactly two different segments, first to second")
    func pairIsExactlyTwo() {
        #expect(InspectorLinks.pair(["a", "b"])! == (from: "a", to: "b"))
        #expect(InspectorLinks.pair(["a"]) == nil)
        #expect(InspectorLinks.pair(["a", "a"]) == nil)
        #expect(InspectorLinks.pair(["a", "b", "c"]) == nil)
    }
}
