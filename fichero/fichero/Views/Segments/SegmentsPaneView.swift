import SwiftUI

/// The Segments pane (#4942): the page's segments as a list beside the Preview. The list, its
/// reorder verbs (drag, ⌥⌘↑ ⌥⌘↓ ⌥⌘⇞ ⌥⌘⇟, ⌘Z) and its selection (the focused Source view's, so the
/// boxes light and the Inspector follows) are the Order list's own -- `ReadingOrderList`, one
/// implementation. The pane adds a head with its kind switcher and a path, and rows that open to
/// their children.
struct SegmentsPaneView: View {
    /// The page the window has selected; nil shows how to get one.
    let document: Document?

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(WindowState.self) private var windowState: WindowState?
    @Environment(ReadingOrderService.self) private var readingOrderService: ReadingOrderService?
    /// ONE order store for the list, the strip and the grid, so all three show the same order.
    @State private var orders: ReadingOrderStore?
    /// The picture views' selected segment (the list keeps its own, as the Order list does).
    @State private var picked: String?
    @State private var lens: SegmentsPane.Lens = .list
    /// The segment whose children are listed; nil lists the page's top level.
    @State private var parentId: String?
    /// A gathered row asked to open: its segment is selected once its page is the one shown.
    @State private var pendingSelect: (documentId: String, segmentId: String)?

    private var segments: [Segment] {
        guard let document, let segmentService else { return [] }
        return SegmentStore.shared(for: segmentService).segments(documentId: document.id)
    }

    var body: some View {
        VStack(spacing: 0) {
            head
            Divider()
            if let gather = windowState?.segmentsGather {
                SegmentsGatheredList(gather: gather, open: open)
            } else if let document, lens != .list {
                SegmentsPictureGrid(
                    segmentIds: orders?.shown.map(\.segmentId) ?? [],
                    segments: Dictionary(segments.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first }),
                    isStrip: lens == .strip, selected: picked,
                    pick: { id in pick(id, on: document.id) },
                    open: { parentId = $0 },
                    opens: { SegmentsPane.hasChildren($0, in: segments) }
                )
            } else if let document, let orders {
                // Only once the ONE store exists: the list keeps the store it is first given, so handing
                // it nil would make it build a second one the strip and grid would not see.
                ReadingOrderList(
                    documentId: document.id, parentSegmentId: parentId, store: orders,
                    onOpen: { parentId = $0 }, opens: { SegmentsPane.hasChildren($0, in: segments) },
                    rowLabel: { id, index in SegmentsPane.rowLabel(segments.first { $0.id == id }, at: index) }
                )
            } else if document != nil {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ContentUnavailableView(
                    "No Page", systemImage: "list.bullet.rectangle",
                    description: Text("Select a page in the Library to list its segments.")
                )
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task(id: "\(document?.id ?? "")/\(parentId ?? "")") { await showLevel() }
        .task(id: document?.id) {
            parentId = nil
            guard let document, let segmentService else { return }
            let store = SegmentStore.shared(for: segmentService)
            await store.load(documentId: document.id)
            // A gathered row's page has arrived: select its segment in the focused Source view.
            if let pending = pendingSelect, pending.documentId == document.id,
               let selection = windowState?.focusedRegionSelection {
                InspectorPath.select(segmentIds: [pending.segmentId], into: selection, documentId: document.id, store: store)
                pendingSelect = nil
            }
        }
    }

    /// The level shown, in the page's order: loaded here so the strip and grid have it too.
    private func showLevel() async {
        guard let document else { return }
        if orders == nil, let readingOrderService { orders = ReadingOrderStore(transport: readingOrderService) }
        if orders?.documentId != document.id { try? await orders?.load(documentId: document.id) }
        await orders?.show(childrenOf: parentId)
    }

    /// A picture picked: the focused Source view's selection, as a list row's is (#5155).
    private func pick(_ segmentId: String, on documentId: String) {
        picked = segmentId
        guard let selection = windowState?.focusedRegionSelection, let segmentService else { return }
        InspectorPath.select(
            segmentIds: [segmentId], into: selection, documentId: documentId, store: SegmentStore.shared(for: segmentService)
        )
    }

    /// Open a gathered row: reveal its page in the Library (the same seam a click uses, so the Preview
    /// follows) and select the segment when the page arrives.
    private func open(_ row: SegmentsGathered.Row) {
        guard let documentId = row.documentId else { return }
        if let segmentId = row.segmentId { pendingSelect = (documentId, segmentId) }
        NotificationCenter.default.post(name: .sidebarRevealDocument, object: nil, userInfo: ["documentId": documentId])
    }

    private var head: some View {
        if let gather = windowState?.segmentsGather {
            return AnyView(PaneHead(
                crumbs: [
                    PaneCrumb(id: "page", title: document?.name ?? "Page", icon: "doc"),
                    PaneCrumb(id: "gather", title: gather.title, icon: "square.stack")
                ],
                onCrumb: { crumb in if crumb.id == "page" { windowState?.segmentsGather = nil } },
                selector: { kindSelector },
                controls: { EmptyView() },
                tools: { EmptyView() }
            ))
        }
        return AnyView(pageHead)
    }

    private var kindSelector: some View {
        PaneKindSelector(
            kindTitle: PaneSpec.Kind.segments.title, kindIcon: PaneSpec.Kind.segments.icon,
            currentKind: .segments, lenses: SegmentsPane.Lens.allCases,
            lensTitle: { (lens: SegmentsPane.Lens) in lens.title },
            lensIcon: { (lens: SegmentsPane.Lens) in lens.icon },
            lens: $lens
        )
    }

    private var pageHead: some View {
        let steps = SegmentsPane.path(pageTitle: document?.name ?? "Segments", to: parentId, in: segments)
        return PaneHead(
            crumbs: steps.map { PaneCrumb(id: $0.id, title: $0.title, icon: $0.segmentId == nil ? "doc" : "rectangle.dashed") },
            onCrumb: { crumb in
                parentId = steps.first { $0.id == crumb.id }?.segmentId
            },
            selector: { kindSelector },
            controls: { EmptyView() },
            tools: { EmptyView() }
        )
    }
}

#if DEBUG
/// With no page selected the pane says how to get one; the rows of a real page are the Order list's,
/// previewed in `ReadingOrderList.swift` over a fixture transport.
#Preview("Segments pane — no page selected") {
    SegmentsPaneView(document: nil)
        .frame(width: 320, height: 360)
}
#endif
