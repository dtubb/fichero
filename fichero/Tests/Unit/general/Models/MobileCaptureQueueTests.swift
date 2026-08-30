@testable import Fichero
import Foundation
import XCTest

@MainActor
final class MobileCaptureQueueTests: XCTestCase {
    private var originalEngineHost: String?

    override func setUp() {
        super.setUp()
        originalEngineHost = EngineConfig.defaults.string(forKey: EngineConfig.userDefaultsKey)
    }

    override func tearDown() {
        if let originalEngineHost {
            EngineConfig.defaults.set(originalEngineHost, forKey: EngineConfig.userDefaultsKey)
        } else {
            EngineConfig.defaults.removeObject(forKey: EngineConfig.userDefaultsKey)
        }
        originalEngineHost = nil
        super.tearDown()
        EngineConfig.defaults.removeObject(forKey: RemoteAccessConfig.pairedLibraryPathKey)
    }

    private func markDevicePairedWithLibrary() {
        EngineConfig.defaults.set(
            "/Users/testuser/Archive/Open.fichero",
            forKey: RemoteAccessConfig.pairedLibraryPathKey
        )
    }

    private func configureRemoteBackend() {
        EngineConfig.defaults.set("https://pairing.example.com", forKey: EngineConfig.userDefaultsKey)
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

    func testRetryPolicyRequiresPairedLibraryPath() async throws {
        let storageDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: storageDirectory) }

        let store = MobileCaptureQueueStore(storageDirectory: storageDirectory)
        _ = try store.enqueueCapturedImage(
            Data([0x07, 0x08, 0x09]),
            catalog: MobileCaptureCatalogFields(title: "No library")
        )

        let uploader = FakeCaptureUploader(backendHost: URL(string: "https://pairing.example.com"))
        let summary = await store.resumePendingUploads(using: uploader)

