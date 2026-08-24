import SwiftUI

/// One segment of a pane's breadcrumb title — a node with a face (Daniel,
/// 2026-08-23: "crumbs need icons that match sidebar and library").
struct PaneCrumb: Identifiable, Equatable {
    let id: String
    /// The DISPLAY title — already composed through DocumentTitle; never a
    /// raw storage name (the #4416 sweep).
    let title: String
    let icon: String
    /// `false` renders as plain text (e.g. a root the pane cannot navigate to).
    var isNavigable: Bool = true
    /// Icon colour, matching the sidebar/library rows (Daniel, 2026-08-23:
    /// "a folder is colorized like in sidebar / library view").
    var tint: Color = .secondary
}

extension PaneCrumb {
    /// The face a document wears everywhere — matches the sidebar/library rows
    /// so a crumb is recognisably the same node (Daniel, 2026-08-23).
    /// SOLID variants (Daniel, 2026-08-23: "solid icons not just outline")
    /// — the filled glyphs carry their tint better at crumb size.
    static func icon(for doc: Document) -> String {
        if doc.docType == .folder { return doc.isWorkspace ? "square.grid.2x2.fill" : "folder.fill" }
        if doc.docType == .page { return doc.fileType == .image ? "photo.fill" : "doc.richtext.fill" }
        if doc.fileType == .pdf { return "doc.richtext.fill" }
        if doc.fileType == .image { return "photo.fill" }
        return "doc.text.fill"
    }

    /// Sidebar colour rules (Daniel, 2026-08-23: "colorized like in
    /// sidebar / library view"): the sidebar tints EVERY library item's
    /// glyph with the accent, so crumbs do too.
    static func tint(for doc: Document) -> Color { .accentColor }

    init(_ doc: Document) {
        self.init(
            id: doc.id,
            title: DocumentTitle.displayName(for: doc),
            icon: Self.icon(for: doc),
            tint: Self.tint(for: doc)
        )
    }
}

#Preview("PaneHead crumb menus") {
    PaneHead<EmptyView, EmptyView, EmptyView>(
        crumbs: [
            PaneCrumb(id: "a", title: "Marshall Diaries v4", icon: "books.vertical.fill", tint: .accentColor),
            PaneCrumb(id: "b", title: "Inbox", icon: "folder.fill", tint: .accentColor),
            PaneCrumb(id: "c", title: "Jan 10 1933", icon: "photo.fill")
        ],
        onClose: {},
        onCrumb: { _ in },
        crumbChildren: { _ in
            [PaneCrumb(id: "x", title: "Child", icon: "doc.text.fill")]
        },
        selector: { EmptyView() },
        controls: { EmptyView() },
        tools: { EmptyView() }
    )
    .frame(width: 640)
    .padding()
}
