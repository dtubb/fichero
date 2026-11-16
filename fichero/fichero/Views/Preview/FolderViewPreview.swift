import SwiftUI

/// The Preview's folder branch: this pane's chosen view of the folder (`PreviewFolderView`, stored
/// on the pane, `library.preview.folder-view-per-pane`). Canvas is the folder canvas, List, Table and
/// Icons are the Library's own views scoped to the folder, under the Source head alone (#6562). The choice is read, never rewritten, here.
struct FolderViewPreview: View {
    let folderId: String
    /// False for a group, which is always its pages on its own board.
    var usesPaneView = true
    var onNavigateToDocument: ((String) -> Void)?

    @Environment(\.panePreviewFolderView) private var storedView

    var body: some View {
        let view = PreviewFolderView.effective(storedView)
        if usesPaneView, let mode = view.displayMode {
            FolderRowsPreview(folderId: folderId, mode: mode, onNavigateToDocument: onNavigateToDocument)
        } else {
            FolderContentsPreview(folderId: folderId, onNavigateToDocument: onNavigateToDocument)
        }
    }
}

#Preview("Default (Table)") {
    LibraryPreviewFixtures.environment(FolderViewPreview(folderId: "folder-1"))
        .frame(width: 600, height: 400)
}
