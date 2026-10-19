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

    private var kinds: [String] { if case .many(let words) = answer { words } else { [] } }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if kinds.isEmpty {
                Text("Every kind").font(.callout).foregroundStyle(.secondary)
            } else {
                FlowLayout(spacing: 6) {
                    ForEach(kinds, id: \.self) { kind in
                        Button {
                            answer = .many(kinds.filter { $0 != kind })
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
            TextField("Type a kind, then Return", text: $typed)
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
        answer = .many(StageKinds.adding(word, to: kinds))
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
