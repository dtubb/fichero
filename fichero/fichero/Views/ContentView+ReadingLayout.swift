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
        if let match, detailDocument?.id != match.id {
            detailDocument = match
            browserSelection = [match.id]
        }
    }

    /// Resolved PDF file path for the currently previewed document, or nil.
    var detailPDFPath: String? {
        guard let doc = detailDocument else { return nil }
        if doc.fileType == .pdf, let path = doc.path, !path.isEmpty { return path }
        if doc.docType == .page {
            if let metaPath = doc.metadata["pdf_path"]?.value as? String, !metaPath.isEmpty { return metaPath }
            let parentId = doc.metadata["pdf_parent_id"]?.value as? String ?? doc.parentId
            if let pid = parentId,
               let parent = documentStore.currentDocuments.first(where: { $0.id == pid }),
               let path = parent.path, !path.isEmpty { return path }
        }
        return nil
    }

    /// Current PDF page index for the previewed document.
    var selectedPageIndex: Int {
        if let doc = detailDocument, doc.docType == .page {
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
            if let doc = detailDocument, doc.docType == .page {
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
                onPageIndexChange: { idx in syncGridSelectionToPDFPage(index: idx) }
            )
            .overlay { paneFocusIndicator(for: .preview) }
            .frame(maxWidth: .infinity)

            ResizableDivider(
                width: $pageContentPaneWidth,
                minWidth: 160,
                maxWidth: 400,
                edge: .trailing
            )

            PageContentPane(document: detailDocument)
                .frame(width: CGFloat(pageContentPaneWidth))
                .overlay { paneFocusIndicator(for: .content) }
        }
        .frame(maxWidth: .infinity)
    }
}
