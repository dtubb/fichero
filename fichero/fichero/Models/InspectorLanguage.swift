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
