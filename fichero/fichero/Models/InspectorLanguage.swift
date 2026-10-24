import Foundation

/// The Inspector's Language & script section (#5158; `build-notes-inspector.md` 5.3): the three facts
/// and the encoding for the inspected segment, each saying WHERE it came from
/// (`source.lang.says-where-from`) -- set on this segment, inherited from the page or the project,
/// read from the file, detected, or only a fallback. A fallback is shown as one, never as a fact.
enum InspectorLanguage {
    /// One fact as the engine resolved it (`SettingResolution`).
    struct Setting: Equatable {
        let key: String
        let value: String?
        let status: String
        let source: String
        let basis: String
        let level: String?
    }

    struct Row: Equatable, Identifiable {
        let key: String
        /// "Language", "Script", "Direction", "Encoding".
        let title: String
        /// The value, or what its absence means: "Unknown" when examined, "Not determined" otherwise.
        let value: String
        /// Where it came from, in words: "set on this segment", "from the file", "a fallback", ...
        let origin: String
        /// The engine's own sentence for why.
        let basis: String
        var id: String { key }
    }

    /// The rows in the order people read them.
    static func rows(_ settings: [Setting]) -> [Row] {
        let order = ["language", "script", "direction", "encoding"]
        return settings
            .sorted { (order.firstIndex(of: $0.key) ?? order.count) < (order.firstIndex(of: $1.key) ?? order.count) }
            .map { setting in
                Row(
                    key: setting.key, title: setting.key.capitalized,
                    value: setting.value.map { setting.key == "direction" ? SegmentEdit.directionName($0) : $0 }
                        ?? (setting.status == "unknown" && setting.source != "never_determined"
                            ? "Unknown" : "Not determined"),
                    origin: origin(source: setting.source, level: setting.level),
                    basis: setting.basis
                )
            }
    }

    /// The rows for a SELECTION of lines (`source.inspector.multi-selection`): per fact, the value when every selected line
    /// has it, else "Mixed" -- no value -- with the reason in the origin line. One line's settings read as its own rows.
    static func rows(selection perLine: [[Setting]]) -> [Row] {
        let tables = perLine.map(rows)
        guard tables.count > 1 else { return tables.first ?? [] }
        var keys: [String] = []
        for key in tables.flatMap({ $0.map(\.key) }) where !keys.contains(key) { keys.append(key) }
        return keys.compactMap { key -> Row? in
            let rowsOfKey = tables.compactMap { table in table.first { $0.key == key } }
            guard let first = rowsOfKey.first else { return nil }
            // A line with no such fact counts as a different answer: not every line agrees.
            let agree = rowsOfKey.count == tables.count && rowsOfKey.allSatisfy { $0.value == first.value }
            return agree ? first : Row(
                key: key, title: first.title, value: mixed, origin: "differs between the selected lines", basis: ""
            )
        }
    }

    /// What a selection shows: the rows, or why there are none (never a claim of agreement it did not check).
    enum SelectionRows: Equatable {
        case rows([Row])
        case note(String)
    }

    /// The rows of a selection from each line's read (`nil` where a read failed): more lines than `cap` are not read, and
    /// a failed read says so instead of reading as a line that differs or agrees (## 1075).
    static func selection(_ reads: [[Setting]?], total: Int, cap: Int) -> SelectionRows {
        if total > cap {
            return .note("\(total) lines are selected: too many to compare their language, script and direction here.")
        }
        let failed = reads.filter { $0 == nil }.count
        if failed > 0 {
            return .note("The settings of \(failed) selected \(failed == 1 ? "line" : "lines") could not be read, so they are not compared.")
        }
        return .rows(rows(selection: reads.compactMap { $0 }))
    }

    /// What a fact reads when the selected lines differ.
    static let mixed = "Mixed"

    /// Where a value came from, in words. A level (segment, page, folder, project) says where it was
    /// set; the source says how.
    static func origin(source: String, level: String?) -> String {
        guard let level else { return how(source) }
        return "\(how(source)), \(whereSet(level))"
    }

    private static func how(_ source: String) -> String {
        switch source {
        case "user": "set by a person"
        case "metadata": "from the file"
        case "detected": "detected"
        case "fallback": "a fallback"
        case "derived-from-script": "from the script"
        case "never_determined": "not determined"
        default: source.replacingOccurrences(of: "_", with: " ")
        }
    }

    private static func whereSet(_ level: String) -> String {
        switch level {
        case "segment": "on this segment"
        case "page", "document": "on the page"
        case "folder": "on the folder"
        case "project": "for the project"
        default: "at the \(level) level"
        }
    }
}
