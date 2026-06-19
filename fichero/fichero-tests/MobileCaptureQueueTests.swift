@testable import Fichero
import Foundation
import XCTest

final class MobileCaptureQueueTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testCatalogFieldsMapToDocumentMetadataAndFallbackTitle() {
        let fields = MobileCaptureCatalogFields(
            title: "  Scan Title  ",
            folderName: "  Reference  ",
            seriesName: "  Box 17  ",
            pageOrder: 12,
            notes: "  Needs review  ",
            sourceArchiveHint: "  archive-bin  "
        )

        XCTAssertEqual(fields.documentName(fallback: "capture.jpg"), "Scan Title")
        XCTAssertEqual(fields.documentMetadata()["capture_folder"], "Reference")
        XCTAssertEqual(fields.documentMetadata()["capture_series"], "Box 17")
        XCTAssertEqual(fields.documentMetadata()["capture_page_order"], "12")
        XCTAssertEqual(fields.documentMetadata()["capture_notes"], "Needs review")
        XCTAssertEqual(fields.documentMetadata()["capture_source_archive_hint"], "archive-bin")
    }

    func testQueuePersistsAndEditedItemsReturnToQueued() throws {
        let storageDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: storageDirectory) }

        let store = MobileCaptureQueueStore(storageDirectory: storageDirectory)
        let item = try store.enqueueCapturedImage(
            Data([0x01, 0x02, 0x03]),
            catalog: MobileCaptureCatalogFields(title: "Initial")
        )

        store.updateCatalog(id: item.id) { catalog in
            catalog.notes = "Edited after capture"
        }

        XCTAssertEqual(store.items.first?.catalog.notes, "Edited after capture")
        XCTAssertEqual(store.items.first?.uploadState, .queued)

        let reloaded = MobileCaptureQueueStore(storageDirectory: storageDirectory)
        XCTAssertEqual(reloaded.items.count, 1)
        XCTAssertEqual(reloaded.items.first?.catalog.title, "Initial")
        XCTAssertEqual(reloaded.items.first?.catalog.notes, "Edited after capture")
        XCTAssertEqual(reloaded.items.first?.uploadState, .queued)
    }

    func testRetryPolicyRejectsLocalhostAndKeepsQueueWaiting() async throws {
        let storageDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: storageDirectory) }

        let store = MobileCaptureQueueStore(storageDirectory: storageDirectory)
        _ = try store.enqueueCapturedImage(
            Data([0x04, 0x05, 0x06]),
            catalog: MobileCaptureCatalogFields(title: "Offline")
        )

        let uploader = FakeCaptureUploader(backendHost: URL(string: "http://127.0.0.1:8765"))
        let summary = await store.resumePendingUploads(using: uploader)

        XCTAssertEqual(summary.waitingCount, 1)
        XCTAssertTrue(uploader.uploads.isEmpty)
        XCTAssertEqual(store.items.first?.uploadState, .waitingForBackend)
    }

    func testRetryUploadsMarkSuccessAndFailure() async throws {
        let storageDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: storageDirectory) }

        let store = MobileCaptureQueueStore(storageDirectory: storageDirectory)
        _ = try store.enqueueCapturedImage(
            Data([0x07, 0x08, 0x09]),
            catalog: MobileCaptureCatalogFields(title: "Queued")
        )

        let uploader = FakeCaptureUploader(
            backendHost: URL(string: "https://pairing.example.com"),
            result: .success("doc-123")
        )
        let summary = await store.resumePendingUploads(using: uploader)

        XCTAssertEqual(summary.uploadedCount, 1)
        XCTAssertEqual(uploader.uploads.count, 1)
        XCTAssertEqual(store.items.first?.uploadState, .uploaded)
        XCTAssertEqual(store.items.first?.uploadedDocumentId, "doc-123")
    }

    func testRetryUploadsRecordFailures() async throws {
        let storageDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: storageDirectory) }

        let store = MobileCaptureQueueStore(storageDirectory: storageDirectory)
        _ = try store.enqueueCapturedImage(
            Data([0x0A, 0x0B, 0x0C]),
            catalog: MobileCaptureCatalogFields(title: "Failed")
        )

        let uploader = FakeCaptureUploader(
            backendHost: URL(string: "https://pairing.example.com"),
            result: .failure(NSError(domain: "capture", code: 1, userInfo: [NSLocalizedDescriptionKey: "boom"]))
        )
        let summary = await store.resumePendingUploads(using: uploader)

        XCTAssertEqual(summary.failedCount, 1)
        XCTAssertEqual(store.items.first?.uploadState, .failed)
        XCTAssertEqual(store.items.first?.lastError, "boom")
    }

    func testIosConnectionSurfaceExposesCaptureQueueRoute() throws {
        let source = try Self.appSource("FicheroApp_iOS.swift")

        XCTAssertTrue(source.contains("Open Capture Queue"))
        XCTAssertTrue(source.contains("MobileCaptureQueueView("))
        XCTAssertTrue(source.contains("resumePendingUploads("))
        XCTAssertTrue(source.contains(".environmentObject(captureQueue)"))
    }
}

private final class FakeCaptureUploader: MobileCaptureQueueUploading {
    let backendHost: URL?
    var uploads: [(URL, MobileCaptureCatalogFields)] = []
    var result: Result<String, Error>

    init(
        backendHost: URL?,
        result: Result<String, Error> = .success("doc-1")
    ) {
        self.backendHost = backendHost
        self.result = result
    }

    func upload(fileURL: URL, catalog: MobileCaptureCatalogFields) async throws -> String {
        uploads.append((fileURL, catalog))
        return try result.get()
    }
}
