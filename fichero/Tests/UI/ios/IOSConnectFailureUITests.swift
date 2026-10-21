#if os(iOS)
import XCTest

/// `m2p.ios.connect-failure-offers-recovery`: with the server not reachable, the iPhone offers Reconnect and Change Server at the
/// top of whatever column is showing. WRITTEN, NOT RUN: no simulator on the Pro while the owner works. Launches against an address
/// nothing listens on, through the saved-host default (`fichero.server.host`, `EngineConfig.userDefaultsKey`).
final class IOSConnectFailureUITests: XCTestCase {
    func testAnUnreachableServerOffersReconnectAndChangeServer() throws {
        let app = XCUIApplication()
        app.launchArguments = ["--uitesting", "-fichero.server.host", "https://127.0.0.1:9"]
        app.launch()
        let reconnect = app.buttons["connection.recovery.reconnect"]
        let change = app.buttons["connection.recovery.change-server"]
        XCTAssertTrue(reconnect.waitForExistence(timeout: 30), "no Reconnect when the server is unreachable")
        XCTAssertTrue(change.exists, "no Change Server when the server is unreachable")
        change.tap()
        XCTAssertTrue(app.staticTexts["Connect to a Mac"].waitForExistence(timeout: 10) || app.sheets.firstMatch.waitForExistence(timeout: 10),
                      "Change Server did not open the Connect sheet")
    }
}
#endif
