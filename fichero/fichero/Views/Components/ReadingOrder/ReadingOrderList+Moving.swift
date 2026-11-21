import SwiftUI

// MARK: - Moving lines into a region (menu, drag and drop)

extension ReadingOrderList {
    var pageSegments: [Segment] { documentStore?.workingSegments(documentId: documentId) ?? [] }

    /// The lines a move on `named` means: the row, or the focused selection when it holds the row (one rule with Delete).
    func movedIds(named: Set<String>?) -> [String] {
        guard let store = documentStore else { return [] }
        // The rows the menu was opened on, else the list's own picks (Delete, the menu bar): they are the selection,
        // whatever the shared one holds (it can lag behind a pick, which moved only the first of four).
        let held = SegmentDeleter.selectedIds(windowState?.sharedRegionSelection, documentId: documentId, store: store)
        return SegmentDeleter.listRows(picked: named ?? picks, order: self.store?.shown.map(\.segmentId) ?? [], held: held)
    }

    /// ONE audited `segment.reparent`, one ⌘Z; why it did not happen is said under the list, never silent.
    func moveLines(_ ids: [String], into parent: String?) {
        guard let store = documentStore else { return }
        let steps = windowSteps, actionsService = actionStore?.actionsService, documentId = documentId
        Task {
            createNote = await SegmentMover.run(
                SegmentDeleter.segments(ids, documentId: documentId, store: store), into: parent,
                documentId: documentId, store: store, services: (actionsService, steps)
            )
        }
    }

    /// Tab: into the row above at the same level; Shift-Tab (or the back-tab character): out of the parent. Ignored when
    /// the list is flat, nothing is selected, or the move has nowhere to go, so Tab still moves the focus.
    func indent(_ press: KeyPress) -> KeyPress.Result {
        guard nests, let store, filter == nil, !picks.isEmpty else { return .ignored }
        let outline = SegmentsPane.outline(pageSegments, top: store.shown.map(\.segmentId))
        let ids = OrderDrop.inOutlineOrder(picks, outline: outline)
        let outdents = press.modifiers.contains(.shift) || press.characters == "\u{19}"
        if outdents {
            guard let out = OrderDrop.outdentTarget(ids, in: pageSegments) else { return .ignored }
            moveLines(ids, into: out.parent)
        } else {
            guard let target = OrderDrop.indentTarget(ids, outline: outline, in: pageSegments) else { return .ignored }
            moveLines(ids, into: target)
        }
        return .handled
    }

    func canTake(_ regionId: String) -> Bool {
        guard let region = segment(regionId), region.kind == "region" else { return false }
        return true
    }

    func dragPayload(_ segmentId: String) -> SegmentDrag {
        SegmentDrag.forRow(segmentId) { segment($0)?.text }
    }

    func dropped(_ ids: [String], onto regionId: String) -> Bool {
        guard let region = segment(regionId), region.kind == "region" else { return false }
        let accepted = OrderDrop.accepted(ids, into: region, in: pageSegments)
        guard !accepted.isEmpty else { return false }
        moveLines(accepted, into: regionId)
        return true
    }

    /// A drop on a row that takes nothing in: the dragged rows (one or several, in their list order) go just before this
    /// row, where the insertion line showed, as ONE `reading_order.move` and one ⌘Z (`segment-editor.list-drag-reorder`;
    /// the List has no `.onMove`: it would take the drag, #6577). Why it failed is said under the list.
    func reordered(_ ids: [String], to targetId: String) -> Bool {
        guard let store, let orderId = store.orderId, let documentStore, let actionsService = actionStore?.actionsService,
              case .success(let call) = ReadingOrderMove.move(
                  orderId: orderId, entries: store.shown, moving: ids, before: targetId, parentSegmentId: parentSegmentId
              ) else { return false }
        let steps = windowSteps, documentId = documentId
        Task {
            do {
                try await SegmentEditRunner(actionsService: actionsService, store: documentStore).run(
                    call, documentId: documentId, actionName: "Move in Reading Order", steps: steps
                )
                createNote = nil
            } catch {
                createNote = "The rows were not moved: \(error.localizedDescription)"
            }
        }
        return true
    }

    /// A row: its words, and -- in the Segments pane -- a control that opens it to its children.
    func row(_ segmentId: String, at index: Int) -> some View {
        rowContent(segmentId, at: index)
    }

    /// The whole row, swatch and all, is the drag handle and the drop target, lit like the sidebar's: a drag carries the
    /// selection when it holds this row, else the row; dropped on a region it moves them in. The drag is the ROW's
    /// (`itemProvider`), never a `.draggable` on its content: that took the mouse-down, so a click on a row's words did
    /// not select it, only a click beside them (#6476). With the List seeing the click it also takes the keyboard, so
    /// Delete and the arrows come here without a tap gesture of our own.
    func movable(_ segmentId: String, _ view: some View) -> some View {
        view
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(.rect)
            .itemProvider { dragPayload(segmentId).itemProvider() }
            .dropDestination(for: SegmentDrag.self, action: { drags, _ in
                let ids = drags.flatMap(\.ids)
                // On a region it moves them in; anywhere else it puts the dragged line in this row's place.
                return dropped(ids, onto: segmentId) || reordered(ids, to: segmentId)
            }, isTargeted: { targeting in
                if targeting, canTake(segmentId) { dropTarget = segmentId } else if dropTarget == segmentId { dropTarget = nil }
                // A row that takes nothing in shows where the drop lands: a line with a circle, just above it.
                if targeting, !canTake(segmentId) { insertBefore = segmentId } else if insertBefore == segmentId { insertBefore = nil }
            })
            .overlay(alignment: .top) { if insertBefore == segmentId { OrderInsertionLine() } }
    }

    func rowContent(_ segmentId: String, at index: Int) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            rowLine(segmentId, at: index)
            if let rowFooter, renaming != segmentId {
                rowFooter(segmentId)
            }
        }
    }

    func rowLine(_ segmentId: String, at index: Int) -> some View {
        HStack {
            if renaming == segmentId {
                TextField("Words", text: $draft)
                    .font(BundledFonts.shared.font(.body))
                    .focused($renameFocused)
                    .onSubmit { commitRename() }
                    #if os(macOS)
                    .onExitCommand { renaming = nil }
                    #endif
                    .onChange(of: renameFocused) { _, focused in if !focused { commitRename() } }
            } else {
                Text(rowLabel?(segmentId, index) ?? label(for: segmentId, at: index))
                    .font(BundledFonts.shared.font(.body))
                    .lineLimit(2)
                    // An unread line says what to do (#5505).
                    .help(SegmentsPane.rowHelp(segment(segmentId)) ?? "")
                if let rowAccessory {
                    Spacer(minLength: 4)
                    rowAccessory(segmentId)
                }
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
