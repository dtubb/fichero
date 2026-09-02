@testable import Fichero
import Foundation
import Testing

// #100 sibling sweep (2026-08-09): a grid click on a page of the ALREADY-
// rooted PDF moves the page-focus cursor (onPageFocus) instead of re-rooting
// detailDocument — table mode's behavior since the sidebar page-click fix.
// Re-rooting reloads the transcript pane under a click meant to move within
// it (#1463 class). File-scope function, testable off-main.
//
// Every case below passes `isShowingSearchResults: false` because every one of
// them is a BROWSE click — a folder listing, where the clicked page and the
// rooted PDF are the same document. `searchHitAlwaysReroots` is the other
// half, added 2026-09-02.
@Suite("pageClickMovesCursorOnly — grid page clicks move the cursor")
struct PageClickCursorTests {
    private let pdf = Document(id: "pdf-1", docType: .file, fileType: .pdf, name: "Diary.pdf")
    private let page1 = Document(id: "p1", parentId: "pdf-1", docType: .page, name: "Page 1", sequence: 1)
    private let page2 = Document(id: "p2", parentId: "pdf-1", docType: .page, name: "Page 2", sequence: 2)

    @Test("a page of the rooted PDF moves the cursor")
    func pageOfRootedPDF() {
        #expect(pageClickMovesCursorOnly(clicked: page2, detailDocument: pdf, isShowingSearchResults: false))
    }

    @Test("a sibling page keeps the cursor path when a page is rooted")
    func siblingOfRootedPage() {
        #expect(pageClickMovesCursorOnly(clicked: page2, detailDocument: page1, isShowingSearchResults: false))
    }

    @Test("re-root when the page belongs to a DIFFERENT pdf, or nothing is rooted")
    func rerootsAcrossParentsAndFromNil() {
        let otherPDF = Document(id: "pdf-2", docType: .file, fileType: .pdf, name: "Other.pdf")
        #expect(!pageClickMovesCursorOnly(clicked: page2, detailDocument: otherPDF, isShowingSearchResults: false))
        #expect(!pageClickMovesCursorOnly(clicked: page2, detailDocument: nil, isShowingSearchResults: false))
    }

    @Test("non-page clicks always re-root")
    func nonPageClicksReroot() {
        #expect(!pageClickMovesCursorOnly(clicked: pdf, detailDocument: pdf, isShowingSearchResults: false))
        let folder = Document(id: "f1", docType: .folder, name: "Letters")
        #expect(!pageClickMovesCursorOnly(clicked: folder, detailDocument: pdf, isShowingSearchResults: false))
    }

    @Test("virtual page cursors resolve their parent via metadata")
    func virtualCursorParent() {
        let vpage = Document.virtualPageCursor(pdfParentId: "pdf-1", pageIndex: 4)
        #expect(pdfParentDocumentId(of: vpage) == "pdf-1")
        #expect(pageClickMovesCursorOnly(clicked: vpage, detailDocument: pdf, isShowingSearchResults: false))
    }

    /// The reported defect: a hit that is a page of the currently rooted PDF
    /// took the cursor branch, so the reader never moved and the result looked
    /// unopenable (2026-09-02).
    @Test("a SEARCH HIT always re-roots, even a page of the rooted PDF")
    func searchHitAlwaysReroots() {
        #expect(!pageClickMovesCursorOnly(
            clicked: page2, detailDocument: pdf, isShowingSearchResults: true
        ))
        // The sibling-page case too — the same click, the same two documents,
        // and the only difference is which list the row came from.
        #expect(!pageClickMovesCursorOnly(
            clicked: page2, detailDocument: page1, isShowingSearchResults: true
        ))
        // A virtual page cursor is no exception.
        let vpage = Document.virtualPageCursor(pdfParentId: "pdf-1", pageIndex: 4)
        #expect(!pageClickMovesCursorOnly(
            clicked: vpage, detailDocument: pdf, isShowingSearchResults: true
        ))
    }

    @Test("the library passes the search condition from the pane, not a guess")
    func callSitePassesTheCondition() throws {
        let selection = try AppSource.text("Views/Library/LibraryView+Selection.swift")
        #expect(selection.contains("isShowingSearchResults: activeSearchQuery != nil"),
                "handleTap must state which list the click came from — the same "
                    + "condition the mode-scoping fix uses")
    }

    @Test("a page with no resolvable parent re-roots")
    func orphanPageReroots() {
        let orphan = Document(id: "p9", docType: .page, name: "Page 9", sequence: 9)
        #expect(!pageClickMovesCursorOnly(clicked: orphan, detailDocument: pdf, isShowingSearchResults: false))
    }
}
