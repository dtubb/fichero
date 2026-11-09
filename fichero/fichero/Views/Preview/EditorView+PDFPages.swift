extension EditorView {
    /// A PDF shows its pages in the pane's folder view, as a group does (`library.pdf.opens-as-its-pages`, #6410). One whose
    /// pages the engine has not listed yet (no children) still shows the file itself rather than an empty list.
    static func pdfPreviewRoute(for doc: Document) -> PreviewRoute {
        doc.childCount > 0 ? .folderContents(folderId: doc.id) : .storageDisplay(documentId: doc.id)
    }
}
