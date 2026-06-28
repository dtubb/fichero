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
        let backendService = EmbeddedBackendService()
        backendService.status = .running
        delegate.backendService = backendService

        delegate.applicationWillTerminate(Notification(name: NSApplication.willTerminateNotification))

        XCTAssertEqual(backendService.status, .stopped)
    }
}
#endif
