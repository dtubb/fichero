@testable import Fichero
import Foundation
import Testing

// #100 sibling sweep (2026-08-09): a grid click on a page of the ALREADY-
// rooted PDF moves the page-focus cursor (onPageFocus) instead of re-rooting
// detailDocument — table mode's behavior since the sidebar page-click fix.
// Re-rooting reloads the transcript pane under a click meant to move within
// it (#1463 class). File-scope function, testable off-main.
@Suite("pageClickMovesCursorOnly — grid page clicks move the cursor")
struct PageClickCursorTests {
    private let pdf = Document(id: "pdf-1", docType: .file, fileType: .pdf, name: "Diary.pdf")
    private let page1 = Document(id: "p1", parentId: "pdf-1", docType: .page, name: "Page 1", sequence: 1)
    private let page2 = Document(id: "p2", parentId: "pdf-1", docType: .page, name: "Page 2", sequence: 2)

    @Test("a page of the rooted PDF moves the cursor")
    func pageOfRootedPDF() {
        #expect(pageClickMovesCursorOnly(clicked: page2, detailDocument: pdf))
    }

    @Test("a sibling page keeps the cursor path when a page is rooted")
    func siblingOfRootedPage() {
        #expect(pageClickMovesCursorOnly(clicked: page2, detailDocument: page1))
    }

    @Test("re-root when the page belongs to a DIFFERENT pdf, or nothing is rooted")
    func rerootsAcrossParentsAndFromNil() {
        let otherPDF = Document(id: "pdf-2", docType: .file, fileType: .pdf, name: "Other.pdf")
        #expect(!pageClickMovesCursorOnly(clicked: page2, detailDocument: otherPDF))
        #expect(!pageClickMovesCursorOnly(clicked: page2, detailDocument: nil))
    }

    @Test("non-page clicks always re-root")
    func nonPageClicksReroot() {
        #expect(!pageClickMovesCursorOnly(clicked: pdf, detailDocument: pdf))
        let folder = Document(id: "f1", docType: .folder, name: "Letters")
        #expect(!pageClickMovesCursorOnly(clicked: folder, detailDocument: pdf))
    }

    @Test("virtual page cursors resolve their parent via metadata")
    func virtualCursorParent() {
        let vpage = Document.virtualPageCursor(pdfParentId: "pdf-1", pageIndex: 4)
        #expect(pdfParentDocumentId(of: vpage) == "pdf-1")
        #expect(pageClickMovesCursorOnly(clicked: vpage, detailDocument: pdf))
    }

    @Test("a page with no resolvable parent re-roots")
    func orphanPageReroots() {
        let orphan = Document(id: "p9", docType: .page, name: "Page 9", sequence: 9)
        #expect(!pageClickMovesCursorOnly(clicked: orphan, detailDocument: pdf))
    }
}
