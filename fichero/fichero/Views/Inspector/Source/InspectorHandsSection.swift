import SwiftUI

/// The Inspector's Hands section (#5161): who wrote this segment's ink, how sure, and who judged it --
/// every rival attribution shown -- and the verbs: attribute it to a hand (or a new one), withdraw an
/// attribution. Each verb is one audited action, undoable with ⌘Z.
struct InspectorHandsSection: View {
    let segmentId: String

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(\.undoManager) private var undoManager
    @State private var hands: [InspectorHands.ListedHand] = []
    @State private var attributions: [InspectorHands.Attribution] = []
    @State private var naming = false
    @State private var newLabel = ""

    private var handService: HandService? { segmentService.map { HandService(client: $0.client) } }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("Hands").font(.headline)
                Spacer()
                attributeMenu
            }
            ForEach(InspectorHands.rows(attributions, hands: hands)) { row in
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(row.ink).font(.body)
                        if !row.record.isEmpty {
                            Text(row.record).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    Spacer()
                    Button("Withdraw") {
                        run("hand.unattribute", HandUnattributeRequest(attributionId: row.attributionId), "Withdraw Attribution")
                    }
                        .buttonStyle(.borderless)
                        .font(.caption)
                        .help("Withdraw this attribution; it is kept in the record, not deleted")
                }
            }
            if attributions.isEmpty {
                Text("No hand is named for this segment.").font(.caption).foregroundStyle(.secondary)
            }
        }
        .task(id: segmentId) { await reload() }
        .alert("New Hand", isPresented: $naming) {
            TextField("A name, e.g. hand B", text: $newLabel)
            Button("Create and Attribute") { Task { await createAndAttribute() } }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("A hand in the project's list; this segment is attributed to it.")
        }
    }

    private var attributeMenu: some View {
        Menu("Attribute") {
            ForEach(hands) { hand in
                Button(hand.label) { run("hand.attribute", HandAttributeRequest(handId: hand.id, segmentId: segmentId), "Attribute Hand") }
            }
            if !hands.isEmpty { Divider() }
            Button("New Hand…") { newLabel = ""; naming = true }
        }
        .menuStyle(.button)
        .buttonStyle(.borderless)
        .fixedSize()
        .font(.caption)
    }

    private func reload() async {
        guard let handService else { return }
        hands = (try? await handService.hands()) ?? []
        attributions = (try? await handService.attributions(segmentId: segmentId)) ?? []
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

    /// A new hand, then this segment attributed to it: two audited actions, each undoable.
    private func createAndAttribute() async {
        let label = newLabel.trimmingCharacters(in: .whitespaces)
        guard !label.isEmpty, let actionsService = actionStore?.actionsService else { return }
        let known = Set(hands.map(\.id))
        guard (try? await AuditedAction.run(
            "hand.create", params: HandCreateRequest(label: label), actionName: "New Hand",
            actionsService: actionsService, undoManager: undoManager, afterChange: { await reload() }
        )) != nil else { return }
        // The hand the create just made: the one with this name that was not in the list before.
        guard let handId = hands.first(where: { !known.contains($0.id) && $0.label == label })?.id else { return }
        run("hand.attribute", HandAttributeRequest(handId: handId, segmentId: segmentId), "Attribute Hand")
    }
}

#if DEBUG
#Preview("Hands: one hand, attributed") {
    let rows = InspectorHands.rows(
        [.init(id: "a1", handId: "h1", certainty: 0.8, judgedBy: "owner", fromFile: nil)],
        hands: [.init(id: "h1", label: "hand B", scribe: nil, date: nil, style: "Estrangela")]
    )
    VStack(alignment: .leading) {
        ForEach(rows) { row in
            Text(row.ink)
            Text(row.record).font(.caption)
        }
    }
    .padding()
}
#endif
