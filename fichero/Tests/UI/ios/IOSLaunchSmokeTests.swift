#if os(iOS)
import XCTest

/// spec: ui-testing-strategy §ui-testing.crossplatform-plan (#4173). Nothing else launches the iOS app, and the
/// launch-crash class (#4162, the 1 MB main-stack overflow #4331) only shows when it is launched.
/// This launches it and asks only that it is still the foreground app a few seconds later: a crash
/// on launch or in the first layout pass fails here. It does not need a Mac engine, so it passes
/// with the app showing its connect screen. Run it on an iPhone and an iPad simulator and a device.
final class IOSLaunchSmokeTests: XCTestCase {

    func testAppLaunchesAndStaysInTheForeground() {
        let app = XCUIApplication()
        app.launchArguments = ["--uitesting"]
        app.launch()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 30), "the app did not reach the foreground")
        // A first-layout crash lands a moment after launch returns.
        Thread.sleep(forTimeInterval: 5)
        XCTAssertEqual(app.state, .runningForeground, "the app is no longer running: it crashed after launch")
    }
}
#endif
