@testable import Fichero
import XCTest

/// Tests for MobileCaptureQueueItem's custom Codable. MobileCaptureQueueTests
/// exercises queue behavior but not the decoder's forward-compat branch:
/// `requiresExplicitRetry` was added later, so a persisted item lacking the key
/// must decode (defaulting to false) rather than throw — a throw would drop the
/// entire persisted queue, not just one field. Pure codec, no live engine.
final class MobileCaptureQueueItemCodingTests: XCTestCase {

    private func makeItem(requiresExplicitRetry: Bool) -> MobileCaptureQueueItem {
        MobileCaptureQueueItem(
            id: "cap-1",
            imageFileName: "shot.jpg",
            createdAt: Date(timeIntervalSince1970: 1_700_000_000),
            updatedAt: Date(timeIntervalSince1970: 1_700_000_100),
            catalog: MobileCaptureCatalogFields(),
            uploadState: .queued,
            uploadedDocumentId: nil,
            lastError: nil,
            requiresExplicitRetry: requiresExplicitRetry,
            retryCount: 2,
            lastAttemptAt: nil
        )
    }

    /// Encode → decode preserves every field (baseline for the codec).
    func testRoundTripPreservesFields() throws {
        let item = makeItem(requiresExplicitRetry: true)
        let data = try JSONEncoder().encode(item)
        let decoded = try JSONDecoder().decode(MobileCaptureQueueItem.self, from: data)
        XCTAssertEqual(decoded, item)
    }

    /// A legacy persisted item (no requiresExplicitRetry key) must decode with
    /// the field defaulted to false — never throw.
    func testLegacyItemWithoutRequiresExplicitRetryDefaultsFalse() throws {
        // Start from a real encoded item, then strip the newer key to mimic
        // an item persisted before the field existed.
        let data = try JSONEncoder().encode(makeItem(requiresExplicitRetry: true))
        var obj = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        obj.removeValue(forKey: "requiresExplicitRetry")
        XCTAssertNil(obj["requiresExplicitRetry"], "precondition: key removed")
        let legacyData = try JSONSerialization.data(withJSONObject: obj)

        let decoded = try JSONDecoder().decode(MobileCaptureQueueItem.self, from: legacyData)
        XCTAssertFalse(decoded.requiresExplicitRetry)   // ← defaulted, no throw
        // Surrounding fields still decode.
        XCTAssertEqual(decoded.id, "cap-1")
        XCTAssertEqual(decoded.retryCount, 2)
        XCTAssertEqual(decoded.uploadState, .queued)
    }

    /// Absent optional keys (uploadedDocumentId / lastError / lastAttemptAt)
    /// decode to nil rather than throwing.
    func testAbsentOptionalKeysDecodeAsNil() throws {
        let data = try JSONEncoder().encode(makeItem(requiresExplicitRetry: false))
        var obj = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        for key in ["uploadedDocumentId", "lastError", "lastAttemptAt"] {
            obj.removeValue(forKey: key)
        }
        let trimmed = try JSONSerialization.data(withJSONObject: obj)
        let decoded = try JSONDecoder().decode(MobileCaptureQueueItem.self, from: trimmed)
        XCTAssertNil(decoded.uploadedDocumentId)
        XCTAssertNil(decoded.lastError)
        XCTAssertNil(decoded.lastAttemptAt)
    }
}
