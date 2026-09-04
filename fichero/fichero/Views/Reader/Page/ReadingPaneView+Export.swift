import Foundation

// MARK: - What "export what I am reading" means (Daniel, 2026-09-03)

extension ReadingPaneView {
    /// The documents File ▸ Export ▸ Markdown/Word write out: every document
    /// this pane is RENDERING, which for a multi-selection is all of them and
    /// otherwise is the one — the visible-surface selection ruling, applied to
    /// a verb that writes files.
    ///
    /// Carries the reading text alongside each id so the Markdown export
    /// writes exactly what the proxy icon drags, and the Word export still has
    /// an id to hand the engine's own .docx service.
    ///
    /// Lives in its own file, not in `ReadingPaneView.body`'s struct: the pane
    /// is already at the `type_body_length` ceiling.
    var readerExportTargets: ReaderExportTargets {
        let documents = multiDocuments.count > 1
            ? multiDocuments
            : (effectiveDocument.map { [$0] } ?? [])
        return ReaderExportTargets(items: documents.map { document in
            ReaderExportTargets.Item(
                id: document.id,
                name: DocumentTitle.displayName(for: document),
                text: document.pageContent ?? ""
            )
        })
    }
}
