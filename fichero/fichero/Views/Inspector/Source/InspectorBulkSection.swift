import SwiftUI

/// The multi-selection's Hands, Certainty and Rights, each ONE audited action over every selected line
/// (`source.inspector.multi-selection.acts-at-once`, #6082): one step, one ⌘Z. The engine refuses the whole batch when
/// any line cannot take it, and says why here, as it answered. The request is built by `SegmentBulkEdit`.
struct InspectorBulkSection: View {
    let selectedIds: [String]

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(WindowSteps.self) private var windowSteps: WindowSteps?
    @State private var hands: [InspectorHands.ListedHand] = []
    @State private var note: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("\(selectedIds.count) lines, at once").font(.headline)
                Spacer()
                handMenu
                markMenu
                rightsMenu
            }
            if let note {
                Text(note).font(.caption).foregroundStyle(.secondary)
            }
        }
        .task {
            guard let segmentService else { return }
            hands = (try? await HandService(client: segmentService.client).hands()) ?? []
        }
    }

    private var handMenu: some View {
        Menu("Hand") {
            if hands.isEmpty {
                Text("No hands in this project yet")
            }
            ForEach(hands, id: \.id) { hand in
                Button(hand.label) {
                    send("hand.attribute_many", SegmentBulkEdit.attributeHand(hand.id, to: selectedIds), "Attribute Hand")
                }
            }
        }
        .bulkMenuStyle()
        .help("Attribute every selected line to a hand")
    }

    private var markMenu: some View {
        Menu("Certainty") {
            ForEach(InspectorEditorial.Mark.allCases) { mark in
                Button(mark.title) {
                    send("editorial.record_many", SegmentBulkEdit.record(mark.rawValue, on: selectedIds), "Mark \(mark.title)")
                }
            }
        }
        .bulkMenuStyle()
        .help("Mark every selected line's whole reading")
    }

    private var rightsMenu: some View {
        Menu("Rights") {
            ForEach(InspectorRights.modelUses, id: \.value) { use in
                Button(use.title) {
                    send("rights.set_many", SegmentBulkEdit.setRights(on: selectedIds, restricted: false, modelUse: use.value),
                         "Set Model Rule")
                }
            }
        }
        .bulkMenuStyle()
        .help("Set the same model rule on every selected line")
    }

    private func send<Params: Encodable>(_ action: String, _ built: Result<Params, SegmentBulkEdit.Refusal>, _ verb: String) {
        note = nil
        switch built {
        case .failure(let refusal):
            note = refusal.words
        case .success(let params):
            guard let actionsService = actionStore?.actionsService else { return }
            let steps = windowSteps, stepName = SegmentBulkEdit.stepName(verb, count: (try? SegmentBulkEdit.lines(selectedIds).get().count) ?? selectedIds.count)
            Task {
                do {
                    try await AuditedAction.run(action, params: params, actionName: stepName, actionsService: actionsService, steps: steps)
                } catch {
                    note = "Not changed: \(error.localizedDescription)"
                }
            }
        }
    }
}

private extension View {
    func bulkMenuStyle() -> some View {
        menuStyle(.button).buttonStyle(.borderless).fixedSize().font(.caption)
    }
}
