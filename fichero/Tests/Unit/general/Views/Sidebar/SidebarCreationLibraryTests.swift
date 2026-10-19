@testable import Fichero
import XCTest

/// #5817: the sidebar + menu's New Folder and Import land in the selected item's library, else this window's,
/// else Global, and never nowhere while any of them is open.
final class SidebarCreationLibraryTests: XCTestCase {
    private let global = LibraryManager.globalLibraryId

    func testTheSelectedItemsLibraryWins() {
        let selected = UUID()
        let window = UUID()
        XCTAssertEqual(sidebarCreationLibraryId(selected: selected, window: window, open: [selected, window, global]), selected)
    }

    func testTheWindowsLibraryIsUsedWhenGlobalHasNotOpenedYet() {
        let window = UUID()
        XCTAssertEqual(sidebarCreationLibraryId(selected: nil, window: window, open: [window]), window)
    }

    func testGlobalIsTheLastResort() {
        XCTAssertEqual(sidebarCreationLibraryId(selected: nil, window: UUID(), open: [global]), global)
    }

    func testNothingOpenMeansNoLibrary() {
        XCTAssertNil(sidebarCreationLibraryId(selected: UUID(), window: UUID(), open: []))
    }
}
