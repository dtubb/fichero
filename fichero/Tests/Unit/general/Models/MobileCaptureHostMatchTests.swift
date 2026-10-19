@testable import Fichero
import Foundation
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

    func testResumeUploadsAnItemWhoseHostOnlyDiffersInSpelling() async throws {
        EngineConfig.defaults.set("/Users/testuser/Archive/Open.fichero", forKey: RemoteAccessConfig.pairedLibraryPathKey)
        defer { EngineConfig.defaults.removeObject(forKey: RemoteAccessConfig.pairedLibraryPathKey) }
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let store = MobileCaptureQueueStore(storageDirectory: dir)
        _ = try store.enqueueCapturedImage(Data([1]), targetHost: "https://Pairing.Example.com./")
        _ = try store.enqueueCapturedImage(Data([2]), targetHost: "https://other.example.com")

        let summary = await store.resumePendingUploads(using: HostUploader(host: URL(string: "https://pairing.example.com")))

        XCTAssertEqual(summary.uploadedCount, 1, "the item for another host waits; the respelt one goes")
    }
}

@MainActor
private struct HostUploader: MobileCaptureQueueUploading {
    let host: URL?
    var backendHost: URL? { host }
    var targetLibraryKey: String? { nil }
    func upload(fileURL: URL, catalog: MobileCaptureCatalogFields) async throws -> String { "doc" }
}
