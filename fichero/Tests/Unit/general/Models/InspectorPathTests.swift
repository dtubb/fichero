@testable import Fichero
import FicheroAPIClient
import Testing

/// The Inspector's path head and what it inspects (ruled 2026-09-27, `build-notes-inspector.md`).
/// What breaks without these: a path that invents a parent it cannot open, a mixed selection shown
/// as one of its segments, or the Source view's box indices read against the wrong pass -- which
/// inspects a different segment than the one drawn selected.
struct InspectorPathTests {
    private func segment(
        _ id: String, kind: String, parent: String? = nil, passId: String = "p1", boxIndex: Int? = nil
    ) -> Segment {
        Segment(
            id: id, provisional: false, documentId: "page-1", passId: passId,
            kind: kind, kindRaw: nil, parentSegmentId: parent,
            provenanceKind: .workflow,
            anchor: SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "page-1")),
            baseline: nil, text: nil, confidence: nil, language: nil, script: nil, direction: nil,
            sourceArtifactId: nil, boxIndex: boxIndex, pageIndex: nil, metadata: nil
        )
    }

    private var page: [Segment] {
        [
            segment("b1", kind: "region"),
            segment("l1", kind: "line", parent: "b1"),
            segment("w1", kind: "word", parent: "l1"),
            segment("w2", kind: "word", parent: "l1"),
            segment("l2", kind: "line", parent: "b1"),
            segment("b2", kind: "region"),
            segment("l3", kind: "line", parent: "b2")
        ]
    }

    @Test("a word's path runs block, line, word, outermost first")
    func pathToAWord() {
        let path = InspectorPath.to("w2", in: page)
        #expect(path?.crumbs.map(\.segmentId) == ["b1", "l1", "w2"])
        #expect(path?.crumbs.map(\.label) == ["Region", "Line", "Word"])
    }

    @Test("a missing parent or a cycle ends the path; it never invents a crumb")
    func missingParentAndCycleEndTheWalk() {
        let orphan = [segment("w9", kind: "word", parent: "gone")]
        #expect(InspectorPath.to("w9", in: orphan)?.crumbs.map(\.segmentId) == ["w9"])
        let cycle = [segment("a", kind: "line", parent: "b"), segment("b", kind: "region", parent: "a")]
        #expect(InspectorPath.to("a", in: cycle)?.crumbs.map(\.segmentId) == ["b", "a"])
        #expect(InspectorPath.to("nowhere", in: page) == nil)
    }

    @Test("a mixed selection shows its nearest common parent, and counts by kind")
    func mixedSelection() {
        #expect(InspectorPath.common(["w1", "l2"], in: page)?.crumbs.map(\.segmentId) == ["b1"])
        #expect(InspectorPath.common(["w1", "w2"], in: page)?.crumbs.map(\.segmentId) == ["b1", "l1"])
        // Two blocks share no parent segment: the path is the page itself.
        #expect(InspectorPath.common(["l1", "l3"], in: page)?.crumbs.isEmpty == true)
        #expect(InspectorPath.common(["l1", "nowhere"], in: page) == nil)
        let counts = InspectorPath.kindCounts(["l1", "l3", "w1"], in: page)
        #expect(counts.map(\.kind) == ["line", "word"])
        #expect(counts.map(\.count) == [2, 1])
    }

    @Test("the Source view's box indices name segments of the pass THEIR artifact made, in the order picked")
    func selectionIndicesResolveInTheirOwnPass() {
        let passes = [
            SegmentPassValue(
                id: "p1", provisional: false, documentId: "page-1", name: "import", provenanceKind: .workflow,
                sourceArtifactId: "art-1"
            ),
            SegmentPassValue(
                id: "p2", provisional: false, documentId: "page-1", name: "rerun", provenanceKind: .workflow,
                sourceArtifactId: "art-2"
            )
        ]
        let segments = [
            segment("x0", kind: "line", passId: "p1", boxIndex: 0),
            segment("x1", kind: "line", passId: "p1", boxIndex: 1),
            segment("y0", kind: "line", passId: "p2", boxIndex: 0),
            segment("y1", kind: "line", passId: "p2", boxIndex: 1)
        ]
        let fromArt2 = InspectorPath.segmentIds(
            selectedIndices: [1, 0], artifactId: "art-2", passes: passes, segments: segments
        )
        #expect(fromArt2 == ["y1", "y0"])
        let unknown = InspectorPath.segmentIds(
            selectedIndices: [0], artifactId: "art-9", passes: passes, segments: segments
        )
        #expect(unknown.isEmpty)
    }
}
