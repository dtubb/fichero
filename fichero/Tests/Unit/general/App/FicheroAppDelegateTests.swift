#if canImport(AppKit)
import AppKit
import XCTest

@testable import Fichero

@MainActor
final class FicheroAppDelegateTests: XCTestCase {
    func testApplicationSupportsSecureRestorableState() {
        let delegate = FicheroAppDelegate()

        XCTAssertTrue(delegate.applicationSupportsSecureRestorableState(NSApplication.shared))
    }

    func testApplicationWillTerminateStopsBackendService() {
        let delegate = FicheroAppDelegate()
        delegate.controller.backendService.status = .running

        delegate.applicationWillTerminate(Notification(name: NSApplication.willTerminateNotification))

        XCTAssertEqual(delegate.controller.backendService.status, .stopped)
    }

    /// The engine connect moved to `applicationWillFinishLaunching` so it runs while the first
    /// window lays out (#5228). Its test-host guard had to move with it: a test host that dials
    /// the live engine fights the developer's ⌘R instance over the socket (#3902).
    func testWillFinishLaunchingNeverStartsTheEngineInTheTestHost() async {
        let delegate = FicheroAppDelegate()

        delegate.applicationWillFinishLaunching(Notification(name: NSApplication.willFinishLaunchingNotification))
        delegate.applicationDidFinishLaunching(Notification(name: NSApplication.didFinishLaunchingNotification))
        await Task.yield()

        XCTAssertEqual(delegate.controller.backendService.startAttemptsPassedGuard, 0)
    }
}
#endif
