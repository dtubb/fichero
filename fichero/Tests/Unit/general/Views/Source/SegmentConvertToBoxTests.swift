@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.convert-to-box`. Convert to Box sends the
/// selected polygons as one `segment.convert_to_box` with the versions read, so many boxes are one undo. What breaks
/// without these: a call per segment, a box segment sent for nothing, or a segment with no saved version sent anyway.
@MainActor
@Suite(.tags(.paleography))
struct SegmentConvertToBoxTests {
    private func segment(_ id: String, version: Int?, polygon: [[Double]]?) -> Segment {
        var anchor = SourceAnchorValue(
            generated: Components.Schemas.SourceAnchorOutput(documentId: "page-1", rect: [0.1, 0.1, 0.4, 0.5])
        )
        anchor.polygon = polygon
        return Segment(
            id: id, provisional: false, documentId: "page-1", passId: "imported",
            kind: "region", kindRaw: nil, version: version, provenanceKind: .externalImport, anchor: anchor,
            baseline: nil, text: nil, confidence: nil, language: nil, script: nil, direction: nil,
            sourceArtifactId: nil, boxIndex: 0, pageIndex: nil, metadata: nil
        )
    }

    private let triangle: [[Double]] = [[0.1, 0.1], [0.5, 0.2], [0.2, 0.6]]

    @Test("three selected polygons are one segment.convert_to_box with their versions")
    func oneCall() throws {
        let three = [segment("a", version: 2, polygon: triangle), segment("b", version: 5, polygon: triangle),
                     segment("c", version: 1, polygon: triangle)]
        let call = try SegmentEdit.convertToBox(three).get()
        let data = try JSONEncoder().encode(call.params)
        let params = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(call.action == "segment.convert_to_box")
        #expect(params["segment_ids"] as? [String] == ["a", "b", "c"])
        #expect(params["expected_versions"] as? [String: Int] == ["a": 2, "b": 5, "c": 1])
    }

    @Test("a segment that is already a box is left out; only boxes selected sends nothing")
    func boxesAreLeftOut() throws {
        let mixed = [segment("a", version: 2, polygon: triangle), segment("b", version: 3, polygon: nil)]
        let call = try SegmentEdit.convertToBox(mixed).get()
        let params = try #require(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(call.params)) as? [String: Any]
        )
        #expect(params["segment_ids"] as? [String] == ["a"])
        #expect(SegmentEdit.convertToBox([segment("b", version: 3, polygon: nil)]) == .failure(.tooFew))
        #expect(SegmentEdit.convertToBox([]) == .failure(.tooFew))
    }

    @Test("a polygon with no saved version is not sent")
    func unsaved() {
        #expect(SegmentEdit.convertToBox([segment("a", version: nil, polygon: triangle)]) == .failure(.versionUnknown))
    }
}
