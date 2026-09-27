import SwiftUI

/// A document's reading order as a list you can rearrange -- by drag, and by ⌥⌘↑ / ⌥⌘↓ and
/// ⌥⌘⇞ / ⌥⌘⇟ (to the start / end) on the selected line. ONE list view for every place that
/// lists the order (ruled 2026-09-27, Q5): the Inspector's Source section and the Reader both
/// mount this, and every move goes through `ReadingOrderStore`, so a drag and a key, in either
/// place, are the same engine call, undoable with ⌘Z.
struct ReadingOrderList: View {
    let documentId: String
    /// List this segment's children (a block's lines, a line's words) instead of the page's top level
    /// -- the Inspector's Order section at the inspected level.
    var parentSegmentId: String?

    @Environment(ReadingOrderService.self) private var service: ReadingOrderService?
    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(\.undoManager) private var undoManager

    @State private var store: ReadingOrderStore?
    /// The selected line, by segment id.
    @State private var selection: String?

    var body: some View {
        VStack(spacing: 0) {
            if let store, !store.shown.isEmpty {
                List(selection: $selection) {
                    ForEach(Array(store.shown.enumerated()), id: \.element.segmentId) { index, entry in
                        Text(label(for: entry.segmentId, at: index))
                            .lineLimit(2)
                            .tag(entry.segmentId)
                    }
                    .onMove { offsets, destination in
                        guard let from = offsets.first else { return }
                        let segmentId = store.shown[from].segmentId
                        let target = ReadingOrderMove.finalIndex(fromOffset: from, toOffset: destination)
                        Task { await record(store.move(segmentId, to: target), in: store) }
                    }
                }
                Divider()
                keyRow(store)
                if let refusal = store.lastRefusal {
                    Text(refusal).font(.caption).foregroundStyle(.secondary).padding(4)
                }
            } else {
                ContentUnavailableView(
                    "No Reading Order", systemImage: "list.number",
                    description: Text("This page has no named order yet.")
                )
            }
        }
        .task(id: "\(documentId)/\(parentSegmentId ?? "")") {
            if store == nil, let service { store = ReadingOrderStore(transport: service) }
            if store?.documentId != documentId { try? await store?.load(documentId: documentId) }
            await store?.show(childrenOf: parentSegmentId)
        }
    }

    /// The keys, as buttons so they are discoverable and so the shortcuts have a home.
    private func keyRow(_ store: ReadingOrderStore) -> some View {
        HStack(spacing: 8) {
            stepButton("arrow.up.to.line", "Move to Start", .toStart, key: .pageUp, store)
            stepButton("arrow.up", "Move Up", .up, key: .upArrow, store)
            stepButton("arrow.down", "Move Down", .down, key: .downArrow, store)
            stepButton("arrow.down.to.line", "Move to End", .toEnd, key: .pageDown, store)
            Spacer()
        }
        .buttonStyle(.borderless)
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .disabled(selection == nil)
    }

    private func stepButton(
        _ icon: String, _ title: String, _ step: ReadingOrderMove.Step,
        key: KeyEquivalent, _ store: ReadingOrderStore
    ) -> some View {
        Button {
            guard let segmentId = selection else { return }
            Task { await record(store.move(segmentId, step: step), in: store) }
        } label: {
            Label(title, systemImage: icon).labelStyle(.iconOnly)
        }
        .keyboardShortcut(key, modifiers: [.command, .option])
        .help("\(title) (⌥⌘\(Self.keyName(key)))")
        .accessibilityIdentifier("readingOrder.\(title)")
    }

    /// ⌘Z for the move just made.
    private func record(_ auditId: String?, in store: ReadingOrderStore) {
        store.registerUndo(auditId: auditId, undoManager: undoManager, actionsService: actionStore?.actionsService)
    }

    /// The line's own words when the page has them, else "line 3": a list of ids reads as nothing.
    private func label(for segmentId: String, at index: Int) -> String {
        guard let segmentService else { return "Segment \(index + 1)" }
        let segment = SegmentStore.shared(for: segmentService)
            .segments(documentId: documentId).first { $0.id == segmentId }
        if let text = segment?.text, !text.isEmpty { return text }
        return "\((segment?.kind ?? "segment").capitalized) \(index + 1)"
    }

    private static func keyName(_ key: KeyEquivalent) -> String {
        switch key {
        case .upArrow: "↑"
        case .downArrow: "↓"
        case .pageUp: "⇞"
        default: "⇟"
        }
    }
}
