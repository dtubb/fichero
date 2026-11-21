@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.make-region-from-lines`. Make Region from
/// Lines sends the selected lines as one `segment.group_lines` and Ungroup Region one `segment.ungroup_region`, each with
/// the versions read, so each is one undo. What breaks without these: a region made from one line, a call per line, or a
/// region ungrouped with a version nobody read.
@MainActor
@Suite(.tags(.paleography))
struct SegmentGroupLinesTests {
    private func segment(_ id: String, kind: String = "line", version: Int? = 1) -> Segment {
        let anchor = SourceAnchorValue(
            generated: Components.Schemas.SourceAnchorOutput(documentId: "page-1", rect: [0.1, 0.2, 0.5, 0.04])
        )
        return Segment(
            id: id, provisional: false, documentId: "page-1", passId: "imported",
            kind: kind, kindRaw: nil, version: version, provenanceKind: .externalImport, anchor: anchor,
            baseline: nil, text: nil, confidence: nil, language: nil, script: nil, direction: nil,
            sourceArtifactId: nil, boxIndex: 0, pageIndex: nil, metadata: nil
        )
    }

    private func body(_ call: SegmentEdit.Call) throws -> [String: Any] {
        try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(call.params)) as? [String: Any])
    }

    @Test("three selected lines are one segment.group_lines with their versions")
    func group() throws {
        let call = try SegmentEdit.groupLines([segment("a", version: 2), segment("b", version: 5), segment("c", version: 1)]).get()
        let params = try body(call)
        #expect(call.action == "segment.group_lines")
        #expect(params["segment_ids"] as? [String] == ["a", "b", "c"])
        #expect(params["expected_versions"] as? [String: Int] == ["a": 2, "b": 5, "c": 1])
    }

    @Test("one line, or a line with no saved version, makes no region")
    func groupRefusals() {
        #expect(SegmentEdit.groupLines([segment("a")]) == .failure(.tooFew))
        #expect(SegmentEdit.groupLines([segment("a"), segment("b", version: nil)]) == .failure(.versionUnknown))
    }

    @Test("a selected region is one segment.ungroup_region with its version; a line or no version is refused")
    func ungroup() throws {
        let call = try SegmentEdit.ungroupRegion(segment("r", kind: "region", version: 4)).get()
        let params = try body(call)
        #expect(call.action == "segment.ungroup_region")
        #expect(params["region_id"] as? String == "r")
        #expect(params["expected_version"] as? Int == 4)
        #expect(SegmentEdit.ungroupRegion(segment("l")) == .failure(.tooFew))
        #expect(SegmentEdit.ungroupRegion(segment("r", kind: "region", version: nil)) == .failure(.versionUnknown))
    }
}
