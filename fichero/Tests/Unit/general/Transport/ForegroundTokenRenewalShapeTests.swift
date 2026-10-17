@testable import Fichero
import XCTest

/// #3290: the iOS app renews a near-expiry device token when it comes to the
/// foreground, not only at launch. Source-shape guard (no window server).
@MainActor
final class ForegroundTokenRenewalShapeTests: XCTestCase {
    func testIOSSceneRenewsDeviceTokenWhenActive() throws {
        let source = try AppSource.text("FicheroApp_iOS.swift")
        let scene = try XCTUnwrap(source.range(of: "onChange(of: scenePhase) { _, phase in"))
        let tail = String(source[scene.upperBound...].prefix(300))
        XCTAssertTrue(tail.contains("phase == .active"), "renewal must run on .active only")
        XCTAssertTrue(tail.contains("DeviceTokenRenewal.renewIfNeeded"), "the foreground hook no longer renews")
    }
}
