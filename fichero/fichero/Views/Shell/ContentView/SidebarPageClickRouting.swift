import Foundation

// The pure halves of the sidebar page-click routing (2026-08-08): clicking a
// PAGE row in the sidebar must drive the PDF canvas to THAT page. The
// consumer is MainContentModifiers.handleViewModeChange; free functions so
// the seam is unit-testable without a ContentView
// (SidebarPageClickRoutingTests).

/// Parent PDF id for a page document — mirrors
/// `ContentView.resolvedParentPDFDocumentId` (metadata stamp first, then the
/// tree parent).
func sidebarPageParentPDFId(for doc: Document) -> String? {
    doc.metadata["pdf_parent_id"]?.value as? String ?? doc.parentId
}

/// The PDF document id the canvas is currently rooted on, or nil — mirrors
/// `ContentView.detailPDFDocumentId`'s resolution for the two shapes
/// `detailDocument` takes (the PDF itself, or one of its pages).
func sidebarDetailPDFId(for detail: Document?) -> String? {
    guard let detail else { return nil }
    if detail.fileType == .pdf { return detail.id }
    if detail.docType == .page { return sidebarPageParentPDFId(for: detail) }
    return nil
}
