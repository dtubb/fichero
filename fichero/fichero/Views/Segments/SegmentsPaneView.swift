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
    @State private var lens: SegmentsPane.Lens = .list
    /// The segment whose children are listed; nil lists the page's top level.
    @State private var parentId: String?

    private var segments: [Segment] {
        guard let document, let segmentService else { return [] }
        return SegmentStore.shared(for: segmentService).segments(documentId: document.id)
    }

    var body: some View {
        VStack(spacing: 0) {
            head
            Divider()
            if let document {
                ReadingOrderList(
                    documentId: document.id, parentSegmentId: parentId,
                    onOpen: { parentId = $0 }, opens: { SegmentsPane.hasChildren($0, in: segments) },
                    rowLabel: { id, index in SegmentsPane.rowLabel(segments.first { $0.id == id }, at: index) }
                )
            } else {
                ContentUnavailableView(
                    "No Page", systemImage: "list.bullet.rectangle",
                    description: Text("Select a page in the Library to list its segments.")
                )
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task(id: document?.id) {
            parentId = nil
            guard let document, let segmentService else { return }
            await SegmentStore.shared(for: segmentService).load(documentId: document.id)
        }
    }

    private var head: some View {
        let steps = SegmentsPane.path(pageTitle: document?.name ?? "Segments", to: parentId, in: segments)
        return PaneHead(
            crumbs: steps.map { PaneCrumb(id: $0.id, title: $0.title, icon: $0.segmentId == nil ? "doc" : "rectangle.dashed") },
            onCrumb: { crumb in
                parentId = steps.first { $0.id == crumb.id }?.segmentId
            },
            selector: {
                PaneKindSelector(
                    kindTitle: PaneSpec.Kind.segments.title, kindIcon: PaneSpec.Kind.segments.icon,
                    currentKind: .segments, lenses: SegmentsPane.Lens.allCases,
                    lensTitle: { (lens: SegmentsPane.Lens) in lens.title },
                    lensIcon: { (lens: SegmentsPane.Lens) in lens.icon },
                    lens: $lens
                )
            },
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
