import FicheroAPIClient
import Foundation

/// The Inspector's form for a selection (`source.editor.inspector-is-a-form-at-every-level`): the rows the engine answers
/// (`GET /api/segments/inspect`, `source.editor.inspector-form-comes-from-the-engine`), drawn as a grouped form. The app keeps
/// no table of rows, choices or states; it words what the engine says and sends the existing `segment.update_many` for a change
/// (`source.editor.inspector-form-edits-the-selection-at-once`). Pure: the view draws it and `SegmentEditRunner` sends.
struct InspectorForm: Equatable {
    /// The form's own accessibility identifier; a row's is `inspector.form.<key>`.
    static let identifier = "inspector.form"

    enum State: String, Equatable {
        case set, inherited, mixed, none
    }

    struct Choice: Equatable {
        let value: String
        let label: String
    }

    struct Row: Equatable, Identifiable {
        let key: String
        let label: String
        /// An on/off switch whose values are "true" and "false"; otherwise a menu (and a text field when `freeText`).
        let isToggle: Bool
        let state: State
        let value: String?
        /// Every distinct value when `mixed`.
        let values: [String]
        /// The level an inherited value came from.
        let inheritedFrom: String?
        let choices: [Choice]
        let freeText: Bool

        var id: String { key }

        var identifier: String { "\(InspectorForm.identifier).\(key.replacingOccurrences(of: "_", with: "-"))" }

        /// On only when every segment is on; a mixed switch is not on.
        var isOn: Bool { isToggle && state != .mixed && value == "true" }

        private func word(_ value: String) -> String {
            if isToggle { return value == "true" ? "On" : "Off" }
            return choices.first { $0.value == value }?.label ?? value
        }

        /// What the control shows.
        var displayValue: String {
            switch state {
            case .mixed: "Mixed"
            case .none: "Not set"
            case .set, .inherited: value.map(word) ?? "Not set"
            }
        }

        /// What VoiceOver reads after the label: the value and how it stands.
        var accessibilityValue: String {
            switch state {
            case .mixed: "Mixed: " + values.map(word).joined(separator: ", ")
            case .none: "Not set"
            case .set: "\(displayValue), set on this segment"
            case .inherited: "\(displayValue), inherited" + (inheritedFrom.map { " from \($0)" } ?? "")
            }
        }
    }

    let level: String
    let count: Int
    /// Ids the engine left out (not found, or on a page the person may not read).
    let withheld: Int
    let rows: [Row]

    /// "Region", "3 lines", "2 segments" (a selection across levels).
    var title: String {
        let noun = level == "mixed" ? "segment" : level
        return count == 1 ? noun.capitalized : "\(count) \(noun)s"
    }

    init(level: String, count: Int, withheld: Int, rows: [Row]) {
        self.level = level
        self.count = count
        self.withheld = withheld
        self.rows = rows
    }

    /// The engine's answer, in the engine's order.
    init(_ answer: Components.Schemas.SegmentInspectRead) {
        self.init(
            level: answer.level, count: answer.count, withheld: answer.withheld ?? 0,
            rows: answer.rows.map { row in
                Row(
                    key: row.key, label: row.label, isToggle: row.kind.rawValue == "toggle",
                    state: State(rawValue: row.state.rawValue) ?? .none, value: row.value, values: row.values ?? [],
                    inheritedFrom: row.inheritedFrom,
                    choices: (row.choices ?? []).map { Choice(value: $0.value, label: $0.label) },
                    freeText: row.freeText ?? false
                )
            }
        )
    }

    /// The attribute a row's control sets; nil for a key the form does not know or a typed code that is empty.
    static func attribute(rowKey: String, value: String) -> SegmentEdit.Attribute? {
        let value = value.trimmingCharacters(in: .whitespaces)
        guard !value.isEmpty else { return nil }
        switch rowKey {
        case "type": return .type(value)
        case "furniture": return .furniture(value == "true")
        case "language": return .language(value)
        case "script": return .script(value)
        case "direction": return .direction(value)
        case "line_progression": return .lineProgression(value)
        default: return nil
        }
    }

    /// A control's change as the existing action: ONE `segment.update_many` over every segment picked, so one ⌘Z undoes it.
    static func edit(rowKey: String, to value: String, on segments: [Segment]) -> Result<SegmentEdit.Call, SegmentEdit.Refusal> {
        guard let attribute = attribute(rowKey: rowKey, value: value) else { return .failure(.tooFew) }
        return SegmentEdit.set(attribute, on: segments)
    }
}
