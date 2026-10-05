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
    /// The Segments pane's: open a row to its children (nil: rows do not open, as in the Inspector).
    var onOpen: ((String) -> Void)?
    /// Which rows can be opened (they have children).
    var opens: ((String) -> Bool)?
    /// The Segments pane's row words; nil keeps the Order list's own.
    var rowLabel: ((String, Int) -> String)?
    /// The ids a row click or double-click wrote into the focused selection: the Inspector's hold (#5424).
    var onSelected: (([String]) -> Void)?

    @Environment(ReadingOrderService.self) private var service: ReadingOrderService?
    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(\.undoManager) private var undoManager
    @Environment(WindowState.self) private var windowState: WindowState?

    @State private var store: ReadingOrderStore?

    init(
        documentId: String, parentSegmentId: String? = nil, hidesWhenEmpty: Bool = false,
        store: ReadingOrderStore? = nil, onOpen: ((String) -> Void)? = nil, opens: ((String) -> Bool)? = nil,
        rowLabel: ((String, Int) -> String)? = nil, onSelected: (([String]) -> Void)? = nil
    ) {
        self.documentId = documentId
        self.parentSegmentId = parentSegmentId
        self.hidesWhenEmpty = hidesWhenEmpty
        self.onOpen = onOpen
        self.opens = opens
        self.rowLabel = rowLabel
        self.onSelected = onSelected
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
            if let store, !store.orders.isEmpty, !(hidesWhenEmpty && store.shown.isEmpty) {
                // Which order, new orders and flows, Previous / Next (#5160).
                ReadingOrderPicker(documentId: documentId, store: store, selection: $selection)
                Divider()
            }
            if let store, !store.shown.isEmpty {
                List(selection: $selection) {
                    ForEach(Array(store.shown.enumerated()), id: \.element.segmentId) { index, entry in
                        row(entry.segmentId, at: index)
                            .tag(entry.segmentId)
                    }
                    .onMove { offsets, destination in
                        guard let from = offsets.first else { return }
                        let segmentId = store.shown[from].segmentId
                        let target = ReadingOrderMove.finalIndex(fromOffset: from, toOffset: destination)
                        Task { await record(store.move(segmentId, to: target), in: store) }
                    }
                }
                .contextMenu(forSelectionType: String.self, menu: { _ in EmptyView() }, primaryAction: reveal)
                .focused($listFocused)
                Divider()
                keyRow(store)
                if let refusal = store.lastRefusal {
                    Text(refusal).font(.caption).foregroundStyle(.secondary).padding(4)
                }
            } else if let store, store.documentId == documentId, store.orders.isEmpty, !hidesWhenEmpty,
                      !asWritten.isEmpty {
                // No named order is no reason to show nothing: the page's segments, as written (#5204).
                unordered(asWritten)
            } else if !hidesWhenEmpty {
                ContentUnavailableView(
                    "No Reading Order", systemImage: "list.number",
                    description: Text("This page has no named order yet.")
                )
            }
        }
        // One selection across the surfaces (#5155): a row picked here is the focused Source view's
        // selection too, so the boxes light and the Inspector follows.
        .onChange(of: selection) { _, picked in
            guard let picked, let focused = windowState?.focusedRegionSelection, let segmentService else { return }
            onSelected?(InspectorPath.select(
                segmentIds: [picked], into: focused, documentId: documentId,
                store: SegmentStore.shared(for: segmentService)
            ))
        }
        // The working pass is in the key (#5465): when a run's result becomes the page's working pass (a
        // pass event re-reads this page in `SegmentStore`), the list re-reads this page's orders.
        .task(id: "\(documentId)/\(parentSegmentId ?? "")/\(workingPassId ?? "")") {
            if store == nil, let service { store = ReadingOrderStore(transport: service) }
            // The as-written fallback reads the page's segments; loading is a no-op once loaded.
            if let segmentService { await SegmentStore.shared(for: segmentService).load(documentId: documentId) }
            try? await store?.loadFollowing(documentId: documentId, workingPassId: workingPassId)
            await store?.show(childrenOf: parentSegmentId)
            // Next in a flow crossed onto this page: select the segment it went to.
            if let pending = windowState?.pendingSegmentSelection, pending.documentId == documentId {
                selection = pending.segmentId
                windowState?.pendingSegmentSelection = nil
            }
        }
    }

    /// A double-click (or Return) on a row: reveal it in the linked Preview, selected, scrolled and
    /// zoomed to (#5424) -- the one reveal the Reader's line click makes too.
    private func reveal(_ ids: Set<String>) {
        guard let segmentId = ids.first, let windowState, let segmentService else { return }
        onSelected?(windowState.revealSegments(
            [segmentId], documentId: documentId, store: SegmentStore.shared(for: segmentService)
        ))
    }

    /// Why Create Named Order did not happen; nil after it did.
    @State private var createNote: String?

    /// The level shown, as the page holds it, for a page with no named order: the WORKING pass's
    /// segments only (`SegmentStore.workingSegments`, #5467), never the top level of every pass.
    private var asWritten: [String] {
        guard let segmentService else { return [] }
        let segments = SegmentStore.shared(for: segmentService).workingSegments(documentId: documentId)
        return SegmentsPane.asWritten(segments, under: parentSegmentId)
    }

    /// The page's working pass as the engine names it; nil until the page is read.
    private var workingPassId: String? {
        segmentService.flatMap { SegmentStore.shared(for: $0).workingPass(documentId: documentId)?.id }
    }

    /// A page with no named order: its segments as written, selectable like the order's rows, and the one
    /// verb that gives it an order. No move keys: there is no order to move in.
    private func unordered(_ ids: [String]) -> some View {
        VStack(spacing: 0) {
            List(selection: $selection) {
                ForEach(Array(ids.enumerated()), id: \.element) { index, segmentId in
                    row(segmentId, at: index).tag(segmentId)
                }
            }
            .contextMenu(forSelectionType: String.self, menu: { _ in EmptyView() }, primaryAction: reveal)
            Divider()
            HStack(spacing: 8) {
                Text("Layout order. This page has no named order yet.")
                    .font(.caption).foregroundStyle(.secondary)
                    .help("The segments in the order the layout found them; no file gave an order")
                Spacer()
                Button("Create Named Order") { Task { await createNamedOrder() } }
                    .accessibilityIdentifier("readingOrder.createNamedOrder")
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            if let createNote {
                Text(createNote).font(.caption).foregroundStyle(.secondary).padding(4)
            }
        }
    }

    /// The page's boxes become segments and its `as-written` order is made from them: one action, ⌘Z
    /// puts the page back as it was. The order and the segments are re-read after it and after each undo.
    private func createNamedOrder() async {
        guard let actionsService = actionStore?.actionsService, let store else {
            createNote = "This window cannot make an order."
            return
        }
        let documentId = documentId
        let segmentService = segmentService
        do {
            try await AuditedAction.run(
                "segment.convert_and_edit", params: ConvertPageRequest(documentId: documentId),
                actionName: "Create Named Order", actionsService: actionsService, undoManager: undoManager,
                afterChange: {
                    if let segmentService {
                        await SegmentStore.shared(for: segmentService).load(documentId: documentId, force: true)
                    }
                    try? await store.load(documentId: documentId)
                }
            )
            createNote = nil
        } catch {
            createNote = "The order could not be made: \(error.localizedDescription)"
        }
    }

    /// A row: its words, and -- in the Segments pane -- a control that opens it to its children.
    private func row(_ segmentId: String, at index: Int) -> some View {
        HStack {
            Text(rowLabel?(segmentId, index) ?? label(for: segmentId, at: index))
                .font(BundledFonts.shared.font(.body))
                .lineLimit(2)
            if let onOpen, opens?(segmentId) ?? false {
                Spacer(minLength: 4)
                Button { onOpen(segmentId) } label: {
                    Image(systemName: "chevron.right")
                }
                .buttonStyle(.borderless)
                .accessibilityLabel("Open")
                .help("List what this segment holds")
            }
        }
    }

    /// The keys, as buttons so they are discoverable and so the shortcuts have a home.
    private func keyRow(_ store: ReadingOrderStore) -> some View {
        HStack(spacing: 8) {
            stepButton("arrow.up.to.line", "Move to Start", .toStart, key: .pageUp, store)
            stepButton("arrow.up", "Move Up", .upward, key: .upArrow, store)
            stepButton("arrow.down", "Move Down", .downward, key: .downArrow, store)
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
        .accessibilityLabel(title)
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
        return SegmentsPane.rowLabel(segment, at: index)
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
