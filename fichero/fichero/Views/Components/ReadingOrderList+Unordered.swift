import SwiftUI

/// The page-with-no-named-order state of `ReadingOrderList`: its head, the as-written rows and Create Named Order.
extension ReadingOrderList {
    /// The order's name, at the top of the list in every state (#6482).
    var layoutOrderHead: some View {
        // The order's name sits at the top, like the renditions: always there, even with no named order, so it is
        // plain what a layout order is and where to make one (#6482). The words live in the tooltip, not the menu.
        HStack(spacing: 6) {
            Image(systemName: "list.number").foregroundStyle(.secondary).accessibilityHidden(true)
            Menu {
                CreateNamedOrderMenuItem(target: lineVerbs)
                    .accessibilityIdentifier("readingOrder.createNamedOrder")
            } label: {
                Text("Layout Order").font(.headline)
            }
            .fixedSize()
            .help("The order this page's segments are read in. Now it is the order the layout found them; "
                + "make a named order to rearrange it.")
            Spacer(minLength: 4)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
    }

    /// A page with no named order: its segments as written, selectable like the order's rows, and the one
    /// verb that gives it an order. No move keys: there is no order to move in.
    func unordered(_ ids: [String]) -> some View {
        VStack(spacing: 0) {
            layoutOrderHead
            Divider()
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
            .focused($listFocused)
            if let createNote {
                Text(createNote).font(.caption).foregroundStyle(.secondary).padding(4)
            }
        }
    }

    /// The page's boxes become segments and its `as-written` order is made from them: one action, ⌘Z
    /// puts the page back as it was. The order and the segments are re-read after it and after each undo.
    func createNamedOrder() async {
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
    func nestedRows(top: [String]) -> (rows: [String: SegmentsPane.OutlineRow], tones: [String: RegionColours.Tone])? {
        guard nests, let segmentService else { return nil }
        let segments = SegmentStore.shared(for: segmentService).workingSegments(documentId: documentId)
        let rows = SegmentsPane.outline(segments, top: top)
        return (Dictionary(rows.map { ($0.segmentId, $0) }, uniquingKeysWith: { first, _ in first }),
                RegionColours.tones(of: segments))
    }

    /// A row of the level shown: flat, or
    /// with its swatch. Rows are keyed by segment id, so a segment event redraws its row, never the list.
    @ViewBuilder
    func entryRow(
        _ segmentId: String, at index: Int,
        nesting: (rows: [String: SegmentsPane.OutlineRow], tones: [String: RegionColours.Tone])?
    ) -> some View {
        if let nesting, let node = nesting.rows[segmentId] {
            SegmentOutlineRow(
                node: node, index: index, tones: nesting.tones,
                content: { id, position in AnyView(row(id, at: position)) },
                wrap: { id, view in AnyView(movable(id, view)) }, lit: dropTarget
            )
        } else if nesting != nil {
            // Folded under its region by `SegmentsPane.outline`: shown there, not again beside it (#6425).
            // Kept in the ForEach (not filtered out) so `onMove` offsets still index `store.shown`.
            EmptyView()
        } else {
            movable(segmentId, row(segmentId, at: index)).tag(segmentId)
                .listRowBackground(dropTarget == segmentId ? Color.accentColor.opacity(0.25) : Color.clear)
        }
    }
}
