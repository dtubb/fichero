#if os(iOS)
import XCTest

/// `ios.item.pages`, `ios.item.swipe-changes-page`, `ios.item.header-says-where`,
/// `ios.item.voiceover-reaches-every-page` (#6947): the item view's four pages on an iPhone, on the app's REAL root
/// view and the seeded harness engine. WRITTEN, NOT RUN: no simulator on the Pro while the owner works.
final class IOSItemPagesUITests: XCTestCase {
    private func openSeededImage() throws -> XCUIApplication {
        let env = ProcessInfo.processInfo.environment
        let socket = try XCTUnwrap(env["FICHERO_FORCE_UDS_PATH"], "run through scripts/run_ios_ui_sim.sh: no engine socket")
        let library = try XCTUnwrap(env["FICHERO_UITEST_LIBRARY"], "run through scripts/run_ios_ui_sim.sh: no seeded project")
        let app = XCUIApplication()
        app.launchArguments = ["--uitesting", "-fichero.remote_access.paired_library_path", library]
        app.launchEnvironment["FICHERO_FORCE_UDS_PATH"] = socket
        app.launch()
        XCTAssertTrue(app.otherElements["library.content.ready"].waitForExistence(timeout: 60), "the library never showed")
        func row(_ name: String) -> XCUIElement {
            app.descendants(matching: .any)
                .matching(NSPredicate(format: "identifier BEGINSWITH 'libraryRow.' AND label CONTAINS %@", name)).firstMatch
        }
        XCTAssertTrue(row("Test Archive").waitForExistence(timeout: 20), "no folder row")
        row("Test Archive").tap()
        XCTAssertTrue(row("sample.jpg").waitForExistence(timeout: 20), "the folder lists no image")
        row("sample.jpg").tap()
        XCTAssertTrue(app.images.firstMatch.waitForExistence(timeout: 20), "the item's image is not shown")
        return app
    }

    func testTheHeaderNamesFourPagesAndATapGoesToThePage() throws {
        let app = try openSeededImage()
        for name in ["Source", "Reader", "Segments", "Info"] {
            XCTAssertTrue(app.buttons[name].exists, "no \(name) in the header")
        }
        XCTAssertTrue(app.buttons["Source"].isSelected, "Source is not the selected page on arrival")
        app.buttons["Info"].tap()
        XCTAssertTrue(app.buttons["Info"].isSelected, "tapping Info did not select it")
    }

    /// The walk stops at Segments, which owns its drags (`ios.item.segments-own-their-gestures`); Info is reached by
    /// the header. The spec's three-swipes-to-Info acceptance line conflicts with that rule: raised with the owner.
    func testSwipingLeftWalksToSegmentsAndTheHeaderReachesInfo() throws {
        let app = try openSeededImage()
        for name in ["Reader", "Segments"] {
            app.swipeLeft()
            XCTAssertTrue(app.buttons[name].waitForExistence(timeout: 10))
            XCTAssertTrue(app.buttons[name].isSelected, "a swipe left did not show \(name)")
        }
        app.buttons["Info"].tap()
        XCTAssertTrue(app.buttons["Info"].isSelected, "tapping Info did not select it")
    }

    func testAHorizontalDragOnSegmentsLeavesSegmentsShowing() throws {
        let app = try openSeededImage()
        app.buttons["Segments"].tap()
        app.swipeLeft()
        XCTAssertTrue(app.buttons["Segments"].isSelected, "a drag changed the Segments page")
    }
}
#endif
