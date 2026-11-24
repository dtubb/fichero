@testable import Fichero
import XCTest

/// `ios.nav.sidebar-drills` (#6946): the phone's rows are flat.
final class SidebarPhoneRowsTests: XCTestCase {
    func testThePhoneNeverExpandsARowInPlace() {
        XCTAssertFalse(SidebarPhone.rowExpandsInPlace(isPhone: true))
    }

    func testTheIPadAndTheMacKeepTheTree() {
        XCTAssertTrue(SidebarPhone.rowExpandsInPlace(isPhone: false))
    }

    func testTheMacAndTheIPadShowTheChevronOnARowWithChildren() {
        XCTAssertTrue(SidebarPhone.showsDisclosure(isExpandable: true, isPhone: false))
        XCTAssertFalse(SidebarPhone.showsDisclosure(isExpandable: true, isPhone: true))
        XCTAssertFalse(SidebarPhone.showsDisclosure(isExpandable: false, isPhone: false))
    }
}
