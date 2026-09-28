import SwiftUI

/// The Inspector's Rights section (5.8): what applies here, in words, and the records that add up to
/// it, library first; Set (a model rule, a label) and Withdraw, each one audited action with ⌘Z. The
/// engine decides who may act (owners and editors, `source.rights.who-acts`); a refusal is said here, as
/// the engine gave it. Restricting to named readers is not offered yet: the app cannot list accounts.
struct InspectorRightsSection: View {
    /// "segment" or "document".
    let targetKind: String
    let targetId: String
    let pageId: String

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(\.undoManager) private var undoManager
    @State private var answer = InspectorRights.Answer()
    @State private var failure: String?
    @State private var labeling = false
    @State private var label = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("Rights").font(.headline)
                Spacer()
                setMenu
            }
            ForEach(InspectorRights.effect(answer)) { line in
                HStack(alignment: .firstTextBaseline) {
                    Text(line.title).font(.subheadline).foregroundStyle(.secondary)
                    Spacer(minLength: 8)
                    Text(line.value).font(.body).multilineTextAlignment(.trailing)
                }
                .accessibilityElement(children: .combine)
            }
            ForEach(InspectorRights.rows(answer.records, targetKind: targetKind, targetId: targetId, pageId: pageId)) { row in
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(row.place).font(.body)
                        Text(row.detail).font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("Withdraw") {
                        run("rights.withdraw", RightsRecordIdRequest(recordId: row.recordId), "Withdraw Rights Record")
                    }
                    .buttonStyle(.borderless)
                    .font(.caption)
                    .help("Withdraw this record; it is kept in the record, not deleted")
                }
                .accessibilityElement(children: .combine)
            }
            if let failure {
                Text(failure).font(.caption).foregroundStyle(.secondary)
            }
        }
        .task(id: targetId) { await reload() }
        .alert("Add a Label", isPresented: $labeling) {
            TextField("e.g. TK Attribution", text: $label)
            Button("Add") {
                let text = label.trimmingCharacters(in: .whitespaces)
                if !text.isEmpty {
                    run("rights.set", RightsSetRequest(targetKind: targetKind, targetId: targetId, labels: [text]),
                        "Add Rights Label")
                }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("A community's or a project's label, on \(targetKind == "segment" ? "this segment" : "this page").")
        }
    }

    private var setMenu: some View {
        Menu("Set") {
            Section("Models") {
                ForEach(InspectorRights.modelUses, id: \.value) { use in
                    Button(use.title) {
                        run("rights.set", RightsSetRequest(targetKind: targetKind, targetId: targetId, modelUse: use.value),
                            "Set Model Rule")
                    }
                }
            }
            Button("Add Label…") { label = ""; labeling = true }
        }
        .menuStyle(.button)
        .buttonStyle(.borderless)
        .fixedSize()
        .font(.caption)
        .help("Add a rights record here; records only tighten what is above")
    }

    private func reload() async {
        guard let segmentService else { return }
        answer = (try? await RightsService(client: segmentService.client)
            .effective(targetKind: targetKind, targetId: targetId)) ?? InspectorRights.Answer()
    }

    private func run<Params: Encodable>(_ name: String, _ params: Params, _ actionName: String) {
        guard let actionsService = actionStore?.actionsService else { return }
        let undoManager = undoManager
        failure = nil
        Task {
            do {
                try await AuditedAction.run(
                    name, params: params, actionName: actionName, actionsService: actionsService,
                    undoManager: undoManager, afterChange: { await reload() }
                )
            } catch {
                // Said as the engine answered, never guessed: a refusal to someone who may not act
                // (`source.rights.who-acts`) and an engine that could not be reached read differently.
                failure = "Not changed: \(error.localizedDescription)"
            }
        }
    }
}
