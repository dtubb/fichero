import Foundation
import Testing
@testable import Fichero

/// #6026: the pending-status poll names an engine document, never a project's sidebar row.
struct LibraryViewEngineFolderIdTests {
    @Test func aProjectRowIsNotAnEngineNode() {
        let id = SidebarDestination.library(UUID()).serializedID
        #expect(LibraryView.engineFolderId(fromPaneFolderId: id) == nil)
        #expect(LibraryView.engineFolderId(fromPaneFolderId: nil) == nil)
    }

    @Test func aDocumentRowIsItsEngineId() {
        #expect(LibraryView.engineFolderId(fromPaneFolderId: "doc:abc123") == "abc123")
    }
}
