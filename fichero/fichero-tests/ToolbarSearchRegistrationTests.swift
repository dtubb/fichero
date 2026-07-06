@testable import Fichero
import XCTest

/// Guards the NSToolbar duplicate-identifier crash invariant (#1447/#2309):
/// only the primary split-pane may register `.searchable(placement: .toolbar)`.
/// LibraryView and SearchView both gate their toolbar search slot through this
/// predicate, so a regression here would re-open the crash a headless build
/// can't catch.
final class ToolbarSearchRegistrationTests: XCTestCase {
    func testPrimaryPaneRegistersToolbarSearch() {
        XCTAssertTrue(ToolbarSearchRegistration.shouldRegister(isSecondarySplitPane: false))
    }

    func testSecondaryPaneSkipsToolbarSearch() {
        // The whole point: a secondary copy MUST NOT register, or two identical
        // toolbar search items collide and crash NSToolbar.
        XCTAssertFalse(ToolbarSearchRegistration.shouldRegister(isSecondarySplitPane: true))
    }
}
