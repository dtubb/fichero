import SwiftUI

/// The Order list's head (#5160): which of the page's orders is shown -- As Written, named orders,
/// flows -- with New Order and New Flow (the audited `reading_order.create`, ⌘Z), and Previous / Next
/// through the order shown from the selected segment. In a flow, Next may open another page and
/// select the segment there.
struct ReadingOrderPicker: View {
    let documentId: String
    let store: ReadingOrderStore
    @Binding var selection: String?

    @Environment(ReadingOrderService.self) private var service: ReadingOrderService?
    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(WindowState.self) private var windowState: WindowState?
    @Environment(\.undoManager) private var undoManager
    @State private var naming: ReadingOrderChoice.NewKind?
    @State private var name = ""
    /// Why the last step or create did nothing, or what a continuation did; cleared by the next.
    @State var note: String?
    /// Flows from earlier pages (or the project) this page could continue (#5160 residue).
    @State var flowsOnto = ReadingOrderChoice.FlowsOnto()

    private var shown: ReadingOrderSummary? { store.orders.first { $0.id == store.orderId } }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 6) {
                Menu {
                    ForEach(store.orders) { order in
                        Button { Task { try? await store.choose(order.id) } } label: {
                            if order.id == store.orderId {
                                Label(ReadingOrderChoice.title(order), systemImage: "checkmark")
                            } else {
                                Text(ReadingOrderChoice.title(order))
                            }
                        }
                    }
                    Divider()
                    Button("New Order…") { name = ""; naming = .named }
                    Button("New Flow…") { name = ""; naming = .flow }
                    continueFlowMenu
                } label: {
                    Text(shown.map(ReadingOrderChoice.title) ?? "Order")
                }
                .fixedSize()
                .help("Which reading order the list shows")
                Spacer(minLength: 4)
                Button { Task { await step(forward: false) } } label: {
                    Label("Previous in Order", systemImage: "chevron.up")
                }
                Button { Task { await step(forward: true) } } label: {
                    Label("Next in Order", systemImage: "chevron.down")
                }
            }
            .labelStyle(.iconOnly)
            .buttonStyle(.borderless)
            if let note {
                Text(note).font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .task(id: documentId) { await loadFlowsOnto() }
        .alert(naming?.title ?? "", isPresented: Binding(get: { naming != nil }, set: { if !$0 { naming = nil } })) {
            TextField("Name", text: $name)
            Button("Create") {
                if let kind = naming { Task { await create(kind) } }
                naming = nil
            }
            Button("Cancel", role: .cancel) { naming = nil }
        } message: {
            Text(naming == .flow
                 ? "A flow starts with this page's segments and can continue onto other pages."
                 : "A new order starts as a copy of this page's order, to rearrange.")
        }
    }

    /// New Order / New Flow: the audited create, then show what it made.
    private func create(_ kind: ReadingOrderChoice.NewKind) async {
        guard let actionsService = actionStore?.actionsService,
              let params = ReadingOrderChoice.create(kind, name: name, documentId: documentId, from: shown) else {
            note = "Give the order a name."
            return
        }
        let before = store.orders
        let store = store
        let name = name
        do {
            try await AuditedAction.run(
                "reading_order.create", params: params, actionName: kind.title, actionsService: actionsService,
                undoManager: undoManager, afterChange: { try? await store.reloadOrders() }
            )
            if let made = ReadingOrderChoice.made(named: name, before: before, after: store.orders) {
                try await store.choose(made.id)
            }
            note = nil
        } catch {
            note = "The order could not be made: \(error.localizedDescription)"
        }
    }

    /// Previous / Next from the selected segment in the order shown. A segment on another page (a flow
    /// continuing) opens that page and is selected when it arrives.
    private func step(forward: Bool) async {
        guard let service, let orderId = store.orderId, let from = selection else {
            note = "Select a segment first."
            return
        }
        do {
            let neighbours = try await service.neighbours(orderId: orderId, segmentId: from)
            guard let target = ReadingOrderChoice.target(neighbours, forward: forward) else {
                note = forward ? "This is the end of the order." : "This is the start of the order."
                return
            }
            note = nil
            if store.entries.contains(where: { $0.segmentId == target })
                || (segmentService.map { SegmentStore.shared(for: $0).segments(documentId: documentId) } ?? [])
                    .contains(where: { $0.id == target }) {
                selection = target
            } else if let segmentService, let segment = try await segmentService.segment(id: target) {
                windowState?.pendingSegmentSelection = .init(documentId: segment.documentId, segmentId: target)
                NotificationCenter.default.post(
                    name: .sidebarRevealDocument, object: nil, userInfo: ["documentId": segment.documentId]
                )
            }
        } catch {
            note = "No neighbour: \(error.localizedDescription)"
        }
    }
}

/// Continue a Flow Here (#5160 residue, `source.segment.flow`): a flow ending on an earlier page of this
/// source -- or on a source sharing a project -- takes this page's segments at its end, in the page's
/// order, one `reading_order.place` each, grouped as ONE ⌘Z.
extension ReadingOrderPicker {
    @ViewBuilder
    var continueFlowMenu: some View {
        Divider()
        Menu("Continue a Flow Here") {
            if flowsOnto.flows.isEmpty {
                Text("No flow ends before this page").foregroundStyle(.secondary)
            }
            ForEach(flowsOnto.flows) { candidate in
                Button(candidate.title) { Task { await continueFlow(candidate) } }
            }
            if let withheld = SegmentsGathered.withheldNote(flowsOnto.withheld) {
                Text(withheld).foregroundStyle(.secondary)
            }
        }
    }

    func loadFlowsOnto() async {
        guard let service else { return }
        flowsOnto = (try? await service.flowsOnto(documentId: documentId)) ?? ReadingOrderChoice.FlowsOnto()
    }

    private func continueFlow(_ candidate: ReadingOrderChoice.ContinuableFlow) async {
        guard let service, let segmentService, let actionsService = actionStore?.actionsService else { return }
        let store = SegmentStore.shared(for: segmentService)
        guard let shown = SegmentDisplay.selected(for: documentId, store: store) else {
            note = "This page has no segments to continue the flow with."
            return
        }
        let ids = ReadingOrderChoice.continuation(of: store.segments(documentId: documentId), onPass: shown.passId)
        let undoManager = undoManager
        undoManager?.beginUndoGrouping()
        defer {
            undoManager?.endUndoGrouping()
            undoManager?.setActionName("Continue Flow")
        }
        var placed = 0
        do {
            for id in ids {
                let auditId = try await service.placeAtEnd(orderId: candidate.order.id, segmentId: id)
                ActionUndo.register(
                    auditId: auditId, actionName: "Continue Flow", undoManager: undoManager,
                    performUndo: { try await actionsService.undoAction(auditId: $0).auditId }
                )
                placed += 1
            }
            note = "Continued “\(candidate.order.name)” onto this page: \(placed) segment\(placed == 1 ? "" : "s")."
        } catch {
            note = "The flow was continued with \(placed) of \(ids.count) segments: \(error.localizedDescription)"
        }
        await loadFlowsOnto()
    }
}

#if DEBUG
#Preview("Order picker titles") {
    VStack(alignment: .leading) {
        ForEach([
            ReadingOrderSummary(id: "o1", name: "as-written", kind: "as-written"),
            ReadingOrderSummary(id: "o2", name: "Commentary order", kind: "imposed"),
            ReadingOrderSummary(id: "o3", name: "Into the next page", kind: "flow")
        ]) { Text(ReadingOrderChoice.title($0)) }
    }
    .padding()
}
#endif
