import SwiftUI

/// **Show in Activity** (`activity.pane.commands-through-the-table`, #6441): from a page's or a document's context menu, the
/// Activity window opens grouped by File with that file's row selected (the page's own row, else its document's).
struct ShowInActivityMenuItem: View {
    let document: Document
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        Button {
            ActivityWindowSelectionState.shared.showFile(document)
            openWindow(id: ActivityWindowSelectionState.monitorWindowID)
        } label: {
            Label("Show in Activity", systemImage: PaneSpec.Kind.activity.icon)
        }
    }
}

/// The menu bar's Show in Activity on the one selected page or document: the context menus' item, disabled otherwise.
struct FocusedShowInActivityButton: View {
    let target: ItemVerbsTarget?

    var body: some View {
        if let documents = target?.documents, documents.count == 1, let document = documents.first, document.docType != .folder {
            ShowInActivityMenuItem(document: document)
        } else {
            Button {} label: { Label("Show in Activity", systemImage: PaneSpec.Kind.activity.icon) }
                .disabled(true)
        }
    }
}

#Preview("Show in Activity") {
    Menu("Page") {
        ShowInActivityMenuItem(document: Document(id: "p1", name: "Page 1"))
    }
    .padding()
}
