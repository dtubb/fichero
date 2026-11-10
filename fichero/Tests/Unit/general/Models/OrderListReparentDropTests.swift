@testable import Fichero
import FicheroAPIClient
import Testing

/// Which drops the nested Order list offers (Step 1.25). What breaks without these: a region dropped into a line,
/// a line into itself, or a segment into what it holds -- a loop in the hierarchy the engine would have to refuse.
struct OrderListReparentDropTests {
    private func segment(_ id: String, kind: String, parent: String? = nil) -> Segment {
        Segment(
            id: id, provisional: false, documentId: "p1", passId: "p", kind: kind, kindRaw: nil,
            parentSegmentId: parent, provenanceKind: .externalImport,
            anchor: SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "p1")),
            baseline: nil, text: nil, confidence: nil, sourceArtifactId: nil, boxIndex: nil, pageIndex: nil, metadata: nil
        )
    }

    private var page: [Segment] {
        [segment("r1", kind: "region"), segment("region2", kind: "region"),
         segment("l1", kind: "line", parent: "r1"), segment("l2", kind: "line", parent: "r1"),
         segment("w1", kind: "word", parent: "l1")]
    }

    @Test("lines drop into a region in the order dragged; a line already in it may move to another")
    func linesIntoARegion() {
        let region2 = page[1]
        #expect(OrderDrop.accepted(["l2", "l1"], into: region2, in: page) == ["l2", "l1"])
    }

    @Test("only the level just below drops in: a region into a region or a line, a word into a region, is refused")
    func levels() {
        let region2 = page[1], line1 = page[2]
        #expect(OrderDrop.accepted(["r1"], into: region2, in: page).isEmpty)
        #expect(OrderDrop.accepted(["r1"], into: line1, in: page).isEmpty)
        #expect(OrderDrop.accepted(["w1"], into: region2, in: page).isEmpty)
        #expect(OrderDrop.accepted(["w1"], into: page[3], in: page) == ["w1"])
    }

    @Test("a segment never drops into itself, and an id off the page is dropped from the set")
    func itself() {
        #expect(OrderDrop.accepted(["r1"], into: page[0], in: page).isEmpty)
        #expect(OrderDrop.accepted(["l1", "ghost"], into: page[1], in: page) == ["l1"])
    }

    @Test("Move Into offers the level above: words go into lines, a glyph into a word, lines into regions; nothing mixed")
    func targetsByLevel() {
        let segments = page + [segment("g1", kind: "glyph", parent: "w1")]
        #expect(SegmentMover.targets(for: ["w1"], in: segments).map(\.id) == ["l1", "l2"])
        #expect(SegmentMover.targets(for: ["g1"], in: segments).map(\.id) == ["w1"])
        #expect(SegmentMover.targets(for: ["l1"], in: segments).map(\.id) == ["r1", "region2"])
        #expect(SegmentMover.targets(for: ["l1", "w1"], in: segments).isEmpty)
    }
}
