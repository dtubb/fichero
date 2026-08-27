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
}
#endif
