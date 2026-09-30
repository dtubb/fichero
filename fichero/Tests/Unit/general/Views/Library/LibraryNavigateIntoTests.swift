@testable import Fichero
import Foundation
import Testing

/// A double-click is also two single clicks now that the double tap is simultaneous (#5276). Where a
/// plain tap navigates into a folder (sidebar hidden, compact width), the pane was entered once per
/// click and again by the double-click. Entering the folder the pane already shows is a no-op.
struct LibraryNavigateIntoTests {
    @Test("the pane already showing a folder does not enter it again")
    func alreadyShown() {
        #expect(LibraryView.paneAlreadyShows("f1", folderId: "doc:f1"))
        #expect(LibraryView.paneAlreadyShows("f1", folderId: "f1"))
        #expect(!LibraryView.paneAlreadyShows("f1", folderId: "doc:f2"))
        #expect(!LibraryView.paneAlreadyShows("f1", folderId: nil))
    }

    @Test("both navigation paths go through the guard")
    func bothPathsGuarded() throws {
        let source = try String(
            contentsOf: AppSource.root().appendingPathComponent("Views/Library/LibraryView+Selection.swift"),
            encoding: .utf8)
        #expect(source.components(separatedBy: "navigateIntoUnlessThere(doc)").count - 1 == 2)
        #expect(source.components(separatedBy: "onNavigateInto(doc)").count - 1 == 1, "only inside the guard")
    }
}
