@testable import Fichero
import Foundation
import Testing

/// Sidebar multi-selection scopes the library (Daniel, 2026-08-09, #105):
/// "if three sidebar items are selected they should all be in library view."
/// These pin the two pure helpers the ContentView handler is built on.
struct SidebarMultiSelectionScopeTests {
    @Test("scope ids: document destinations only, sorted for stable comparison")
    func scopeIdsFilterAndSort() {
        let destinations: Set<SidebarDestination> = [
            .document("b"), .document("a"), .search("s1")
        ]
        #expect(sidebarScopeDocumentIds(destinations) == ["a", "b"])
    }

    @Test("scope ids: empty and non-document selections yield no scope")
    func scopeIdsEmpty() {
        #expect(sidebarScopeDocumentIds([]) == [])
        #expect(sidebarScopeDocumentIds([.search("s1"), .chat("c1")]) == [])
    }

    @Test("any selected PDF triggers page expansion; none or empty does not")
    func expandsWheneverAPDFIsSelected() {
        // #114/#115 (supersedes the all-PDF gate): adding an image to five
        // PDFs must not collapse the pages back to document icons — every
        // PDF expands, non-PDFs ride along as themselves.
        let pdf1 = Document(id: "p1", docType: .file, fileType: .pdf, name: "A.pdf")
        let pdf2 = Document(id: "p2", docType: .file, fileType: .pdf, name: "B.pdf")
        let image = Document(id: "i1", docType: .file, fileType: .image, name: "C.png")
        let page = Document(id: "pg1", parentId: "p1", docType: .page, fileType: .pdf, name: "Page 1")
        #expect(sidebarScopeExpandsToPages([pdf1, pdf2]))
        #expect(sidebarScopeExpandsToPages([pdf1, image]))
        #expect(!sidebarScopeExpandsToPages([image]))
        // A PAGE row is not a PDF container — selecting pages never re-expands.
        #expect(!sidebarScopeExpandsToPages([page, image]))
        #expect(!sidebarScopeExpandsToPages([]))
    }
}
