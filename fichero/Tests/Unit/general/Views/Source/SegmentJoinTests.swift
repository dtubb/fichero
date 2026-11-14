@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.merge-lines`. The segment
/// editor's Join asks the engine to join the lines' outlines, baselines and readings and to move lines
/// from other regions into the first one's; the Reader's backspace join asks for neither, so its refusal
/// across regions stands. What breaks without these: a Join that merges the text and leaves the outline
/// of one line, or a Reader join that silently pulls a line out of its paragraph.
@MainActor
@Suite(.tags(.paleography))
struct SegmentJoinTests {
    private func line(_ id: String, version: Int?) -> Segment {
        let anchor = SourceAnchorValue(
            generated: Components.Schemas.SourceAnchorOutput(documentId: "page-1", rect: [0, 0.2, 1, 0.05])
        )
        return Segment(
            id: id, provisional: false, documentId: "page-1", passId: "imported",
            kind: "line", kindRaw: nil, version: version, provenanceKind: .externalImport, anchor: anchor,
            baseline: nil, text: nil, confidence: nil, language: nil, script: nil, direction: nil,
            sourceArtifactId: nil, boxIndex: 0, pageIndex: nil, metadata: nil
        )
    }

    private func json(_ call: SegmentEdit.Call) throws -> [String: Any] {
        let data = try JSONEncoder().encode(call.params)
        return try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    @Test("Join is enabled for two or more selected segments and not for one or none")
    func joinNeedsTwoOrMore() {
        #expect(!SegmentMenuContent.canJoin(selected: 0))
        #expect(!SegmentMenuContent.canJoin(selected: 1))
        #expect(SegmentMenuContent.canJoin(selected: 2))
        #expect(SegmentMenuContent.canJoin(selected: 7))
    }

    @Test("the editor's Join asks for the joined geometry and the move across regions, first picked kept")
    func editorJoinAsksForTheJoinedLine() throws {
        let call = try SegmentEdit.join([line("l2", version: 1), line("l1", version: 4)], asLines: true).get()
        let params = try json(call)
        #expect(call.action == "segment.merge")
        #expect(params["keep_id"] as? String == "l2")
        #expect(params["expected_versions"] as? [String: Int] == ["l2": 1, "l1": 4])
        #expect(params["join_geometry"] as? Bool == true)
        #expect(params["move_into_region"] as? Bool == true)
    }

    @Test("the Reader's join sends neither flag, so the engine keeps its shape and its region refusal")
    func readerJoinSendsNoFlags() throws {
        let params = try json(SegmentEdit.join([line("l1", version: 1), line("l2", version: 1)]).get())
        #expect(params["join_geometry"] == nil)
        #expect(params["move_into_region"] == nil)
    }
    /// `segment-editor.merge-regions`: after regions are merged the page's order numbers show for two seconds.
    @Test("a Join of regions flashes the order numbers, which go again by themselves; a Join of lines does not")
    func mergedRegionsFlashTheOrder() async throws {
        var region = line("r1", version: 1)
        region.kind = "region"
        var other = line("r2", version: 1)
        other.kind = "region"
        #expect(SegmentEdit.joinsRegions([region, other]))
        #expect(!SegmentEdit.joinsRegions([region, line("a", version: 1)]))
        #expect(!SegmentEdit.joinsRegions([region]))

        let window = WindowState(libraryId: UUID())
        window.flashOrderOverlay(for: 0.05)
        #expect(window.orderOverlayFlash)
        try await Task.sleep(for: .milliseconds(400))
        #expect(!window.orderOverlayFlash, "the numbers go again by themselves")
    }
}
