import SwiftUI

/// Watches the document store for the window, so the window itself does not (#4228).
///
/// `ContentView` used to carry these three `.onChange(of: documentStore…)` modifiers itself. An
/// `onChange` reads its value while the body is built, which made every folder load (a new
/// `currentDocuments`), every change-stream splice (`revision`) and every root change
/// (`collections`) re-evaluate the whole window: the content column, the sidebar and every pane
/// head, whatever the handler then did. Here only this empty view re-runs; the window updates only
/// when a handler changes its state.
///
/// Its identity is stable (no `.id`), so when the window switches project and hands it another
/// store, each `onChange` still fires with the new store's values, as it did on `ContentView`.
struct DocumentStoreChangeObserver: View {
    let store: DocumentStore
    let onCollectionsChange: (_ old: [Document], _ new: [Document]) -> Void
    let onCurrentDocumentsChange: ([Document]) -> Void
    let onRevisionChange: () -> Void

    var body: some View {
        Color.clear
            .frame(width: 0, height: 0)
            .accessibilityHidden(true)
            .onChange(of: store.collections) { old, new in onCollectionsChange(old, new) }
            .onChange(of: store.currentDocuments) { _, new in onCurrentDocumentsChange(new) }
            .onChange(of: store.revision) { _, _ in onRevisionChange() }
    }
}

#Preview("Document store change observer") {
    let store = DocumentStore.preview
    VStack(alignment: .leading, spacing: 8) {
        Text("\(store.collections.count) collections, revision \(store.revision)")
        DocumentStoreChangeObserver(
            store: store,
            onCollectionsChange: { _, _ in },
            onCurrentDocumentsChange: { _ in },
            onRevisionChange: {}
        )
    }
    .padding()
}
