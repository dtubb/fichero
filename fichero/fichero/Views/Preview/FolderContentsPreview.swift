import SwiftUI

/// A selected plain folder previews like a PDF (#25, Daniel): its items are
/// its "pages". The pane shows the folder's FIRST previewable item through
/// that item's own preview route; a swipe (or ←/→) then steps the selection
/// through the folder's children via the ContentView sibling navigation —
/// the same machinery a PDF's page flips use.
///
/// Subfolders are skipped rather than recursed into: the first frame should
/// be an item, and entering a nested folder is a selection, not a preview.
struct FolderContentsPreview: View {
    let folderId: String
    var onNavigateToDocument: ((String) -> Void)?

    @Environment(DocumentStore.self) private var documentStore
    @State private var firstItem: Document?
    @State private var loaded = false

    var body: some View {
        Group {
            if let firstItem {
                // The child's own preview — image, PDF, text, media — with
                // navigation forwarded so stepping keeps working (#25). Safe
                // from recursion: subfolders are filtered out below, so this
                // nested EditorView can never route back here.
                EditorView(
                    document: firstItem,
                    showHeader: false,
                    onNavigateToDocument: onNavigateToDocument
                )
                .id(firstItem.id)
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
            firstItem = await documentStore.children(of: folderId)
                .first { $0.docType != .folder }
            loaded = true
        }
    }
}
