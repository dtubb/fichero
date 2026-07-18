import SwiftUI

// MARK: - Reading Layout Helpers (#1189)
//
// PDF page-index math + grid↔page sync used by the reader. The old
// `fivePaneReadingView` (page-strip | PDF | content) was retired in the reader
// IA fold — its role is now the tabbed reader's Page tab.

extension ContentView {

    /// Sync grid selection to the PDF page at `index`. Fired from
    /// PDFPageView's coordinator when the user scrolls to a different page
    /// in multi-page mode (#586). Finds the matching page Document among
    /// `documentStore.currentDocuments` and updates `detailDocument`.
    ///
    /// The `sequence - 1 == index` formula converts our 1-based `sequence`
    /// (page_number) to PDFKit's 0-based index.
    /// Pure: the page Document whose 1-based `sequence` maps to PDFKit's 0-based
    /// `index` (`sequence - 1 == index`). Extracted for #3013 page-index tests.
    static func pageDocument(atPDFIndex index: Int, in documents: [Document]) -> Document? {
        documents.first { $0.docType == .page && ($0.sequence ?? 0) == index + 1 }
    }

    /// Pure: the 0-based PDF page index for a page Document (1-based `sequence`),
    /// clamped to 0; non-page docs (or nil) resolve to the first page. (#3013)
    static func pdfPageIndex(for doc: Document?) -> Int {
        guard let doc, doc.docType == .page else { return 0 }
        return max(0, (doc.sequence ?? 1) - 1)
    }

    func syncGridSelectionToPDFPage(index: Int) {
        guard let match = Self.pageDocument(atPDFIndex: index, in: documentStore.currentDocuments) else { return }
        // Update only the page-focus cursor — never re-root detailDocument or
        // browserSelection from a scroll event (#1463). detailDocument stays
        // pinned to the active container (parent PDF / folder) so the WebKit
        // transcript doesn't reload; pageFocusDocument drives the inspector.
        if pageFocusDocument?.id != match.id {
            pageFocusDocument = match
        }
    }

    /// Resolved parent-PDF document id for the currently previewed document, or nil.
    var detailPDFDocumentId: String? {
        guard let doc = detailDocument else { return nil }
        guard CanvasDocumentPolicy.shouldUsePDFCanvas(for: doc) else { return nil }
        if doc.fileType == .pdf { return doc.id }
        if doc.docType == .page {
            return resolvedParentPDFDocumentId(for: doc)
        }
        return nil
    }

    /// Resolve the parent PDF document id for a page child. Page documents
    /// carry their own id, but the bytes live on the parent PDF document.
    func resolvedParentPDFDocumentId(for doc: Document) -> String? {
        let parentId = doc.metadata["pdf_parent_id"]?.value as? String ?? doc.parentId
        return parentId
    }

    /// Current PDF page index. Prefers pageFocusDocument (set by scroll/flip)
    /// over detailDocument so the PDF viewer tracks scrolling without
    /// re-rooting the active container (#1463).
    var selectedPageIndex: Int {
        Self.pdfPageIndex(for: pageFocusDocument ?? detailDocument)
    }

    /// Number of page-child documents for the previewed PDF (#3866). The reading
    /// pane needs only the COUNT, so this skips the O(n log n) filter+sort +
    /// array allocation that the old `pdfDocPages` accessor cost — read twice per
    /// render for `isEmpty ? nil : count`.
    var pdfDocPageCount: Int {
        Self.pdfDocPageCount(in: documentStore.currentDocuments)
    }

    /// Pure page-child count over a document set — no sort, no allocation
    /// (`lazy`). Static so it's unit-testable without a ContentView. (#3866)
    static func pdfDocPageCount(in documents: [Document]) -> Int {
        documents.lazy.filter { $0.docType == .page }.count
    }

}
