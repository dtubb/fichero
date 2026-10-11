import SwiftUI

/// The window title's proxy icon (Daniel, 2026-10-11): the title names the selected folder or file, and beside it
/// sits that item's own icon, as a document window's does. Dragging the icon drags the item, the same
/// `LibraryItemDrag` a row drags (into another project, the sidebar, Finder as a file copy).
///
/// ponytail: the system's ⌘-click path menu is built from a file URL, and a Fichero folder has none (the engine may
/// be remote), so the path stays in the title's subtitle (`breadcrumbSubtitle`). An ancestors menu on ⌘-click
/// needs an AppKit title-bar hook; add it if the subtitle is not enough.
struct WindowProxyIcon: ViewModifier {
    let document: Document?
    let libraryId: UUID?

    /// What the proxy icon carries for a document: its drag and its icon; nil shows no proxy icon.
    static func proxy(for document: Document?, libraryId: UUID?) -> (drag: LibraryItemDrag, symbol: String)? {
        guard let document else { return nil }
        return (LibraryItemDrag.forDocument(document, libraryId: libraryId), document.displaySymbol())
    }

    func body(content: Content) -> some View {
        if let document, let proxy = Self.proxy(for: document, libraryId: libraryId) {
            content.navigationDocument(
                proxy.drag,
                preview: SharePreview(DocumentTitle.displayName(for: document), image: Image(systemName: proxy.symbol))
            )
        } else {
            content
        }
    }
}

#Preview("A window titled with its folder's proxy icon") {
    NavigationStack {
        Text("Items")
            .navigationTitle("Sources")
            .modifier(WindowProxyIcon(document: Document(id: "src", docType: .folder, name: "Sources"), libraryId: nil))
    }
    .frame(width: 400, height: 200)
}
