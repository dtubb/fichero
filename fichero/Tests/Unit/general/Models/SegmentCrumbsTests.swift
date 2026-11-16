@testable import Fichero
import FicheroAPIClient
import Testing

/// The path's tail for a selection (Step 1.25). What breaks without these: a selected line the head does not name,
/// or a multi-selection that names one segment as if it were alone.
struct SegmentCrumbsTests {
    private func segment(_ id: String, kind: String, parent: String? = nil) -> Segment {
        Segment(
            id: id, provisional: false, documentId: "p1", passId: "p", kind: kind, kindRaw: nil,
            parentSegmentId: parent, provenanceKind: .externalImport,
            anchor: SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "p1")),
            baseline: nil, text: nil, confidence: nil, sourceArtifactId: nil, boxIndex: nil, pageIndex: nil, metadata: nil
        )
    }

    private var page: [Segment] {
        [segment("r1", kind: "region"), segment("r2", kind: "region"),
         segment("l1", kind: "line", parent: "r2"), segment("l2", kind: "line", parent: "r2"),
         segment("l3", kind: "line", parent: "r2")]
    }

    @Test("nothing selected, no tail; one segment names its path, numbered among its siblings")
    func single() {
        #expect(SegmentCrumbs.trail(selected: [], in: page).isEmpty)
        #expect(SegmentCrumbs.trail(selected: ["l2"], in: page).map(\.title) == ["Region 2", "Line 2"])
        #expect(SegmentCrumbs.trail(selected: ["r1"], in: page).map(\.title) == ["Region 1"])
    }

    @Test("several share their path and then say how many, by kind")
    func several() {
        #expect(SegmentCrumbs.trail(selected: ["l1", "l3"], in: page).map(\.title) == ["Region 2", "2 lines"])
        #expect(SegmentCrumbs.trail(selected: ["l1", "r1"], in: page).map(\.title).last == "1 region, 1 line"
            || SegmentCrumbs.trail(selected: ["l1", "r1"], in: page).map(\.title).last == "1 line, 1 region")
    }
}
