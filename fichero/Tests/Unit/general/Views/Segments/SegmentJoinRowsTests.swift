@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.join-lines-in-the-same-row`,
/// `segment-editor.join-rows-says-what-it-will-do`. Join Lines in the Same Row sends ONE `segment.join_rows` for the lines
/// asked about (only lines, two or more), says what it did, and is offered with the Join chord's sibling. What breaks without
/// these: a join that sends words or regions the engine would refuse, or says nothing about the rows it left alone.
@MainActor
@Suite(.tags(.paleography))
struct SegmentJoinRowsTests {
    private func segment(_ id: String, kind: String = "line", version: Int? = 1) -> Segment {
        let anchor = SourceAnchorValue(
            generated: Components.Schemas.SourceAnchorOutput(documentId: "page-1", rect: [0, 0.2, 1, 0.05])
        )
        return Segment(
            id: id, provisional: false, documentId: "page-1", passId: "imported",
            kind: kind, kindRaw: nil, version: version, provenanceKind: .externalImport, anchor: anchor,
            baseline: nil, text: nil, confidence: nil, language: nil, script: nil, direction: nil,
            sourceArtifactId: nil, boxIndex: 0, pageIndex: nil, metadata: nil
        )
    }

    @Test("one segment.join_rows with the lines' ids and versions")
    func oneActionWithVersions() throws {
        let call = try SegmentEdit.joinRows([segment("a", version: 2), segment("b", version: 5)]).get()
        #expect(call.action == "segment.join_rows")
        let data = try JSONEncoder().encode(call.params)
        let body = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(body["segment_ids"] as? [String] == ["a", "b"])
        #expect(body["expected_versions"] as? [String: Int] == ["a": 2, "b": 5])
    }

    @Test("only lines are sent: a word or a region in the selection is left out")
    func onlyLines() throws {
        let call = try SegmentEdit.joinRows([segment("a"), segment("w", kind: "word"), segment("b"), segment("r", kind: "region")]).get()
        let data = try JSONEncoder().encode(call.params)
        let body = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(body["segment_ids"] as? [String] == ["a", "b"])
    }

    @Test("fewer than two lines is refused, and a line with no version is refused")
    func refusals() {
        #expect(SegmentEdit.joinRows([segment("a")]) == .failure(.tooFew))
        #expect(SegmentEdit.joinRows([segment("a"), segment("w", kind: "word")]) == .failure(.tooFew))
        #expect(SegmentEdit.joinRows([segment("a"), segment("b", version: nil)]) == .failure(.versionUnknown))
    }

    @Test("the notice says what was joined and what was left alone")
    func notice() {
        #expect(SegmentEdit.joinRowsNotice(rows: 2, leftAlone: 1) == "Joined 2 rows; 1 line left alone")
        #expect(SegmentEdit.joinRowsNotice(rows: 1, leftAlone: 0) == "Joined 1 row")
        #expect(SegmentEdit.joinRowsNotice(rows: 3, leftAlone: 4) == "Joined 3 rows; 4 lines left alone")
    }

    @Test("after the join the lines asked about that still exist are selected")
    func selectionAfter() {
        #expect(SegmentEdit.selectionAfterJoinRows(asked: ["a", "b", "c"], live: ["a", "c"]) == ["a", "c"])
        #expect(SegmentEdit.selectionAfterJoinRows(asked: ["a", "b"], live: ["a", "b"]) == ["a", "b"])
    }

    @Test("with nothing selected the lines of the page are the ones asked about")
    func pageLines() {
        let page = [segment("a"), segment("w", kind: "word"), segment("r", kind: "region"), segment("b")]
        #expect(SegmentEdit.linesToJoinInRows(selected: [], page: page).map(\.id) == ["a", "b"])
        #expect(SegmentEdit.linesToJoinInRows(selected: [page[3]], page: page).map(\.id) == ["b"])
    }
}
