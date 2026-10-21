#if os(iOS)
import XCTest

/// `m2p.ios.sidebar-to-library` (#5964): on an iPhone, with the Mac connected, the person can go sidebar -> library -> item and
/// back. WRITTEN, NOT RUN: no simulator on the Pro while the owner works; it runs on the M4 / the builder, against a connected
/// engine (`FICHERO_UITEST_ENGINE`, as the other connected iOS UI tests).
final class IOSSidebarToLibraryUITests: XCTestCase {
    func testChoosingAProjectInTheSidebarShowsItsContentAndBackReturns() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--uitesting"]
        app.launch()
        try XCTSkipUnless(app.otherElements["library.content.ready"].waitForExistence(timeout: 30), "needs a connected engine")

        // Go back to the sidebar column (the system Back at the content column's leading edge).
        let back = app.navigationBars.buttons.element(boundBy: 0)
        XCTAssertTrue(back.waitForExistence(timeout: 10), "no way back to the sidebar")
        back.tap()

        // The sidebar's first project row; choosing it must show the content column again.
        let projectRow = app.buttons.matching(identifier: "sidebar.project.row").firstMatch
        XCTAssertTrue(projectRow.waitForExistence(timeout: 10), "the sidebar shows no project row")
        projectRow.tap()
        XCTAssertTrue(app.otherElements["library.content.ready"].waitForExistence(timeout: 10),
                      "choosing a project in the sidebar did not show its content")
        // Choosing the SAME row again from the sidebar still goes in.
        app.navigationBars.buttons.element(boundBy: 0).tap()
        projectRow.tap()
        XCTAssertTrue(app.otherElements["library.content.ready"].waitForExistence(timeout: 10),
                      "choosing the row that is already selected did not show its content")
    }
}
#endif
