@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.group-drag`. Dragging one of several
/// selected segments moves all of them by the same offset, as ONE `segment.translate` with each segment's version, so
/// one ⌘Z puts the group back and the engine moves outlines and baselines with their boxes. What breaks without these:
/// a move per segment (an undo per segment), or a baseline left behind its line.
@MainActor
@Suite(.tags(.paleography))
struct GroupMoveAndNudgeTests {
    private func line(_ id: String, version: Int?) -> Segment {
        Segment(
            id: id, provisional: false, documentId: "page-1", passId: "imported",
            kind: "line", kindRaw: nil, version: version, provenanceKind: .externalImport,
            anchor: SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "page-1", rect: [0.1, 0.2, 0.5, 0.05])),
            baseline: [[0.1, 0.24], [0.6, 0.24]], text: nil, confidence: nil, language: nil, script: nil, direction: nil,
            sourceArtifactId: nil, boxIndex: 0, pageIndex: nil, metadata: nil
        )
    }

    @Test("the group is one segment.translate by the drag's offset, every segment with its version")
    func oneCall() throws {
        let call = try SegmentEdit.translate([line("a", version: 2), line("b", version: 7)], by: [0.05, -0.1]).get()
        let data = try JSONEncoder().encode(call.params)
        let params = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(call.action == "segment.translate")
        #expect(params["dx"] as? Double == 0.05)
        #expect(params["dy"] as? Double == -0.1)
        let segments = try #require(params["segments"] as? [[String: Any]])
        #expect(segments.map { $0["segment_id"] as? String } == ["a", "b"])
        #expect(segments.map { $0["expected_version"] as? Int } == [2, 7])
    }

    @Test("an unsaved segment in the group refuses the move; an empty selection sends nothing")
    func refusals() {
        #expect(SegmentEdit.translate([line("a", version: 2), line("b", version: nil)], by: [0.1, 0]) == .failure(.versionUnknown))
        #expect(SegmentEdit.translate([], by: [0.1, 0]) == .failure(.tooFew))
    }
}
