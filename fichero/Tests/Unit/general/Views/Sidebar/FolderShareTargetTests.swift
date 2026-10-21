@testable import Fichero
import XCTest

/// `sharing.settings.project-share-sheet`, folder Share… (#5967). Not run on the Pro; the builder/M4 runs it.
@MainActor
final class FolderShareTargetTests: XCTestCase {
    func testAFolderTargetIsIdentifiedByItsFolderSoTheSheetReopensPerFolder() {
        let library = UUID()
        let a = FolderShareTarget(libraryId: library, folderId: "f1", name: "Letters")
        let b = FolderShareTarget(libraryId: library, folderId: "f2", name: "Letters")
        XCTAssertNotEqual(a.id, b.id)
        XCTAssertEqual(a.id, "f1")
    }

    func testSettingTheTargetOnTheSidebarStateOpensTheSheetAndClearingItClosesIt() {
        let state = SidebarState(windowId: "test")
        XCTAssertNil(state.folderToShare)
        state.folderToShare = FolderShareTarget(libraryId: UUID(), folderId: "f1", name: "Letters")
        XCTAssertEqual(state.folderToShare?.folderId, "f1")
        state.folderToShare = nil
        XCTAssertNil(state.folderToShare)
    }
}
