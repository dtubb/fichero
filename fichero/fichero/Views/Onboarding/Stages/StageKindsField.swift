import FicheroAPIClient
import SwiftUI

/// The words of an open stage question (#5805, `source.onboard.stages.kinds-are-open-ended`). Pure, for the tests.
enum StageKinds {
    /// The kinds with one more the person typed or pressed: trimmed, and not again under another case.
    static func adding(_ word: String, to kinds: [String]) -> [String] {
        let trimmed = word.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !kinds.contains(where: { $0.caseInsensitiveCompare(trimmed) == .orderedSame }) else {
            return kinds
        }
        return kinds + [trimmed]
    }

    /// The kinds with `id` ticked or unticked, in the order they are held; ticking one already held changes nothing.
    static func toggled(_ id: String, on: Bool, in kinds: [String]) -> [String] {
        on ? adding(id, to: kinds) : kinds.filter { $0.caseInsensitiveCompare(id) != .orderedSame }
    }

    /// The saved answer for every box unticked; the engine reads it as none. `[]` is an old project's "every kind" (## 1110).
    static let none = "none"

    /// What the tick boxes show for a saved answer: `[]` (an old project) is every box ticked, `none` is every box unticked.
    static func shown(_ saved: [String], options: [String]) -> [String] {
        guard !options.isEmpty else { return saved }
        if saved.isEmpty { return options }
        return saved.filter { $0.caseInsensitiveCompare(none) != .orderedSame }
    }

    /// What to save for the kinds shown: nothing left means `none`, never `[]` (that would read as every kind).
    static func saved(_ shown: [String], options: [String]) -> [String] {
        shown.isEmpty && !options.isEmpty ? [none] : shown
    }

    /// The kinds held that no tick box names: the ones the person typed.
    static func extras(_ kinds: [String], options: [String]) -> [String] {
        kinds.filter { kind in !options.contains { $0.caseInsensitiveCompare(kind) == .orderedSame } }
    }

    /// What a sample try found, less what the person already has: the chips offered.
    static func unchosen(_ suggestions: [String], chosen: [String]) -> [String] {
        suggestions.filter { found in !chosen.contains { $0.caseInsensitiveCompare(found) == .orderedSame } }
    }
}

/// An open stage question: every kind unless the person types some, each kept as typed and removable, with chips for
/// the kinds a sample try found. No fixed list of options (the engine sends none).
struct StageKindsField: View {
    let question: Components.Schemas.StageQuestion
    @Binding var answer: StageAnswer?
    @State private var typed = ""

    private var saved: [String] { if case .many(let words) = answer { words } else { [] } }
    private var optionIds: [String] { (question.options ?? []).map(\.id) }
    /// What the boxes show (a saved `[]` is all ticked, `none` all unticked).
    private var kinds: [String] { StageKinds.shown(saved, options: optionIds) }

    private func save(_ shown: [String]) { answer = .many(StageKinds.saved(shown, options: optionIds)) }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            let options = question.options ?? []
            if !options.isEmpty {
                // Tick boxes in plain words, all ticked to begin with (`source.onboard.stages.names-kinds-are-tick-boxes`).
                FlowLayout(spacing: 6) {
                    ForEach(options, id: \.id) { option in
                        Toggle(option.title, isOn: Binding(
                            get: { kinds.contains { $0.caseInsensitiveCompare(option.id) == .orderedSame } },
                            set: { save(StageKinds.toggled(option.id, on: $0, in: kinds)) }
                        ))
                        .setupCheckbox()
                    }
                }
            }
            let extras = StageKinds.extras(kinds, options: options.map(\.id))
            if kinds.isEmpty {
                Text(options.isEmpty ? "Every kind" : "None: Names is off for this project")
                    .font(.callout).foregroundStyle(.secondary)
            } else if !extras.isEmpty || options.isEmpty {
                FlowLayout(spacing: 6) {
                    ForEach(options.isEmpty ? kinds : extras, id: \.self) { kind in
                        Button {
                            save(kinds.filter { $0 != kind })
                        } label: {
                            Label(kind, systemImage: "xmark.circle.fill")
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .accessibilityLabel("Remove \(kind)")
                    }
                }
            }
            if question.readByAStep != true {
                // Kept with the answers, but no run reads it yet (review 180): said, not implied.
                Text("Saved with your answers. No step uses this yet.").font(.caption).foregroundStyle(.secondary)
            }
            TextField(options.isEmpty ? "Type a kind, then Return" : "Another kind, then Return", text: $typed)
                .textFieldStyle(.roundedBorder)
                .onSubmit { add(typed) }
            let found = StageKinds.unchosen(question.suggestions ?? [], chosen: kinds)
            if !found.isEmpty {
                Text("Found on your sample pages").font(.caption).foregroundStyle(.secondary)
                FlowLayout(spacing: 6) {
                    ForEach(found, id: \.self) { kind in
                        Button(kind) { add(kind) }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                    }
                }
            }
        }
    }

    private func add(_ word: String) {
        save(StageKinds.adding(word, to: kinds))
        typed = ""
    }
}

#Preview("Open kinds: none chosen, two found on the samples") {
    @Previewable @State var answer: StageAnswer? = .many([])
    StageKindsField(
        question: Components.Schemas.StageQuestion(
            key: "entity_kinds", ask: "Which kinds of names?", kind: .many,
            readByAStep: true, openEnded: true, suggestions: ["people", "places"]
        ),
        answer: $answer
    )
    .padding()
    .frame(width: 420)
}
