@testable import Fichero
import XCTest

/// The reopen list drops a library that sits in a Trash folder (#6377).
final class LibraryTrashPathTests: XCTestCase {
    func testVolumeTrashesPathIsInsideTrash() {
        XCTAssertTrue(LibraryManager.isInsideTrash("/Volumes/Files/.Trashes/503/GHG Box 12.fichero"))
    }

    func testHomeTrashPathIsInsideTrash() {
        XCTAssertTrue(LibraryManager.isInsideTrash("~/.Trash/Old.fichero"))
    }

    func testOrdinaryPathsAreNot() {
        XCTAssertFalse(LibraryManager.isInsideTrash("/Volumes/Files/GHG 12.fichero"))
        XCTAssertFalse(LibraryManager.isInsideTrash("/Volumes/Files/My.Trashes.fichero"))
        XCTAssertFalse(LibraryManager.isInsideTrash("/Volumes/Files/Trash/x.fichero"))
    }
}
