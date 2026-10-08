import SwiftUI

/// "Change date" on a statement (#5602): a year, a year and month, or a full date, sent as the claim's
/// `time_start` through `claim.patch`. Save is off until the words are a date.
struct StatementDateEditor: View {
    let onCancel: () -> Void
    let onSave: (String) -> Void
    @State private var typed = ""

    var body: some View {
        HStack(spacing: 6) {
            TextField("Date (1650, 1650-03, 1650-03-01)", text: $typed)
                .textFieldStyle(.roundedBorder)
                .onSubmit(save)
            Button("Cancel", action: onCancel)
            Button("Save", action: save)
                .disabled(InspectorStatements.claimDate(typed) == nil)
        }
        .font(.callout)
    }

    private func save() {
        guard let date = InspectorStatements.claimDate(typed) else { return }
        onSave(date)
    }
}

/// "Not this person… (choose another)" on a mention (#5602): the entity search the claim editor already
/// uses, and the pick re-points the name at this mark (`mention.repoint`).
struct MentionRepointEditor: View {
    let mention: InspectorStatements.Mention
    let onCancel: () -> Void
    let onPick: (String) -> Void
    @State private var entityId: String?
    @State private var name = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("“\(mention.excerpt ?? mention.name)” is not \(mention.name). Who is it?")
                .font(.caption).foregroundStyle(.secondary)
            ClaimSubjectEntityPicker(subjectEntityId: $entityId, subjectName: $name, role: "Who it is",
                                     startsExpanded: true)
            Button("Cancel", action: onCancel).font(.callout)
        }
        .onChange(of: entityId) { _, picked in
            guard let picked, picked != mention.id else { return }
            onPick(picked)
        }
    }
}

/// "Fix the words" on a mention (#5602): select the right words on the line; Save sends them as the
/// mention's span in the page text (`mention.respan`). The line is shown to select in, never to edit.
struct MentionRespanEditor: View {
    let mention: InspectorStatements.Mention
    let lineText: String
    let onCancel: () -> Void
    let onSave: ((start: Int, end: Int)) -> Void
    @State private var shown = ""
    @State private var selection: TextSelection?

    private var target: (start: Int, end: Int)? {
        guard shown == lineText, case .selection(let range) = selection?.indices else { return nil }
        // The range indexes `shown`, the very string the editor holds (equal to the line).
        return InspectorStatements.respanTarget(mention, lineText: shown, selection: range)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Select the words that name \(mention.name), then Save.")
                .font(.caption).foregroundStyle(.secondary)
            TextEditor(text: $shown, selection: $selection)
                .font(.body)
                .frame(minHeight: 44, maxHeight: 88)
                .onChange(of: shown) { _, now in
                    if now != lineText { shown = lineText }
                }
            HStack(spacing: 6) {
                Button("Cancel", action: onCancel)
                Button("Save") { if let target { onSave(target) } }
                    .disabled(target == nil)
            }
            .font(.callout)
        }
        .onAppear { shown = lineText }
    }
}

#if DEBUG
#Preview("Change date on a statement") {
    StatementDateEditor(onCancel: {}, onSave: { _ in }).padding().frame(width: 340)
}

#Preview("Fix the words of a name on its line") {
    MentionRespanEditor(
        mention: .init(id: "e1", name: "Juan de Mosquera", entityType: "person", excerpt: "Juan",
                       sourceCharStart: 112, sourceCharEnd: 116, charStart: 12, charEnd: 16),
        lineText: "En Istmina, Juan de Mosquera vecino de esta villa",
        onCancel: {}, onSave: { _ in }
    )
    .padding()
    .frame(width: 340)
}

#Preview("Not this person: choose another") {
    MentionRepointEditor(
        mention: .init(id: "e1", name: "Juan de Mosquera", entityType: "person", excerpt: "Juan de Mosquera",
                       sourceCharStart: 112, sourceCharEnd: 128, charStart: 12, charEnd: 28),
        onCancel: {}, onPick: { _ in }
    )
    .padding()
    .frame(width: 340)
}
#endif
