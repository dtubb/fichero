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
    /// Each row holds its children, nested (a region its lines, a line its words), with the swatch of the colour
    /// its box is drawn in (hierarchy A, #5426): the Segments pane's and the page's Order tab (#5505). The
    /// Inspector's list of one segment's children stays one level.
    var nests = false

    @Environment(ReadingOrderService.self) private var service: ReadingOrderService?
    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(WindowSteps.self) private var windowSteps: WindowSteps?
    @Environment(WindowState.self) private var windowState: WindowState?

    @State private var store: ReadingOrderStore?

    init(
        documentId: String, parentSegmentId: String? = nil, hidesWhenEmpty: Bool = false,
        store: ReadingOrderStore? = nil, onOpen: ((String) -> Void)? = nil, opens: ((String) -> Bool)? = nil,
        rowLabel: ((String, Int) -> String)? = nil, onSelected: (([String]) -> Void)? = nil, nests: Bool = false
    ) {
        self.documentId = documentId
        self.parentSegmentId = parentSegmentId
        self.hidesWhenEmpty = hidesWhenEmpty
        self.onOpen = onOpen
        self.opens = opens
        self.rowLabel = rowLabel
        self.onSelected = onSelected
        self.nests = nests
        // A store handed in (a preview's, over a fixture transport) is used as is; otherwise the
        // library's service makes one.
        _store = State(initialValue: store)
    }

    /// The selected line, by segment id.
    @State private var picks: Set<String> = []
    /// The one selected row; nil with none or several (the verbs that act on one row ask this; Shift, ⌘ and ⌥ click
    /// pick several, Finder style, and the list's Delete and the shared selection take them all).
    private var selection: String? {
        get { picks.count == 1 ? picks.first : nil }
        nonmutating set { picks = newValue.map { [$0] } ?? [] }
    }
    /// Whether the list itself has keyboard focus: its ⌥⌘ keys exist only then, so with the Reader
    /// focused the same keys reach the Reader's caret line (`ReaderLineMove`), not this list.
    @FocusState private var listFocused: Bool
    /// The line being renamed in place (Return, Finder style; Step 1.25) and the words typed so far.
    @State private var renaming: String?
    @State private var draft = ""
    @FocusState private var renameFocused: Bool
    /// The region a drag is over, lit as a drop target.
    @State private var dropTarget: String?

    var body: some View {
        VStack(spacing: 0) {
            if let store, !store.orders.isEmpty, !(hidesWhenEmpty && store.shown.isEmpty) {
                // Which order, new orders and flows, Previous / Next (#5160).
                ReadingOrderPicker(documentId: documentId, store: store, selection: Binding(get: { selection }, set: { selection = $0 }))
                Divider()
            }
            if let store, !store.shown.isEmpty {
                let nested = nestedRows(top: store.shown.map(\.segmentId))
                List(selection: $picks) {
                    ForEach(Array(store.shown.enumerated()), id: \.element.segmentId) { index, entry in
                        entryRow(entry.segmentId, at: index, nesting: nested)
                    }
                    .onMove { offsets, destination in
                        guard let from = offsets.first else { return }
                        let segmentId = store.shown[from].segmentId
                        let target = ReadingOrderMove.finalIndex(fromOffset: from, toOffset: destination)
                        Task { await record(store.move(segmentId, to: target), in: store) }
                    }
                }
                .contextMenu(forSelectionType: String.self, menu: lineMenu, primaryAction: primaryAction)
                #if os(macOS)
                .onDeleteCommand { deleteLines(nil) }
                #endif
                .focused($listFocused)
                // Shift+Up/Down add the next row to the shared selection (#6457); plain arrows stay the list's own.
                .onKeyPress(.upArrow, phases: .down) { press in extend(-1, press, store: documentStore) }
                .onKeyPress(.downArrow, phases: .down) { press in extend(1, press, store: documentStore) }
                // Return renames the one selected line in place; a double-click reveals (Step 1.25).
                .onKeyPress(.return, phases: .down) { _ in beginRename(selection) }
                Divider()
                keyRow(store)
                if let refusal = store.lastRefusal {
                    Text(refusal).font(.caption).foregroundStyle(.secondary).padding(4)
                }
                if let createNote {
                    Text(createNote).font(.caption).foregroundStyle(.secondary).padding(4)
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
        .correctThisLine($correcting)
        // Page › Segments acts on this list's selection while it has focus (#5652): the same verbs its rows offer.
        .focusedValue(\.lineVerbs, lineVerbs)
        // One selection across the surfaces (#5155): a row picked here is the focused Source view's
        // selection too, so the boxes light and the Inspector follows.
        // And back: what another surface selects (the Reader, the Preview) is selected here too.
        .onChange(of: sharedIds) { _, now in if Set(now) != picks { picks = Set(now) } }
        .onChange(of: picks) { _, picked in
            guard !picked.isEmpty, Set(sharedIds) != picked, let focused = windowState?.sharedRegionSelection, let segmentService else { return }
            // In the list's own order, so the shared selection reads top to bottom.
            let inOrder = (store?.shown.map(\.segmentId) ?? []).filter(picked.contains)
            onSelected?(InspectorPath.select(
                segmentIds: inOrder.isEmpty ? Array(picked) : inOrder, into: focused, documentId: documentId,
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
            await flags?.load(documentId: documentId)
            // Next in a flow crossed onto this page: select the segment it went to.
            if let pending = windowState?.pendingSegmentSelection, pending.documentId == documentId {
                selection = pending.segmentId
                windowState?.pendingSegmentSelection = nil
            }
        }
    }

    /// The segments the one shared selection holds on this page (the Preview's, the Reader's, this list's).
    private var sharedIds: [String] {
        guard let segmentService, let selection = windowState?.sharedRegionSelection else { return [] }
        return InspectorPath.selectedSegmentIds(
            selection: selection, documentId: documentId, store: SegmentStore.shared(for: segmentService)
        )
    }

    /// The list's selection as Page › Segments' verbs see it (#5652): Correct This Line… on the selected line, and
    /// Create Named Order while the page has none.
    private var lineVerbs: LineVerbsTarget {
        var target = LineVerbsTarget(segment: selection.flatMap(segment))
        // A line is corrected IN PLACE here (Return, the menu): one verb, not a rename and a correct (Step 1.25).
        if let line = target.segment, CorrectLine.offers(line) { target.correct = { _ = beginRename(line.id) } }
        if let selection {
            target.delete = { deleteLines(nil) }
            target.reveal = { reveal([selection]) }
            if let store, !store.shown.isEmpty {
                target.move = { step in Task { await record(store.move(selection, step: step), in: store) } }
            }
        }
        if let store, store.documentId == documentId, store.orders.isEmpty {
            target.createNamedOrder = { Task { await createNamedOrder() } }
        }
        return target
    }

    /// A row's menu: Correct This Line on one line (#5499).
    @ViewBuilder
    private func lineMenu(_ ids: Set<String>) -> some View {
        CorrectThisLineButton(segment: ids.count == 1 ? ids.first.flatMap(segment) : nil) { _ = beginRename($0.id) }
        if ids.count == 1 { Button(LineVerbs.revealTitle) { reveal(ids) } }
        moveMenu(ids)
        Divider()
        Button(role: .destructive) { deleteLines(ids) } label: { Label("Delete", systemImage: "trash") }
            .disabled(ids.isEmpty)
    }

    /// Delete (the key, the row menu) on the row named or highlighted: that row, or the focused Source view's selection
    /// (a multi-selection made in the Preview) when it contains the row (`SegmentDeleter.ids`). ONE audited `segment.delete` batch, one ⌘Z
    /// (`source.editor.delete-selected-lines`); why it did not happen is said under the list, never silent.
    private func deleteLines(_ named: Set<String>?) {
        guard let segmentService else { return }
        let store = SegmentStore.shared(for: segmentService)
        let focused = windowState?.sharedRegionSelection
        let held = SegmentDeleter.selectedIds(focused, documentId: documentId, store: store)
        let ids = SegmentDeleter.ids(row: named?.first ?? selection, held: held)
        let steps = windowSteps, actionsService = actionStore?.actionsService, documentId = documentId
        Task {
            createNote = await SegmentDeleter.run(
                SegmentDeleter.segments(ids, documentId: documentId, store: store), documentId: documentId,
                store: store, actionsService: actionsService, steps: steps, clearing: focused
            )
        }
    }

    /// The line Correct This Line is asking about; nil when it is not asking.
    @State private var correcting: Segment?

    private var documentStore: SegmentStore? { segmentService.map { SegmentStore.shared(for: $0) } }

    /// Shift+Up/Down (#6457): only Shift extends; a plain arrow stays the List's own (`InspectorPath.extendPlaces`).
    private func extend(_ places: Int, _ press: KeyPress, store: SegmentStore?) -> KeyPress.Result {
        guard let places = InspectorPath.extendPlaces(places, shift: press.modifiers.contains(.shift)),
              let store, let focused = windowState?.sharedRegionSelection,
              InspectorPath.stepSelection(by: places, extend: true, selection: focused, documentId: documentId, store: store)
        else { return .ignored }
        return .handled
    }

    /// Return on the one selected line: edit its words in place (`OrderRename.begins`).
    private func beginRename(_ id: String? = nil) -> KeyPress.Result {
        guard renaming == nil, let id = id ?? selection,
              let words = OrderRename.begins(on: [segment(id)].compactMap { $0 }) else { return .ignored }
        draft = words
        renaming = id
        selection = id
        renameFocused = true
        return .handled
    }

    /// Return (or a click away) in the field: record the words as the person's reading, through the one correction path.
    private func commitRename() {
        guard let id = renaming else { return }
        renaming = nil
        guard let line = segment(id), let words = OrderRename.commit(draft, on: line), let segmentService else { return }
        Task {
            do {
                try await CorrectLine.send(line, words: words, segmentService: segmentService)
            } catch {
                createNote = "The line was not corrected: \(error.localizedDescription)"
            }
        }
    }

    /// The list's one primary action runs on a double-click AND on Return: Return (a key event) corrects the one
    /// selected line in place, as Finder renames; a double-click, or Return on a segment with no edit yet, reveals.
    private func primaryAction(_ ids: Set<String>) {
        #if os(macOS)
        if NSApp.currentEvent?.type == .keyDown, ids.count == 1, let id = ids.first, beginRename(id) == .handled { return }
        #endif
        reveal(ids)
    }

    /// A double-click on a row (Return renames): reveal it in the linked Preview, selected, scrolled and
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

    /// Which lines the teacher-line check flagged (#5446): the one store every line list reads.
    private var flags: FlaggedLineStore? {
        segmentService.map { FlaggedLineStore.shared(for: $0) }
    }

    /// The page's working pass as the engine names it; nil until the page is read.
    private var workingPassId: String? {
        segmentService.flatMap { SegmentStore.shared(for: $0).workingPass(documentId: documentId)?.id }
    }

    /// A page with no named order: its segments as written, selectable like the order's rows, and the one
    /// verb that gives it an order. No move keys: there is no order to move in.
    private func unordered(_ ids: [String]) -> some View {
        VStack(spacing: 0) {
            let nested = nestedRows(top: ids)
            List(selection: $picks) {
                ForEach(Array(ids.enumerated()), id: \.element) { index, segmentId in
                    entryRow(segmentId, at: index, nesting: nested)
                }
            }
            .contextMenu(forSelectionType: String.self, menu: lineMenu, primaryAction: primaryAction)
            #if os(macOS)
            .onDeleteCommand { deleteLines(nil) }
            #endif
            Divider()
            HStack(spacing: 8) {
                Text("Layout order. This page has no named order yet.")
                    .font(.caption).foregroundStyle(.secondary)
                    .help("The segments in the order the layout found them; no file gave an order")
                Spacer()
                CreateNamedOrderMenuItem(target: lineVerbs)
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
                actionName: LineVerbs.createNamedOrderTitle, actionsService: actionsService, steps: windowSteps,
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

    /// What the nested rows hold and the tones their swatches take, made ONCE per list from the working pass's
    /// segments (per row it would be quadratic on a page of thousands of lines). Nil when the list does not nest.
    private func nestedRows(top: [String]) -> (rows: [String: SegmentsPane.OutlineRow], tones: [String: RegionColours.Tone])? {
        guard nests, let segmentService else { return nil }
        let segments = SegmentStore.shared(for: segmentService).workingSegments(documentId: documentId)
        let rows = SegmentsPane.outline(segments, top: top)
        return (Dictionary(rows.map { ($0.segmentId, $0) }, uniquingKeysWith: { first, _ in first }),
                RegionColours.tones(of: segments))
    }

    /// A row of the level shown: flat, or -- nesting -- holding its children (`SegmentsPane.outline`), each
    /// with its swatch. Rows are keyed by segment id, so a segment event redraws its row, never the list.
    @ViewBuilder
    private func entryRow(
        _ segmentId: String, at index: Int,
        nesting: (rows: [String: SegmentsPane.OutlineRow], tones: [String: RegionColours.Tone])?
    ) -> some View {
        if let nesting, let node = nesting.rows[segmentId] {
            SegmentOutlineRow(
                node: node, index: index, tones: nesting.tones,
                content: { id, position in AnyView(row(id, at: position)) },
                wrap: { id, view in AnyView(movable(id, view)) }
            )
        } else if nesting != nil {
            // Folded under its region by `SegmentsPane.outline`: shown there, not again beside it (#6425).
            // Kept in the ForEach (not filtered out) so `onMove` offsets still index `store.shown`.
            EmptyView()
        } else {
            movable(segmentId, row(segmentId, at: index)).tag(segmentId)
        }
    }
}

// MARK: - Key rows and the step control

extension ReadingOrderList {
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
        store.registerUndo(auditId: auditId, steps: windowSteps, actionsService: actionStore?.actionsService)
    }

    /// "Line 6 · its words", as the Segments pane labels it (#5505): one label on every surface, the number kept
    /// once a line has a reading.
    private func label(for segmentId: String, at index: Int) -> String {
        guard segmentService != nil else { return "Segment \(index + 1)" }
        return SegmentsPane.rowLabel(segment(segmentId), at: index)
    }

    private func segment(_ segmentId: String) -> Segment? {
        segmentService.flatMap { SegmentStore.shared(for: $0).segments(documentId: documentId).first { $0.id == segmentId } }
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

/// One row of the nested Segments list (hierarchy A, #5426, `source.editor.hierarchy.segments-list-nests`): the
/// swatch of the colour its box is drawn in (`SelectionStyle.regionSwatch`, the one colour path), its words, and
/// its children disclosed under it, indented -- a region open on its lines, a line closed on its words.
struct SegmentOutlineRow: View {
    let node: SegmentsPane.OutlineRow
    let index: Int
    let tones: [String: RegionColours.Tone]
    /// The list's own row for an id (its words, its flag).
    let content: (String, Int) -> AnyView
    /// What surrounds the whole row (the swatch included): the list's drag and drop, lit across the row.
    let wrap: (String, AnyView) -> AnyView

    @State private var expanded: Bool

    init(
        node: SegmentsPane.OutlineRow, index: Int, tones: [String: RegionColours.Tone],
        content: @escaping (String, Int) -> AnyView, wrap: @escaping (String, AnyView) -> AnyView = { _, view in view }
    ) {
        self.wrap = wrap
        self.node = node
        self.index = index
        self.tones = tones
        self.content = content
        // A region shows its lines; a line keeps its words until asked.
        _expanded = State(initialValue: SegmentHierarchy.Level(kind: node.kind) == .region)
    }

    var body: some View {
        if node.children.isEmpty {
            labelled
        } else {
            DisclosureGroup(isExpanded: $expanded) {
                ForEach(Array(node.children.enumerated()), id: \.element.id) { position, child in
                    SegmentOutlineRow(node: child, index: position, tones: tones, content: content, wrap: wrap)
                }
            } label: {
                labelled
            }
        }
    }

    private var labelled: some View {
        wrap(node.segmentId, AnyView(
            HStack(spacing: 6) {
                Circle()
                    .fill(SelectionStyle.regionSwatch(tones[node.segmentId]))
                    .frame(width: 8, height: 8)
                    .accessibilityHidden(true)
                content(node.segmentId, index)
            }
        ))
        .tag(node.segmentId)
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

#Preview("Nested: a region, its lines, a line's words") {
    let words = ["In", "the", "beginning"].map { SegmentsPane.OutlineRow(segmentId: $0, kind: "word", children: []) }
    let lines = (1...3).map {
        SegmentsPane.OutlineRow(segmentId: "line \($0)", kind: "line", children: $0 == 1 ? words : [])
    }
    let regions = [
        SegmentsPane.OutlineRow(segmentId: "body", kind: "region", children: lines),
        SegmentsPane.OutlineRow(segmentId: "marginal note", kind: "region", children: [])
    ]
    // The region at full strength, its lines shaded along the order, the first line's words in its shade.
    let tones: [String: RegionColours.Tone] = [
        "body": .init(hue: 0, strength: 1), "marginal note": .init(hue: 1, strength: 1),
        "line 1": .init(hue: 0, strength: 1), "line 2": .init(hue: 0, strength: 0.725),
        "line 3": .init(hue: 0, strength: 0.45),
        "In": .init(hue: 0, strength: 1), "the": .init(hue: 0, strength: 1), "beginning": .init(hue: 0, strength: 1)
    ]
    return List {
        ForEach(Array(regions.enumerated()), id: \.element.id) { index, region in
            SegmentOutlineRow(node: region, index: index, tones: tones, content: { id, _ in AnyView(Text(id)) })
        }
    }
    .frame(width: 320, height: 300)
}

#Preview("A block's lines") {
    ReadingOrderList(
        documentId: "page-1", parentSegmentId: "body", store: ReadingOrderStore(transport: PreviewOrderTransport())
    )
    .frame(width: 320, height: 260)
}
#endif

// MARK: - Moving lines into a region (menu, drag and drop)

extension ReadingOrderList {
    /// Move Into Region ▸ (the page's other regions) and Lift Out of Region: present only when they can apply, never greyed.
    @ViewBuilder
    private func moveMenu(_ ids: Set<String>) -> some View {
        let held = movedIds(named: ids)
        let regions = SegmentMover.targets(for: held, in: pageSegments)
        if !regions.isEmpty {
            Menu("Move Into Region") {
                ForEach(Array(regions.enumerated()), id: \.element.id) { position, region in
                    Button("Region \(position + 1)") { moveLines(held, into: region.id) }
                }
            }
        }
        if SegmentMover.canLift(held, in: pageSegments) {
            Button("Lift Out of Region") { moveLines(held, into: nil) }
        }
    }

    private var pageSegments: [Segment] { documentStore?.workingSegments(documentId: documentId) ?? [] }

    /// The lines a move on `named` means: the row, or the focused selection when it holds the row (one rule with Delete).
    private func movedIds(named: Set<String>?) -> [String] {
        guard let store = documentStore else { return [] }
        let held = SegmentDeleter.selectedIds(windowState?.sharedRegionSelection, documentId: documentId, store: store)
        return SegmentDeleter.ids(row: named?.first ?? selection, held: held)
    }

    /// ONE audited `segment.reparent`, one ⌘Z; why it did not happen is said under the list, never silent.
    private func moveLines(_ ids: [String], into parent: String?) {
        guard let store = documentStore else { return }
        let steps = windowSteps, actionsService = actionStore?.actionsService, documentId = documentId
        Task {
            createNote = await SegmentMover.run(
                SegmentDeleter.segments(ids, documentId: documentId, store: store), into: parent,
                documentId: documentId, store: store, actionsService: actionsService, steps: steps
            )
        }
    }

    private func canTake(_ regionId: String) -> Bool {
        guard let region = segment(regionId), region.kind == "region" else { return false }
        return true
    }

    private func dragPayload(_ segmentId: String) -> SegmentDrag {
        let held = (store?.shown.map(\.segmentId) ?? []).filter(picks.contains)
        let ids = picks.contains(segmentId) && !held.isEmpty ? held : [segmentId]
        let text = ids.compactMap { segment($0)?.text }.joined(separator: "\n")
        return SegmentDrag(ids: ids, text: text)
    }

    private func dropped(_ ids: [String], onto regionId: String) -> Bool {
        guard let region = segment(regionId), region.kind == "region" else { return false }
        let accepted = OrderDrop.accepted(ids, into: region, in: pageSegments)
        guard !accepted.isEmpty else { return false }
        moveLines(accepted, into: regionId)
        return true
    }

    /// A row: its words, and -- in the Segments pane -- a control that opens it to its children.
    private func row(_ segmentId: String, at index: Int) -> some View {
        rowContent(segmentId, at: index)
    }

    /// The whole row, swatch and all, is the drag handle and the drop target, lit like the sidebar's: a drag carries the
    /// selection when it holds this row, else the row; dropped on a region it moves them in.
    func movable(_ segmentId: String, _ view: some View) -> some View {
        view
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(.rect)
            .background(dropTarget == segmentId ? Color.accentColor.opacity(0.25) : .clear, in: .rect(cornerRadius: 6))
            .draggable(dragPayload(segmentId))
            .dropDestination(for: SegmentDrag.self, action: { drags, _ in
                dropped(drags.flatMap(\.ids), onto: segmentId)
            }, isTargeted: { targeting in
                if targeting, canTake(segmentId) { dropTarget = segmentId } else if dropTarget == segmentId { dropTarget = nil }
            })
    }

    private func rowContent(_ segmentId: String, at index: Int) -> some View {
        HStack {
            if renaming == segmentId {
                TextField("Words", text: $draft)
                    .font(BundledFonts.shared.font(.body))
                    .focused($renameFocused)
                    .onSubmit { commitRename() }
                    .onExitCommand { renaming = nil }
                    .onChange(of: renameFocused) { _, focused in if !focused { commitRename() } }
            } else {
                Text(rowLabel?(segmentId, index) ?? label(for: segmentId, at: index))
                    .font(BundledFonts.shared.font(.body))
                    .lineLimit(2)
                    // An unread line says what to do (#5505).
                    .help(SegmentsPane.rowHelp(segment(segmentId)) ?? "")
            }
            // A line the teacher-line check flagged (#5446): marked, its scores on hover.
            if let line = flags?.flag(segmentId: segmentId, documentId: documentId) {
                Spacer(minLength: 4)
                FlaggedLineMark(line: line)
            }
            if !nests, let onOpen, opens?(segmentId) ?? false {
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
}
