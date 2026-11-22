#if os(iOS)
import XCTest

/// `ios.nav.one-path` (#6944), `ios.proof.flows-on-a-simulator`: on an iPhone the person goes folder → item → image, and Back returns one level each time. Drives the app's REAL root view against the seeded harness engine that
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

    func testFolderThenItemThenBackOneLevelEachTime() throws {
        let app = try launchSeededApp()
        XCTAssertTrue(app.otherElements["library.content.ready"].waitForExistence(timeout: 60), "the library never showed")

        let folder = row(app, containing: "Test Archive")
        XCTAssertTrue(folder.waitForExistence(timeout: 20), "no folder row")
        folder.tap()

        let item = row(app, containing: "sample.jpg")
        XCTAssertTrue(item.waitForExistence(timeout: 20), "the folder lists no image")
        item.tap()
        XCTAssertTrue(app.images.firstMatch.waitForExistence(timeout: 20), "the item's image is not shown")

        back(app)
        XCTAssertTrue(row(app, containing: "sample.jpg").waitForExistence(timeout: 10), "Back from the item did not show the list")
    }

    /// `ios.nav.folders-push`, `ios.nav.back-is-one-step` (#6945): Test Archive > Box 1 > Series A, and Back
    /// shows Box 1's list, then Test Archive's list.
    func testNestedFoldersPushAndBackIsOneFolder() throws {
        let app = try launchSeededApp()
        XCTAssertTrue(app.otherElements["library.content.ready"].waitForExistence(timeout: 60), "the library never showed")

        row(app, containing: "Test Archive").tap()
        let box = row(app, containing: "Box 1")
        XCTAssertTrue(box.waitForExistence(timeout: 20), "Test Archive lists no Box 1")
        box.tap()
        let series = row(app, containing: "Series A")
        XCTAssertTrue(series.waitForExistence(timeout: 20), "Box 1 lists no Series A")
        series.tap()
        XCTAssertTrue(app.navigationBars["Series A"].waitForExistence(timeout: 10), "Series A's screen was not pushed")

        back(app)
        XCTAssertTrue(app.navigationBars["Box 1"].waitForExistence(timeout: 10), "Back from Series A did not show Box 1")
        XCTAssertTrue(row(app, containing: "Series A").exists, "Box 1's list has no Series A row")
        back(app)
        XCTAssertTrue(app.navigationBars["Test Archive"].waitForExistence(timeout: 10), "Back did not show Test Archive")
        XCTAssertTrue(row(app, containing: "Box 1").exists, "Test Archive's list has no Box 1 row")
    }

    /// `ios.nav.sidebar-drills` (#6946): no row of the sidebar expands in place.
    func testTheSidebarHasNoDisclosureRow() throws {
        let app = try launchSeededApp()
        XCTAssertTrue(app.otherElements["library.content.ready"].waitForExistence(timeout: 60), "the library never showed")
        XCTAssertEqual(app.disclosureTriangles.count, 0, "an iPhone sidebar row expands in place")
    }
}
#endif
