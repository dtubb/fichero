#if os(iOS)
import XCTest

/// `ios.nav.one-path` (#6944), `ios.proof.flows-on-a-simulator`: on an iPhone the person goes folder → item → image, Reader
/// and Info, and Back returns one level each time. Drives the app's REAL root view against the seeded harness engine that
/// `scripts/run_ios_ui_sim.sh` starts; it FAILS, not skips, when that engine is missing. WRITTEN, NOT RUN: no simulator on
/// the Pro while the owner works.
final class IOSDrillDownUITests: XCTestCase {
    private func launchSeededApp() throws -> XCUIApplication {
        let env = ProcessInfo.processInfo.environment
        let socket = try XCTUnwrap(env["FICHERO_FORCE_UDS_PATH"], "run through scripts/run_ios_ui_sim.sh: no engine socket")
        let library = try XCTUnwrap(env["FICHERO_UITEST_LIBRARY"], "run through scripts/run_ios_ui_sim.sh: no seeded project")
        let app = XCUIApplication()
        app.launchArguments = ["--uitesting", "-fichero.remote_access.paired_library_path", library]
        app.launchEnvironment["FICHERO_FORCE_UDS_PATH"] = socket
        app.launch()
        return app
    }

    private func row(_ app: XCUIApplication, containing name: String) -> XCUIElement {
        app.descendants(matching: .any)
            .matching(NSPredicate(format: "identifier BEGINSWITH 'libraryRow.' AND label CONTAINS %@", name)).firstMatch
    }

    private func back(_ app: XCUIApplication) {
        let button = app.navigationBars.buttons.element(boundBy: 0)
        XCTAssertTrue(button.waitForExistence(timeout: 10), "no Back button")
        button.tap()
    }

    func testFolderThenItemThenReaderAndInfoAndBackOneLevelEachTime() throws {
        let app = try launchSeededApp()
        XCTAssertTrue(app.otherElements["library.content.ready"].waitForExistence(timeout: 60), "the library never showed")

        let folder = row(app, containing: "Test Archive")
        XCTAssertTrue(folder.waitForExistence(timeout: 20), "no folder row")
        folder.tap()

        let item = row(app, containing: "sample.jpg")
        XCTAssertTrue(item.waitForExistence(timeout: 20), "the folder lists no image")
        item.tap()
        XCTAssertTrue(app.images.firstMatch.waitForExistence(timeout: 20), "the item's image is not shown")

        app.buttons["Reader"].tap()
        XCTAssertTrue(app.navigationBars["Reader"].waitForExistence(timeout: 10), "Reader did not open")
        app.buttons["Info"].tap()
        XCTAssertTrue(app.navigationBars["Info"].waitForExistence(timeout: 10), "Info did not open")

        back(app)
        XCTAssertTrue(app.navigationBars["Reader"].waitForExistence(timeout: 10), "Back from Info did not show Reader")
        back(app)
        XCTAssertTrue(app.images.firstMatch.waitForExistence(timeout: 10), "Back from Reader did not show the image")
        back(app)
        XCTAssertTrue(row(app, containing: "sample.jpg").waitForExistence(timeout: 10), "Back from the item did not show the list")
    }
}
#endif
