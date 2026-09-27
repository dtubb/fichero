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
    /// Show nothing at all for an empty level (ruled: a section with nothing to say is hidden).
    var hidesWhenEmpty = false

    @Environment(ReadingOrderService.self) private var service: ReadingOrderService?
    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(\.undoManager) private var undoManager

    @State private var store: ReadingOrderStore?

    init(
        documentId: String, parentSegmentId: String? = nil, hidesWhenEmpty: Bool = false,
        store: ReadingOrderStore? = nil
    ) {
        self.documentId = documentId
        self.parentSegmentId = parentSegmentId
        self.hidesWhenEmpty = hidesWhenEmpty
        // A store handed in (a preview's, over a fixture transport) is used as is; otherwise the
        // library's service makes one.
        _store = State(initialValue: store)
    }

    /// The selected line, by segment id.
    @State private var selection: String?
    /// Whether the list itself has keyboard focus: its ⌥⌘ keys exist only then, so with the Reader
    /// focused the same keys reach the Reader's caret line (`ReaderLineMove`), not this list.
    @FocusState private var listFocused: Bool

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
                .focused($listFocused)
                Divider()
                keyRow(store)
                if let refusal = store.lastRefusal {
                    Text(refusal).font(.caption).foregroundStyle(.secondary).padding(4)
                }
            } else if !hidesWhenEmpty {
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
        .keyboardShortcut(ReadingOrderListKeys.shortcut(key, listFocused: listFocused))
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

/// The list's ⌥⌘ keys, claimed only while the list has focus. `.keyboardShortcut` on a button is
/// WINDOW-wide: with the list showing a selection, ⌥⌘↑ pressed in the Reader moved the list's row
/// instead of the Reader's caret line. Nil detaches the shortcut; the buttons still work by click.
enum ReadingOrderListKeys {
    static func shortcut(_ key: KeyEquivalent, listFocused: Bool) -> KeyboardShortcut? {
        listFocused ? KeyboardShortcut(key, modifiers: [.command, .option]) : nil
    }
}

#if DEBUG
/// A page of three regions, the middle one holding three lines, as the engine would list them.
@MainActor
private final class PreviewOrderTransport: ReadingOrderTransport {
    func orders(documentId: String) async throws -> [ReadingOrderSummary] {
        [.init(id: "o1", name: "as-written", kind: "as-written")]
    }
    func entries(orderId: String, parentEntryId: String?) async throws -> [ReadingOrderMove.Entry] {
        parentEntryId == nil
            ? ["heading", "body", "marginal note"].map { .init(entryId: "e-\($0)", segmentId: $0, version: 1) }
            : ["line 1", "line 2", "line 3"].map {
                .init(entryId: "e-\($0)", segmentId: $0, version: 1, parentEntryId: parentEntryId)
            }
    }
    func place(_ place: ReadingOrderMove.Place) async throws -> String? { "preview-audit" }
}

#Preview("A page's order") {
    ReadingOrderList(documentId: "page-1", store: ReadingOrderStore(transport: PreviewOrderTransport()))
        .frame(width: 320, height: 260)
}

#Preview("A block's lines") {
    ReadingOrderList(
        documentId: "page-1", parentSegmentId: "body", store: ReadingOrderStore(transport: PreviewOrderTransport())
    )
    .frame(width: 320, height: 260)
}
#endif
