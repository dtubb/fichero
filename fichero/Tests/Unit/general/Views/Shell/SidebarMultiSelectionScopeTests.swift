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

    @Test("any selected CONTAINER (pdf or folder) triggers expansion; leaves do not")
    func expandsWheneverAContainerIsSelected() {
        // #114/#115 then #144: PDFs expand to pages, FOLDERS to their
        // children ("if you select a folder it should also show contents in
        // multiple selection like a pdf"); leaves ride along as themselves.
        let pdf1 = Document(id: "p1", docType: .file, fileType: .pdf, name: "A.pdf")
        let pdf2 = Document(id: "p2", docType: .file, fileType: .pdf, name: "B.pdf")
        let folder = Document(id: "f1", docType: .folder, name: "Screen Shots")
        let image = Document(id: "i1", docType: .file, fileType: .image, name: "C.png")
        let page = Document(id: "pg1", parentId: "p1", docType: .page, fileType: .pdf, name: "Page 1")
        #expect(sidebarScopeExpandsToContents([pdf1, pdf2]))
        #expect(sidebarScopeExpandsToContents([pdf1, image]))
        #expect(sidebarScopeExpandsToContents([folder, image]))
        #expect(sidebarScopeIsExpandableContainer(folder))
        #expect(!sidebarScopeExpandsToContents([image]))
        // A PAGE row is not a container — selecting pages never re-expands.
        #expect(!sidebarScopeExpandsToContents([page, image]))
        #expect(!sidebarScopeExpandsToContents([]))
    }

    @Test("shown set is a SET: parent-and-child ⌘A keeps first occurrence only")
    func dedupeKeepsFirstOccurrenceInOrder() {
        // 2026-08-23 crash: ⌘A selects every visible sidebar row, so an
        // expanded folder AND its child both contribute the child — the
        // duplicate id trapped CanvasArrangement.slotIndices in 3D mode.
        let child = Document(id: "d1", parentId: "f1", docType: .file, fileType: .image, name: "C.png")
        let childAgain = Document(id: "d1", parentId: "f1", docType: .file, fileType: .image, name: "C.png")
        let other = Document(id: "d2", docType: .file, fileType: .image, name: "D.png")
        #expect(sidebarScopeDeduped([child, other, childAgain]).map(\.id) == ["d1", "d2"])
        #expect(sidebarScopeDeduped([]).isEmpty)
        // Unique input passes through untouched, order intact.
        #expect(sidebarScopeDeduped([other, child]).map(\.id) == ["d2", "d1"])
    }
}
