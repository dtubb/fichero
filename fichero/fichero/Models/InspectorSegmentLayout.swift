import Foundation

/// How the Inspector's segment pane is laid out (`source.editor.inspector-segment-pane-is-laid-out-in-groups`, #6413): its
/// groups in order, which sections hide while they hold nothing (their verb then in ONE Add menu in the head), and the
/// Details group's one line ("Spanish · Latin · Left to Right"). Pure: the sections load their own facts and say whether
/// they hold any; this only decides what shows.
enum InspectorSegmentLayout {
    /// The groups, in the order they are drawn under the head.
    enum Group: String, CaseIterable, Identifiable {
        case readings, details, history, linksAndRights

        var id: String { rawValue }

        var title: String {
            switch self {
            case .readings: "Readings"
            case .details: "Details"
            case .history: "History"
            case .linksAndRights: "Links and Rights"
            }
        }
    }

    /// A section hidden while empty, named as the Add menu names it.
    enum Addition: String, CaseIterable, Identifiable {
        case hand, certaintyMark

        var id: String { rawValue }

        var title: String {
            switch self {
            case .hand: "Hand"
            case .certaintyMark: "Certainty Mark"
            }
        }
    }

    /// A section hides while it holds nothing, unless the person asked for it from the Add menu.
    static func hides(_ addition: Addition, empty: Set<Addition>, revealed: Set<Addition>) -> Bool {
        empty.contains(addition) && !revealed.contains(addition)
    }

    /// The Add menu: the hidden sections, in the menu's order.
    static func addMenu(empty: Set<Addition>, revealed: Set<Addition>) -> [Addition] {
        Addition.allCases.filter { hides($0, empty: empty, revealed: revealed) }
    }

    /// The Details line: language, script and direction in words, those known only; nil when none is.
    static func detailsLine(_ rows: [InspectorLanguage.Row], locale: Locale = .current) -> String? {
        let words = ["language", "script", "direction"].compactMap { key -> String? in
            guard let row = rows.first(where: { $0.key == key }), known(row.value) else { return nil }
            switch key {
            case "language": return locale.localizedString(forLanguageCode: row.value) ?? row.value
            case "script": return locale.localizedString(forScriptCode: row.value) ?? row.value
            default: return row.value
            }
        }
        return words.isEmpty ? nil : words.joined(separator: " · ")
    }

    /// The Details line's tooltip: where each value came from, one per line ("Language: set by a person, for the project").
    static func detailsHelp(_ rows: [InspectorLanguage.Row]) -> String {
        rows.map { "\($0.title): \(known($0.value) ? $0.origin : $0.value)" }.joined(separator: "\n")
    }

    private static func known(_ value: String) -> Bool { value != "Unknown" && value != "Not determined" }
}
