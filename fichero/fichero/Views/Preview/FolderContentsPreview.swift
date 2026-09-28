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
            // Previewable children only: subfolders are a selection, not a
            // preview, and a workflow mirror has no source file — routing one
            // here surfaced the Quick Look error state (Daniel, 2026-08-10).
            firstItem = Self.pageShown(in: await documentStore.children(of: folderId))
            loaded = true
        }
    }

    /// The item this preview shows for a folder: its first child that is not a folder or a workflow
    /// mirror. The ONE rule, so the panes that follow the Preview (Segments, Reader) show the same page
    /// (#5204, #5205).
    static func pageShown(in children: [Document]) -> Document? {
        children.first { $0.docType != .folder && !$0.isWorkflowNode }
    }

    /// What a pane following the Preview is handed (`FolderPageShown`): the folder's page once found for
    /// THIS folder, else the document itself.
    static func shown(_ document: Document?, isFolder: Bool, found: (folderId: String, page: Document?)?) -> Document? {
        guard isFolder, let document, let found, found.folderId == document.id, let page = found.page else { return document }
        return page
    }

    /// Whether the Preview shows a folder through one of its items: a PLAIN folder. A folder that is an
    /// image or a PDF is shown as itself (`EditorView.folderPreviewRoute`).
    static func previewsAnItem(_ folder: Document) -> Bool {
        folder.docType == .folder && folder.fileType != .image && folder.fileType != .pdf
    }
}

/// A pane that follows the Preview: given a folder, it shows the page the Preview shows for that folder
/// (`FolderContentsPreview.pageShown`), not the folder (#5204, #5205). A folder with no such item stays
/// the folder, so a folder of folders still reads as itself (the Reader's folder proxy, 2026-09-05).
/// Anything that is not a folder passes through.
struct FolderPageShown<Content: View>: View {
    let document: Document?
    /// False passes the folder through: the Reader's open-folder fallback has no Preview page to follow.
    var resolves = true
    @ViewBuilder let content: (Document?) -> Content

    @Environment(DocumentStore.self) private var documentStore: DocumentStore?
    /// The page found, keyed by its folder so a page found for one folder is never shown for the next.
    @State private var found: (folderId: String, page: Document?)?

    private var isFolder: Bool { resolves && document.map(FolderContentsPreview.previewsAnItem) == true }

    var body: some View {
        content(FolderContentsPreview.shown(document, isFolder: isFolder, found: found))
            .task(id: isFolder ? document?.id : nil) {
                guard isFolder, let document, let documentStore else { return }
                found = (document.id, FolderContentsPreview.pageShown(in: await documentStore.children(of: document.id)))
            }
    }

}
