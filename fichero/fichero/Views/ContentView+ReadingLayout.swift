import SwiftUI

// MARK: - Five-Pane Reading Layout (#1189)

extension ContentView {

    /// Sync grid selection to the PDF page at `index`. Fired from
    /// PDFPageView's coordinator when the user scrolls to a different page
    /// in multi-page mode (#586). Finds the matching page Document among
    /// `documentStore.currentDocuments` and updates `detailDocument`.
    ///
    /// The `sequence - 1 == index` formula converts our 1-based `sequence`
    /// (page_number) to PDFKit's 0-based index.
    func syncGridSelectionToPDFPage(index: Int) {
        let match = documentStore.currentDocuments.first { doc in
            doc.docType == .page && (doc.sequence ?? 0) == index + 1
        }
        guard let match else { return }
        // Update only the page-focus cursor — never re-root detailDocument or
        // browserSelection from a scroll event (#1463). detailDocument stays
        // pinned to the active container (parent PDF / folder) so the WebKit
        // transcript doesn't reload; pageFocusDocument drives the inspector.
        if pageFocusDocument?.id != match.id {
            pageFocusDocument = match
        }
    }

    /// Resolved PDF file path for the currently previewed document, or nil.
    var detailPDFPath: String? {
        guard let doc = detailDocument else { return nil }
        guard CanvasDocumentPolicy.shouldUsePDFCanvas(for: doc) else { return nil }
        if doc.fileType == .pdf, let path = doc.path, !path.isEmpty { return path }
        if doc.docType == .page {
            return resolvedParentPDFPath(for: doc)
        }
        return nil
    }

    /// Resolve the parent PDF's on-disk path for a page child (page docs have
    /// `path == nil` — the file lives on the parent PDF). Mirrors
    /// `EditorView.resolvedParentPDFPath` (#890): prefer a `pdf_path` that
    /// actually EXISTS on disk and isn't a stale import temp dir, else the
    /// selected collection, else the parent in `currentDocuments`.
    ///
    /// Crucially this returns nil when nothing resolves to a real file rather
    /// than handing a stale/nonexistent path to `PDFView`, which renders a blank
    /// page-with-toolbar (the #1247 symptom). On nil the widescreen layout falls
    /// through to `EditorView`, whose resolver covers the same cases.
    func resolvedParentPDFPath(for doc: Document) -> String? {
        let metadataPath = doc.metadata["pdf_path"]?.value as? String
        if let metadataPath, !metadataPath.isEmpty,
           !metadataPath.contains("/fichero-drop-"),
           FileManager.default.fileExists(atPath: metadataPath) {
            return metadataPath
        }
        let parentId = doc.metadata["pdf_parent_id"]?.value as? String ?? doc.parentId
        if let parentId {
            if let selected = documentStore.selectedCollection,
               selected.id == parentId,
               let selectedPath = selected.path, !selectedPath.isEmpty {
                return selectedPath
            }
            if let parent = documentStore.currentDocuments.first(where: { $0.id == parentId }),
               let parentPath = parent.path, !parentPath.isEmpty {
                return parentPath
            }
        }
        // Last resort: a metadata path that exists even if it wasn't preferred
        // above (e.g. didn't match the parent lookups). Never return a path that
        // isn't on disk — that's what blanks the viewer.
        if let metadataPath, !metadataPath.isEmpty,
           FileManager.default.fileExists(atPath: metadataPath) {
            return metadataPath
        }
        return nil
    }

    /// Current PDF page index. Prefers pageFocusDocument (set by scroll/flip)
    /// over detailDocument so the PDF viewer tracks scrolling without
    /// re-rooting the active container (#1463).
    var selectedPageIndex: Int {
        let focusDoc = pageFocusDocument ?? detailDocument
        if let doc = focusDoc, doc.docType == .page {
            return max(0, (doc.sequence ?? 1) - 1)
        }
        return 0
    }

    /// Page-child documents for the previewed PDF, sorted by sequence.
    var pdfDocPages: [Document] {
        documentStore.currentDocuments
            .filter { $0.docType == .page }
            .sorted { ($0.sequence ?? 0) < ($1.sequence ?? 0) }
    }

    /// Five-pane reading layout: page-thumbnail strip | PDF | content text.
    /// Sidebar (NavigationSplitView) and inspector (window-level HStack) are the other two panes.
    @ViewBuilder
    func fivePaneReadingView(pdfPath: String, pages: [Document]) -> some View {
        let selectedIdx: Int = {
            let focusDoc = pageFocusDocument ?? detailDocument
            if let doc = focusDoc, doc.docType == .page {
                return max(0, (doc.sequence ?? 1) - 1)
            }
            return 0
        }()
        HStack(spacing: 0) {
            DocumentPageListView(
                pdfPath: pdfPath,
                pages: pages,
                selectedPageIndex: selectedIdx,
                onPageSelect: { idx in syncGridSelectionToPDFPage(index: idx) }
            )
            .frame(width: CGFloat(pageListWidth))

            ResizableDivider(width: $pageListWidth, minWidth: 80, maxWidth: 200)

            PDFPageWithToolbar(
                path: pdfPath,
                pageIndex: selectedIdx,
                onPageIndexChange: { idx in
                    guard documentScrollSync.beginDriving(.pdf) else { return }
                    syncGridSelectionToPDFPage(index: idx)
                }
            )
            .overlay { paneFocusIndicator(for: .preview) }
            .frame(minWidth: ContentView.pdfCanvasMinWidth, maxWidth: .infinity)

            ResizableDivider(
                width: $pageContentPaneWidth,
                minWidth: 160,
                maxWidth: 400,
                edge: .trailing
            )

            PageContentPane(document: pageFocusDocument ?? detailDocument)
                .frame(width: CGFloat(pageContentPaneWidth))
                .overlay { paneFocusIndicator(for: .content) }
        }
        .frame(maxWidth: .infinity)
    }
}
