import SwiftUI

/// A selected plain folder previews as its items do when they are selected together (#5300, ruled
/// 2026-09-30): the Finder fan of the first few, and the count.
///
/// It used to preview its FIRST item as though the folder were a PDF (#25), and the Inspector,
/// the Segments pane and the Reader followed that first item (#5204, #5205): select a folder and
/// three panes described one file inside it. The folder is now what every pane shows, and the
/// Preview draws it the way it draws a multiple selection, with the same view.
struct FolderContentsPreview: View {
    let folderId: String
    var onNavigateToDocument: ((String) -> Void)?

    @Environment(DocumentStore.self) private var documentStore
    @State private var items: [Document] = []
    @State private var loaded = false

    var body: some View {
        Group {
            if !items.isEmpty {
                MultiSelectionPreviewStack(documents: items)
            } else if loaded {
                ContentUnavailableView(
                    "Empty Folder",
                    systemImage: "folder",
                    description: Text("Items you add to this folder appear here.")
                )
            } else {
                // ★ EVERY FRAME PERFECT: hold a quiet frame while the cached
                // children resolve (usually one turn) instead of flashing the
                // empty-folder state first.
                Color.clear
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task(id: folderId) {
            // Every child, subfolders included: the count is what the folder holds, as Finder counts it.
            items = await documentStore.children(of: folderId)
            loaded = true
        }
    }
}
