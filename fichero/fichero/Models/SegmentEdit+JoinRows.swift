import Foundation

/// Join Lines in the Same Row (`segment-editor.join-lines-in-the-same-row`).
extension SegmentEdit {
    /// JOIN LINES IN THE SAME ROW (`segment-editor.join-lines-in-the-same-row`): the lines among `segments`, in ONE
    /// `segment.join_rows` and one undo. The engine groups the rows and says which lines it left alone.
    static func joinRows(_ segments: [Segment]) -> Result<Call, Refusal> {
        let lines = segments.filter { $0.kind.lowercased() == "line" }
        guard lines.count >= 2 else { return .failure(.tooFew) }
        guard let versions = versions(of: lines) else { return .failure(.versionUnknown) }
        return .success(Call(
            action: "segment.join_rows",
            params: .joinRows(SegmentCutWordsRequest(segmentIds: lines.map(\.id), expectedVersions: versions))
        ))
    }

    /// The segments Join Lines in the Same Row looks at: the selection, or every segment of the page when nothing is selected.
    static func linesToJoinInRows(selected: [Segment], page: [Segment]) -> [Segment] {
        (selected.isEmpty ? page : selected).filter { $0.kind.lowercased() == "line" }
    }

    /// The ids selected after Join Lines in the Same Row: the lines asked about that still exist (each row's kept line, the
    /// lines left alone, and every line again once an undo has brought the others back).
    static func selectionAfterJoinRows(asked: [String], live: Set<String>) -> [String] {
        asked.filter(live.contains)
    }

    /// What the page says after Join Lines in the Same Row: the rows joined, and the lines left alone.
    static func joinRowsNotice(rows: Int, leftAlone: Int) -> String {
        let joined = "Joined \(rows) \(rows == 1 ? "row" : "rows")"
        guard leftAlone > 0 else { return joined }
        return "\(joined); \(leftAlone) \(leftAlone == 1 ? "line" : "lines") left alone"
    }
}
