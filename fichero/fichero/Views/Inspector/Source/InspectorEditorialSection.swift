import SwiftUI

/// The Inspector's Certainty and Damage section (`build-notes-inspector.md` 5.5): the text as the
/// editor prints it (drawn from the facts, never typed), each fact with where, how much, why, who and
/// how sure, and the verbs -- mark the whole segment's reading, withdraw a fact. Each verb is one
/// audited action, undoable with ⌘Z.
struct InspectorEditorialSection: View {
    let segmentId: String
    /// The counting transcription: what a Mark covers. Nil when no reading counts.
    let reading: InspectorText.Reading?

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(\.undoManager) private var undoManager
    @State private var answer = InspectorEditorial.Answer(facts: [], drawn: nil)

    private var service: EditorialService? { segmentService.map { EditorialService(client: $0.client) } }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("Certainty and Damage").font(.headline)
                Spacer()
                markMenu
            }
            if !answer.facts.isEmpty, let drawn = answer.drawn {
                Text(drawn).font(.body).textSelection(.enabled)
                    .accessibilityLabel("The text as the editor prints it: \(drawn)")
            }
            ForEach(InspectorEditorial.rows(answer.facts)) { row in
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(row.title).font(.body)
                        Text(row.detail).font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("Withdraw") {
                        run("editorial.withdraw", EditorialFactRequest(factId: row.factId), "Withdraw Editorial Fact")
                    }
                    .buttonStyle(.borderless)
                    .font(.caption)
                    .help("Withdraw this fact; it is kept in the record, not deleted")
                }
                .accessibilityElement(children: .combine)
            }
            if answer.facts.isEmpty {
                Text("Nothing is recorded about the state of this text.").font(.caption).foregroundStyle(.secondary)
            }
        }
        .task(id: segmentId) { await reload() }
    }

    private var markMenu: some View {
        Menu("Mark") {
            ForEach(InspectorEditorial.Mark.allCases) { mark in
                Button(mark.title) {
                    guard let params = InspectorEditorial.record(mark, segmentId: segmentId, reading: reading) else { return }
                    run("editorial.record", params, "Mark \(mark.title)")
                }
            }
        }
        .menuStyle(.button)
        .buttonStyle(.borderless)
        .fixedSize()
        .font(.caption)
        .disabled(reading == nil)
        .help(reading == nil ? "No reading counts for this segment, so there is no text to mark"
                             : "Say something about the state of this segment's whole text")
    }

    private func reload() async {
        guard let service else { return }
        answer = (try? await service.facts(segmentId: segmentId)) ?? InspectorEditorial.Answer(facts: [], drawn: nil)
    }

    private func run<Params: Encodable>(_ name: String, _ params: Params, _ actionName: String) {
        guard let actionsService = actionStore?.actionsService else { return }
        let undoManager = undoManager
        Task {
            _ = try? await AuditedAction.run(
                name, params: params, actionName: actionName, actionsService: actionsService,
                undoManager: undoManager, afterChange: { await reload() }
            )
        }
    }
}

#if DEBUG
#Preview("Certainty and damage: an unclear stretch and a lost one") {
    let rows = InspectorEditorial.rows([
        .init(id: "f1", kind: "unclear", charStart: 0, charEnd: 3, reason: "faded", certainty: 0.8, createdBy: "owner"),
        .init(id: "f2", kind: "lost", charStart: 5, extentQuantity: 2, extentUnit: "character", reason: "a hole",
              source: "file: p.flor.2.133.xml")
    ])
    VStack(alignment: .leading) {
        Text("ܐ̣ܒ̣ܪ̣ܗܡ[.2] ܐܘܠܕ")
        ForEach(rows) { row in
            Text(row.title)
            Text(row.detail).font(.caption)
        }
    }
    .padding()
}
#endif
