@testable import Fichero
import XCTest

/// The pane breadcrumb as a navigator, like Finder's path control (#5218). Daniel found the library item
/// greyed out in the crumb menu above "syriac-rtl": a root the pane could not go to. What breaks without
/// these: the library crumb goes dead again, or a crumb navigates by some path other than the sidebar's
/// reveal seam, so the sidebar, the panes and ⌘[ / ⌘] stop agreeing about where you are.
@MainActor
final class PaneCrumbNavigatorTests: XCTestCase {
    func testALibraryCrumbIsNavigableAndNamesItsLibrary() {
        let id = UUID()
        let crumb = PaneCrumb(id: PaneCrumb.libraryPrefix + id.uuidString, title: "Acceptance 2026-09-27b",
                              icon: "books.vertical.fill")
        XCTAssertTrue(crumb.isNavigable)
        XCTAssertEqual(crumb.libraryId, id)
        XCTAssertNil(PaneCrumb(id: "doc-1", title: "syriac-rtl", icon: "folder.fill").libraryId,
                     "a document's crumb is not a library")
    }

    func testALibraryCrumbSelectsThatLibraryThroughTheSidebarsSeam() {
        let id = UUID()
        let posted = expectation(forNotification: .sidebarRevealDocument, object: nil) { note in
            note.userInfo?["libraryId"] as? String == id.uuidString && note.userInfo?["documentId"] == nil
        }
        PaneCrumb.reveal(PaneCrumb(id: PaneCrumb.libraryPrefix + id.uuidString, title: "L", icon: "books.vertical.fill"))
        wait(for: [posted], timeout: 1)
    }

    func testADocumentCrumbRevealsItsDocument() {
        let posted = expectation(forNotification: .sidebarRevealDocument, object: nil) { note in
            note.userInfo?["documentId"] as? String == "doc-1" && note.userInfo?["libraryId"] == nil
        }
        PaneCrumb.reveal(PaneCrumb(id: "doc-1", title: "syriac-rtl", icon: "folder.fill"))
        wait(for: [posted], timeout: 1)
    }
}
