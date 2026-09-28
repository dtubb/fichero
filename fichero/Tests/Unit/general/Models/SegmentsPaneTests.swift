@testable import Fichero
import FicheroAPIClient
import Testing

/// The Segments pane (#4942). What breaks without these: a row offered to open with nothing inside,
/// a path that names ids instead of levels, or a row that reads as an id.
struct SegmentsPaneTests {
    private func segment(_ id: String, kind: String, parent: String? = nil, text: String? = nil) -> Segment {
        Segment(
            id: id, provisional: false, documentId: "p1", passId: "p", kind: kind, kindRaw: nil,
            parentSegmentId: parent, provenanceKind: .externalImport,
            anchor: SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "p1")),
            baseline: nil, text: text, confidence: nil, sourceArtifactId: nil, boxIndex: nil, pageIndex: nil, metadata: nil
        )
    }

    @Test("a row opens only when the segment holds others; the path names each level down to it")
    func openAndPath() {
        let segments = [
            segment("r1", kind: "region"),
            segment("l1", kind: "line", parent: "r1", text: "ܐܒܪܗܡ"),
            segment("w1", kind: "word", parent: "l1")
        ]
        #expect(SegmentsPane.hasChildren("r1", in: segments))
        #expect(SegmentsPane.hasChildren("l1", in: segments))
        #expect(!SegmentsPane.hasChildren("w1", in: segments))
        #expect(SegmentsPane.path(pageTitle: "fol. 1r", to: nil, in: segments).map(\.title) == ["fol. 1r"])
        let path = SegmentsPane.path(pageTitle: "fol. 1r", to: "l1", in: segments)
        #expect(path.map(\.title) == ["fol. 1r", "Region", "Line"])
        #expect(path.map(\.segmentId) == [nil, "r1", "l1"])
    }

    @Test("a row reads as its kind and its words, or its kind and place when it has none")
    func rowLabels() {
        #expect(SegmentsPane.rowLabel(segment("l1", kind: "line", text: " ܐܒ "), at: 0) == "Line · ܐܒ")
        #expect(SegmentsPane.rowLabel(segment("r1", kind: "region"), at: 2) == "Region 3")
        #expect(SegmentsPane.rowLabel(nil, at: 0) == "Segment 1")
    }
}
