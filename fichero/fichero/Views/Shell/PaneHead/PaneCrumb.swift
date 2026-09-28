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

    static let libraryPrefix = "library:"

    /// A library's root crumb (#5218): navigable -- it shows the library's top level, as its sidebar row does.
    @MainActor
    static func library(_ library: LibraryManager.LibraryReference) -> PaneCrumb {
        PaneCrumb(
            id: libraryPrefix + library.id.uuidString, title: library.displayName,
            icon: "books.vertical.fill", tint: .accentColor
        )
    }

    /// The library a library crumb names; nil for a document's crumb.
    var libraryId: UUID? {
        id.hasPrefix(Self.libraryPrefix) ? UUID(uuidString: String(id.dropFirst(Self.libraryPrefix.count))) : nil
    }

    /// Every OTHER open library, listed above the path in the crumb menu to switch to without the sidebar.
    @MainActor
    static func otherLibraries(than libraryId: UUID) -> [PaneCrumb] {
        LibraryManager.shared.openLibraries.filter { $0.id != libraryId }.map(library)
    }

    /// The ONE way a crumb navigates, like Finder's path control: through the sidebar's reveal seam, which
    /// selects the row as a click does (so the panes, the Inspector and ⌘[ / ⌘] follow). A library crumb
    /// selects the library -- its top level, switching the window when it is another library.
    @MainActor
    static func reveal(_ crumb: PaneCrumb) {
        let info: [String: String] = crumb.libraryId.map { ["libraryId": $0.uuidString] } ?? ["documentId": crumb.id]
        NotificationCenter.default.post(name: .sidebarRevealDocument, object: nil, userInfo: info)
    }

    /// What a crumb's menu offers to step into: a library's top level, or a node's children.
    @MainActor
    static func children(of crumb: PaneCrumb, in store: DocumentStore) -> [PaneCrumb] {
        if crumb.libraryId != nil { return store.collections.filter { $0.parentId == nil }.map(PaneCrumb.init) }
        return (store.outline(for: crumb.id)?.children ?? store.childrenCache[crumb.id] ?? []).map(PaneCrumb.init)
    }

    /// The leaf crumb for a multi-selection (Daniel, 2026-08-29): with N>1
    /// items selected a pane head must SAY so — "3 items" — never name one
    /// document as if it were alone. Not navigable: there is no single node
    /// behind it to reveal.
    static func multiSelection(count: Int) -> PaneCrumb {
        PaneCrumb(
            id: "multi-selection",
            title: "\(count) items",
            icon: "square.on.square",
            isNavigable: false
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
