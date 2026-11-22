@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.convert-level`. Convert to Line and
/// Convert to Region send the selected segments of the other level as one `segment.convert_level` with the versions read,
/// so many are one undo. What breaks without these: a call per segment, a segment already at the level sent for nothing,
/// or a segment with no saved version sent anyway.
@MainActor
@Suite(.tags(.paleography))
struct SegmentConvertLevelTests {
    private func segment(_ id: String, kind: String, version: Int?) -> Segment {
        let anchor = SourceAnchorValue(
            generated: Components.Schemas.SourceAnchorOutput(documentId: "page-1", rect: [0.1, 0.1, 0.4, 0.1])
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

    @Test("three regions are one segment.convert_level to line, with their versions")
    func regionsToLines() throws {
        let three = [segment("a", kind: "region", version: 2), segment("b", kind: "region", version: 5),
                     segment("c", kind: "region", version: 1)]
        let call = try SegmentEdit.convertLevel(three, to: "line").get()
        let params = try body(call)
        #expect(call.action == "segment.convert_level")
        #expect(params["to_kind"] as? String == "line")
        #expect(params["to"] == nil)
        #expect(params["segment_ids"] as? [String] == ["a", "b", "c"])
        #expect(params["expected_versions"] as? [String: Int] == ["a": 2, "b": 5, "c": 1])
    }

    @Test("a segment already at the level is left out; only those sends nothing")
    func alreadyThere() throws {
        let mixed = [segment("a", kind: "line", version: 2), segment("b", kind: "region", version: 3)]
        let params = try body(SegmentEdit.convertLevel(mixed, to: "region").get())
        #expect(params["segment_ids"] as? [String] == ["a"])
        #expect(SegmentEdit.convertLevel([segment("b", kind: "region", version: 3)], to: "region") == .failure(.tooFew))
        #expect(SegmentEdit.convertLevel([], to: "line") == .failure(.tooFew))
    }

    @Test("a segment with no saved version is not sent")
    func unsaved() {
        #expect(SegmentEdit.convertLevel([segment("a", kind: "region", version: nil)], to: "line") == .failure(.versionUnknown))
    }
}
