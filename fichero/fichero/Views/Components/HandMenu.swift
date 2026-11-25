import SwiftUI

/// Hand ▸ for a selection of segments: the project's hands, New Hand…, Remove Hand, headed by the selection's hand or Mixed
/// (#5161; `source.hand.assign-from-every-surface`). Mounted by `SegmentVerbMenu`, so the Order list's row menu and the
/// Reader's line menu both carry it; each verb is one audited action (`HandAssignment`), one ⌘Z.
struct HandMenu: View {
    let ids: [String]
    var onNote: (String?) -> Void = { _ in }

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(WindowSteps.self) private var windowSteps: WindowSteps?
    @State private var hands: [InspectorHands.ListedHand] = []
    @State private var attributions: [String: [InspectorHands.Attribution]] = [:]
    @State private var naming = false
    @State private var newLabel = ""

    private var handService: HandService? { segmentService.map { HandService(client: $0.client) } }

    var body: some View {
        Menu("Hand: \(HandAssignment.summary(selection: ids, attributions: attributions, hands: hands))") {
            ForEach(hands) { hand in
                Button(hand.label) { attribute(to: hand.id) }
            }
            if !hands.isEmpty { Divider() }
            Button("New Hand…") { newLabel = ""; naming = true }
            Button("Remove Hand") { remove() }
                .disabled(HandAssignment.remove(selection: ids, attributions: attributions) == nil)
        }
        .task(id: ids) { await reload() }
        .alert("New Hand", isPresented: $naming) {
            TextField("A name, e.g. hand B", text: $newLabel)
            Button("Create and Attribute") { createAndAttribute() }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("A hand in the project's list; the selected segments are attributed to it.")
        }
    }

    private func reload() async {
        guard let handService else { return }
        hands = (try? await handService.hands()) ?? []
        var found: [String: [InspectorHands.Attribution]] = [:]
        for id in ids { found[id] = (try? await handService.attributions(segmentId: id)) ?? [] }
        attributions = found
    }

    private func attribute(to handId: String) {
        HandAssignment.remember(handId)
        send(HandAssignment.attribute(handId: handId, segmentIds: ids))
    }

    private func remove() {
        send(HandAssignment.remove(selection: ids, attributions: attributions))
    }

    private func send(_ call: HandAssignment.Call?) {
        guard let call, let actionsService = actionStore?.actionsService else { return }
        let steps = windowSteps, note = onNote
        Task {
            do {
                _ = try await AuditedAction.run(
                    call.action, params: call.params, actionName: call.name, actionsService: actionsService,
                    steps: steps, afterChange: { await reload() }
                )
                note(nil)
            } catch { note("That did not happen: \(error.localizedDescription)") }
        }
    }

    /// A new hand, then the selection attributed to it: two audited actions, each undoable.
    private func createAndAttribute() {
        let label = newLabel.trimmingCharacters(in: .whitespaces)
        guard !label.isEmpty, let actionsService = actionStore?.actionsService else { return }
        let known = Set(hands.map(\.id)), steps = windowSteps, note = onNote
        Task {
            do {
                _ = try await AuditedAction.run(
                    "hand.create", params: HandCreateRequest(label: label), actionName: "New Hand",
                    actionsService: actionsService, steps: steps, afterChange: { await reload() }
                )
                guard let handId = hands.first(where: { !known.contains($0.id) && $0.label == label })?.id else { return }
                attribute(to: handId)
            } catch { note("That did not happen: \(error.localizedDescription)") }
        }
    }
}
