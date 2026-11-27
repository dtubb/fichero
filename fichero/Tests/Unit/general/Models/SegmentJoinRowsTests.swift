@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.join-lines-in-the-same-row`,
/// `segment-editor.join-rows-says-what-it-will-do`. What breaks without these: a join sent with no version, a kept line
/// nobody expected, a menu that joins without saying how many lines it touches, or a selection lost after the join.
struct SegmentJoinRowsTests {
    private func segment(_ id: String, version: Int?) -> Segment {
        let anchor = SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "page-1", rect: [0, 0, 1, 1]))
        return Segment(
            id: id, provisional: false, documentId: "page-1", passId: "imported",
            kind: "line", kindRaw: nil, version: version, provenanceKind: .externalImport, anchor: anchor,
            baseline: nil, text: nil, confidence: nil, language: nil, script: nil, direction: nil,
            sourceArtifactId: nil, boxIndex: 0, pageIndex: nil, metadata: nil
        )
    }

    @Test("one segment.join_rows keeps the first of each row, every line with its version")
    func oneCallForEveryRow() throws {
        let call = try SegmentEdit.joinRows(
            [["a", "b"], ["c", "d"]], segments: ["a", "b", "c", "d", "e"].enumerated().map { segment($1, version: $0 + 1) }
        ).get()
        #expect(call.action == "segment.join_rows")
        let params = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(call.params)) as? [String: Any])
        let groups = try #require(params["groups"] as? [[String: Any]])
        #expect(groups.map { $0["keep_id"] as? String } == ["a", "c"])
        #expect(groups.map { $0["segment_ids"] as? [String] } == [["a", "b"], ["c", "d"]])
        #expect(params["expected_versions"] as? [String: Int] == ["a": 1, "b": 2, "c": 3, "d": 4])
    }

    @Test("no rows, or a line with no version, sends nothing")
    func refusals() {
        #expect(SegmentEdit.joinRows([], segments: []) == .failure(.tooFew))
        let unversioned = [segment("a", version: 1), segment("b", version: nil)]
        #expect(SegmentEdit.joinRows([["a", "b"]], segments: unversioned) == .failure(.versionUnknown))
        #expect(SegmentEdit.joinRows([["a", "b"]], segments: [segment("a", version: 1)]) == .failure(.versionUnknown))
    }

    @Test("after the join each row's kept line is selected, after the undo every line of every row")
    func selection() {
        let rows = [["a", "b"], ["c", "d"]]
        #expect(SegmentEdit.selectionAfterJoinRows(rows: rows, live: ["a", "c", "e"]) == ["a", "c"])
        #expect(SegmentEdit.selectionAfterJoinRows(rows: rows, live: ["a", "b", "c", "d"]) == ["a", "b", "c", "d"])
    }

    @Test("the notice says how many lines join into how many rows and how many are left alone, before and after")
    func notices() {
        let rows = [["a", "b"], ["c", "d", "e"]]
        #expect(SegmentEdit.joinRowsWillSay(rows: rows, leftAlone: 1) == "Joining 5 lines into 2 rows; 1 line left alone")
        #expect(SegmentEdit.joinRowsDone(rows: [["a", "b"]], leftAlone: 0) == "Joined 2 lines into 1 row")
        #expect(SegmentEdit.joinRowsNothing == "No two lines share a row, so nothing was joined")
    }
}
