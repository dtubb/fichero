import SwiftUI

/// A selected folder in a Preview pane shown as the Library's own List or Table, scoped to the
/// folder (`library.preview.folder-view-per-pane`): one row renderer, not a second copy. A click on
/// a row makes that item the Inspector's and Reader's subject while the pane keeps the rows, exactly
/// as a canvas card does (`onFolderCanvasFocus`, #5305); a double-click opens the item here.
struct FolderRowsPreview: View {
    let folderId: String
    let mode: ViewDisplayMode
    var onNavigateToDocument: ((String) -> Void)?

    @Environment(DocumentStore.self) private var documentStore
    @Environment(\.onFolderCanvasFocus) private var onFolderCanvasFocus
    @Environment(\.onFolderCanvasSelection) private var onFolderCanvasSelection
    @State private var items: [Document] = []
    @State private var loaded = false
    @State private var selection: Set<String> = []
    @State private var detail: Document?
    @State private var toolbar = LibraryToolbarState()

    var body: some View {
        LibraryView(
            documents: items,
            contentCollection: .documents,
            isLoading: !loaded,
            isConnected: documentStore.isConnected,
            errorMessage: nil,
            onRetry: {},
            libraryToolbar: toolbar,
            selection: $selection,
            detailDocument: $detail,
            defaultDisplayMode: mode,
            availableDisplayModes: [mode],
            folderId: folderId,
            onNavigateInto: { onNavigateToDocument?($0.id) },
            onOpenItem: { onNavigateToDocument?($0.id) }
        )
        .task(id: folderId) {
            loaded = false
            items = await documentStore.children(of: folderId)
            loaded = true
        }
        .onChange(of: selection) { _, ids in
            let chosen = items.filter { ids.contains($0.id) }
            onFolderCanvasFocus?(chosen.count == 1 ? chosen.first : nil)
            onFolderCanvasSelection?(chosen)
        }
        .onDisappear {
            onFolderCanvasFocus?(nil)
            onFolderCanvasSelection?([])
        }
    }
}

#Preview("Table") {
    LibraryPreviewFixtures.environment(FolderRowsPreview(folderId: "folder-1", mode: .table))
        .frame(width: 600, height: 400)
}
