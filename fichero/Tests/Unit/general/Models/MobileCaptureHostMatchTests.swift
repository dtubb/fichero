@testable import Fichero
import XCTest

/// #3281: an outbox item holds for its own host, but the match must not be an exact string compare, or
/// "https://Mac.local./" never equals "https://mac.local" and the item is blocked forever.
@MainActor
final class MobileCaptureHostMatchTests: XCTestCase {
    func testCaseTrailingDotAndSlashDoNotMakeHostsDiffer() {
        XCTAssertTrue(MobileCaptureQueueRouting.sameHost("https://Mac.local./", "https://mac.local"))
        XCTAssertTrue(MobileCaptureQueueRouting.sameHost("HTTPS://mac.local:8443/", "https://mac.local:8443"))
        XCTAssertTrue(MobileCaptureQueueRouting.sameHost("https://mac.local/api/", "https://mac.local/api"))
    }

    func testRealDifferencesStillHold() {
        XCTAssertFalse(MobileCaptureQueueRouting.sameHost("https://mac.local", "https://air.local"))
        XCTAssertFalse(MobileCaptureQueueRouting.sameHost("https://mac.local:8443", "https://mac.local"))
        XCTAssertFalse(MobileCaptureQueueRouting.sameHost("https://mac.local", nil))
    }

    func testResumeUsesTheNormalisedMatch() throws {
        let source = try AppSource.code("Models/MobileCaptureQueue+Uploading.swift")
        XCTAssertTrue(source.contains("MobileCaptureQueueRouting.sameHost(target"), "resume went back to an exact compare")
    }
}
