import Foundation

/// Join Lines in the Same Row (`segment-editor.join-lines-in-the-same-row`): the engine's preview names the rows, this
/// turns them into the one `segment.join_rows` call and says what it will do and did. Pure; the Preview sends it.
extension SegmentEdit {
    /// One call joining every row of `rows` (each row's ids, the first kept), each line with the version read in `segments`.
    static func joinRows(_ rows: [[String]], segments: [Segment]) -> Result<Call, Refusal> {
        guard rows.contains(where: { $0.count >= 2 }) else { return .failure(.tooFew) }
        let ids = Set(rows.flatMap { $0 })
        guard let versions = versions(of: segments.filter { ids.contains($0.id) }), ids.allSatisfy({ versions[$0] != nil }) else {
            return .failure(.versionUnknown)
        }
        return .success(Call(
            action: "segment.join_rows",
            params: .joinRows(SegmentJoinRowsRequest(
                groups: rows.map { SegmentJoinRow(segmentIds: $0, keepId: $0[0]) }, expectedVersions: versions
            ))
        ))
    }

    /// The ids left selected after each re-read of the join (it, its undo, its redo): each row's kept line, or the row's
    /// lines once an undo has brought them back.
    static func selectionAfterJoinRows(rows: [[String]], live: Set<String>) -> [String] {
        rows.flatMap { selectionAfterJoin(joined: $0, live: live) }
    }

    /// What the menu says before it joins (`segment-editor.join-rows-says-what-it-will-do`).
    static func joinRowsWillSay(rows: [[String]], leftAlone: Int) -> String {
        let lines = rows.reduce(0) { $0 + $1.count }
        return "Joining \(lines) lines into \(rows.count) \(rows.count == 1 ? "row" : "rows")" + leftAloneWords(leftAlone)
    }

    /// What it says once the join landed.
    static func joinRowsDone(rows: [[String]], leftAlone: Int) -> String {
        let lines = rows.reduce(0) { $0 + $1.count }
        return "Joined \(lines) lines into \(rows.count) \(rows.count == 1 ? "row" : "rows")" + leftAloneWords(leftAlone)
    }

    /// What it says when no two lines share a row.
    static let joinRowsNothing = "No two lines share a row, so nothing was joined"

    private static func leftAloneWords(_ count: Int) -> String {
        count == 0 ? "" : "; \(count) \(count == 1 ? "line" : "lines") left alone"
    }
}