        XCTAssertEqual(summary.waitingCount, 1)
        XCTAssertTrue(uploader.uploads.isEmpty)
        XCTAssertEqual(store.items.first?.uploadState, .waitingForBackend)
    }

    func testRetryUploadsMarkSuccessAndFailure() async throws {
        markDevicePairedWithLibrary()
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
        markDevicePairedWithLibrary()
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

    func testConcurrentResumeUploadsUploadEachCaptureExactlyOnce() async throws {
        // #2389: the launch flush (reconnectToConfiguredHost) and the recovery
        // flush (heartbeat / endpoint-failover flipping ready, wired via the iOS
        // root's onChange) can overlap. resumePendingUploads reserves items as
        // `.uploading` synchronously before its first await, so two concurrent
        // flushes must upload each capture exactly once — never dropped, never
        // doubled. If the reservation ever stops being synchronous this fails.
        markDevicePairedWithLibrary()
        let storageDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: storageDirectory) }

        let store = MobileCaptureQueueStore(storageDirectory: storageDirectory)
        for index in 0..<3 {
            _ = try store.enqueueCapturedImage(
                Data([UInt8(index)]),
                catalog: MobileCaptureCatalogFields(title: "Capture \(index)")
            )
        }

        let uploader = FakeCaptureUploader(
            backendHost: URL(string: "https://pairing.example.com"),
            result: .success("doc")
        )
        async let first = store.resumePendingUploads(using: uploader)
        async let second = store.resumePendingUploads(using: uploader)
        let uploadedTotal = await first.uploadedCount + second.uploadedCount

        XCTAssertEqual(uploader.uploads.count, 3, "each capture uploads exactly once across overlapping flushes")
        XCTAssertEqual(uploadedTotal, 3)
        XCTAssertEqual(store.items.filter { $0.uploadState == .uploaded }.count, 3)
    }

    // MARK: — Active-library wiring (#2401)

    func testUploadClientWithTargetLibraryIdFailsWhenLibraryNotOpen() async throws {
        // Verifies that targetLibraryId is used instead of silently falling back to
        // globalLibrary: when the specified library isn't open, the upload fails.
        markDevicePairedWithLibrary()
        configureRemoteBackend()
        let storageDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: storageDirectory) }

        let store = MobileCaptureQueueStore(storageDirectory: storageDirectory)
        _ = try store.enqueueCapturedImage(
            Data([0xAA, 0xBB]),
            catalog: MobileCaptureCatalogFields(title: "Active Library Capture")
        )

        // LibraryManager.shared has no open libraries in unit-test context.
        let unknownId = UUID()
        let client = MobileCaptureBackendUploadClient(
            libraryManager: LibraryManager.shared,
            targetLibraryId: unknownId
        )
        let summary = await store.resumePendingUploads(using: client)

        XCTAssertEqual(summary.failedCount, 1, "upload should fail when targetLibraryId not in openLibraries")
        XCTAssertEqual(store.items.first?.uploadState, .failed)
        XCTAssertEqual(
            store.items.first?.lastError,
            MobileCaptureQueueStoreError.noLibraryAvailable.localizedDescription
        )
    }

    func testUploadClientWithoutTargetLibraryIdFallsBackToGlobalLibrary() async throws {
        // Verifies backward-compat: nil targetLibraryId still attempts globalLibrary
        // and produces the same noLibraryAvailable error when no library is open.
        markDevicePairedWithLibrary()
        configureRemoteBackend()
        let storageDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: storageDirectory) }

        let store = MobileCaptureQueueStore(storageDirectory: storageDirectory)
        _ = try store.enqueueCapturedImage(
            Data([0xCC, 0xDD]),
            catalog: MobileCaptureCatalogFields(title: "Startup Capture")
        )

        // No targetLibraryId → falls back to globalLibrary, which is nil in unit test.
        let client = MobileCaptureBackendUploadClient(libraryManager: LibraryManager.shared)
        let summary = await store.resumePendingUploads(using: client)

        XCTAssertEqual(summary.failedCount, 1, "should fail when globalLibrary not open")
        XCTAssertEqual(store.items.first?.uploadState, .failed)
    }

    // swiftlint:disable:next function_body_length
    func testPersistedUploadingItemsReloadAsFailedAndRequireExplicitRetry() async throws {
        markDevicePairedWithLibrary()
        let storageDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: storageDirectory) }

        let fileManager = FileManager.default
        let assetsDirectory = storageDirectory.appendingPathComponent("assets", isDirectory: true)
        try fileManager.createDirectory(at: assetsDirectory, withIntermediateDirectories: true)

        let item = MobileCaptureQueueItem(
            id: "capture-1",
            imageFileName: "capture-1.jpg",
            createdAt: .now,
            updatedAt: .now,
            catalog: MobileCaptureCatalogFields(title: "Reloaded"),
            uploadState: .uploading,
            uploadedDocumentId: nil,
            lastError: "in flight",
            retryCount: 3,
            lastAttemptAt: .now
        )

        try Data([0x11, 0x22, 0x33]).write(
            to: assetsDirectory.appendingPathComponent(item.imageFileName),
            options: .atomic
        )
        try JSONEncoder().encode([item]).write(
            to: storageDirectory.appendingPathComponent("capture-queue.json"),
            options: .atomic
        )

        let store = MobileCaptureQueueStore(storageDirectory: storageDirectory)
        XCTAssertEqual(store.items.first?.uploadState, .failed)
        XCTAssertEqual(
            store.items.first?.lastError,
            "This upload was interrupted before it completed. Tap Retry to upload it again."
        )
        XCTAssertNil(store.items.first?.lastAttemptAt)

        let uploader = FakeCaptureUploader(backendHost: URL(string: "https://pairing.example.com"))
        let summary = await store.resumePendingUploads(using: uploader)

        XCTAssertEqual(summary.uploadedCount, 0)
        XCTAssertTrue(uploader.uploads.isEmpty)
        XCTAssertEqual(store.items.first?.uploadState, .failed)

        store.updateCatalog(id: "capture-1") { catalog in
            catalog.notes = "Edited after relaunch"
        }

        XCTAssertEqual(store.items.first?.uploadState, .failed)
        XCTAssertEqual(
            store.items.first?.lastError,
            "This upload was interrupted before it completed. Tap Retry to upload it again."
        )

        let editedSummary = await store.resumePendingUploads(using: uploader)
        XCTAssertEqual(editedSummary.uploadedCount, 0)
        XCTAssertEqual(uploader.uploads.count, 0)

        let retrySummary = await store.resumePendingUploads(
            using: uploader,
            retryInterruptedUploads: true
        )

        XCTAssertEqual(retrySummary.uploadedCount, 1)
        XCTAssertEqual(store.items.first?.uploadState, .uploaded)
        XCTAssertEqual(uploader.uploads.count, 1)
    }
}

@MainActor
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
        // Suspend once so overlapping resumePendingUploads calls actually
        // interleave in tests (#2389 concurrency guard). Harmless to the
        // single-flush tests, which await the result regardless.
        await Task.yield()
        uploads.append((fileURL, catalog))
        return try result.get()
    }
}
