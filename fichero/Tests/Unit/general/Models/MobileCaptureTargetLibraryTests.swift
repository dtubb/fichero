@testable import Fichero
import Foundation
import XCTest

/// #3281:a capture waits for an uploader aimed at the project it was taken in.
@MainActor
final class MobileCaptureTargetLibraryTests: XCTestCase {
    func testAnItemForAnotherProjectIsNotUploadedToThisOne() async throws {
        EngineConfig.defaults.set("/Users/testuser/Archive/Open.fichero", forKey: RemoteAccessConfig.pairedLibraryPathKey)
        defer { EngineConfig.defaults.removeObject(forKey: RemoteAccessConfig.pairedLibraryPathKey) }
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let host = "https://pairing.example.com"
        let store = MobileCaptureQueueStore(storageDirectory: dir)
        _ = try store.enqueueCapturedImage(Data([1]), targetLibraryId: "A", targetHost: host)
        _ = try store.enqueueCapturedImage(Data([2]), targetLibraryId: "B", targetHost: host)
        _ = try store.enqueueCapturedImage(Data([3]), targetHost: host)

        let uploader = KeyedUploader(host: URL(string: host), key: "A")
        let summary = await store.resumePendingUploads(using: uploader)

        XCTAssertEqual(summary.uploadedCount, 2)   // A's and the unstamped one; B waits
        XCTAssertEqual(store.items.filter { $0.targetLibraryId == "B" }.first?.uploadState, .queued)
    }
}

@MainActor
private struct KeyedUploader: MobileCaptureQueueUploading {
    let host: URL?
    let key: String?
    var backendHost: URL? { host }
    var targetLibraryKey: String? { key }
    func upload(fileURL: URL, catalog: MobileCaptureCatalogFields) async throws -> String { "doc" }
}
