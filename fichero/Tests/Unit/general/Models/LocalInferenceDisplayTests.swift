@testable import Fichero
import XCTest

/// Unit tests for the pure local-inference presentation mapping (#3120).
/// Exercises the state machine directly — no transport stub needed because the
/// display logic is separated from `LocalInferenceStore`'s I/O.
final class LocalInferenceDisplayTests: XCTestCase {

    // MARK: Service state → badge

    func testHealthyBadge() {
        let badge = LocalInferenceDisplay.badge(state: "healthy", lastError: nil)
        XCTAssertEqual(badge.text, "Healthy")
        XCTAssertEqual(badge.tint, .success)
    }

    func testStartingBadge() {
        XCTAssertEqual(LocalInferenceDisplay.badge(state: "starting", lastError: nil).tint, .active)
    }

    func testDegradedBadge() {
        XCTAssertEqual(LocalInferenceDisplay.badge(state: "degraded", lastError: nil).tint, .warning)
    }

    func testStoppedBadge() {
        let badge = LocalInferenceDisplay.badge(state: "stopped", lastError: nil)
        XCTAssertEqual(badge.text, "Stopped")
        XCTAssertEqual(badge.tint, .neutral)
    }

    func testFailedBadgeSurfacesErrorVerbatim() {
        let badge = LocalInferenceDisplay.badge(state: "failed", lastError: "port 8123 in use")
        XCTAssertEqual(badge.text, "Failed — port 8123 in use")
        XCTAssertEqual(badge.tint, .error)
    }

    func testFailedBadgeWithoutErrorStillReadsFailed() {
        let badge = LocalInferenceDisplay.badge(state: "failed", lastError: nil)
        XCTAssertEqual(badge.text, "Failed")
        XCTAssertEqual(badge.tint, .error)
    }

    func testFailedBadgeIgnoresEmptyError() {
        XCTAssertEqual(LocalInferenceDisplay.badge(state: "failed", lastError: "").text, "Failed")
    }

    func testUnknownStateFallsBackNeutral() {
        let badge = LocalInferenceDisplay.badge(state: "provisioning", lastError: nil)
        XCTAssertEqual(badge.text, "Provisioning")
        XCTAssertEqual(badge.tint, .neutral)
    }

    // MARK: Job terminal detection (drives the poll loop)

    func testTerminalOnError() {
        XCTAssertTrue(LocalInferenceDisplay.isTerminal(state: "running", error: "boom", percent: 20))
    }

    func testTerminalOnFullPercent() {
        XCTAssertTrue(LocalInferenceDisplay.isTerminal(state: "running", error: nil, percent: 100))
    }

    func testTerminalOnDoneState() {
        XCTAssertTrue(LocalInferenceDisplay.isTerminal(state: "completed", error: nil, percent: nil))
        XCTAssertTrue(LocalInferenceDisplay.isTerminal(state: "cancelled", error: nil, percent: nil))
    }

    func testNotTerminalMidDownload() {
        XCTAssertFalse(LocalInferenceDisplay.isTerminal(state: "downloading", error: nil, percent: 42))
    }

    func testNotTerminalWithNoSignal() {
        XCTAssertFalse(LocalInferenceDisplay.isTerminal(state: nil, error: nil, percent: nil))
    }

    // MARK: Catalog row — unsupported entries stay visible but greyed (#3119)

    func testSupportedInstalledRow() {
        let row = LocalInferenceDisplay.row(supported: true, unsupportedReason: nil, installed: true)
        XCTAssertTrue(row.installed)
        XCTAssertFalse(row.disabled)
        XCTAssertNil(row.unsupportedReason)
    }

    func testUnsupportedRowKeepsReason() {
        let row = LocalInferenceDisplay.row(
            supported: false,
            unsupportedReason: "requires 16 GB unified memory",
            installed: false
        )
        XCTAssertTrue(row.disabled)
        XCTAssertEqual(row.unsupportedReason, "requires 16 GB unified memory")
    }

    func testNilSupportedDefaultsSupported() {
        let row = LocalInferenceDisplay.row(supported: nil, unsupportedReason: "ignored", installed: nil)
        XCTAssertFalse(row.disabled)
        XCTAssertFalse(row.installed)
        XCTAssertNil(row.unsupportedReason)
    }

    // MARK: Download progress fraction

    func testPercentTakesPrecedence() {
        XCTAssertEqual(LocalInferenceDisplay.progressFraction(current: 1, total: 4, percent: 50), 0.5)
    }

    func testFallsBackToCurrentOverTotal() {
        XCTAssertEqual(LocalInferenceDisplay.progressFraction(current: 3, total: 4, percent: nil), 0.75)
    }

    func testIndeterminateWhenTotalUnknown() {
        XCTAssertNil(LocalInferenceDisplay.progressFraction(current: 3, total: nil, percent: nil))
        XCTAssertNil(LocalInferenceDisplay.progressFraction(current: 3, total: 0, percent: nil))
    }

    func testFractionClampedToUnitRange() {
        XCTAssertEqual(LocalInferenceDisplay.progressFraction(current: nil, total: nil, percent: 150), 1)
        XCTAssertEqual(LocalInferenceDisplay.progressFraction(current: nil, total: nil, percent: -10), 0)
    }
}

// MARK: - Catalog labels (#4560 follow-up)

/// The catalog used to render five OCR-looking names with a byte count and
/// nothing else: no capability, no memory floor, no reason to pick one. These
/// pin the labels that make a 6 GB download a decision rather than a gamble.
final class LocalInferenceCatalogLabelTests: XCTestCase {

    private func bytes(_ value: Int) -> String { "\(value) B" }

    func testSubtitleJoinsSizeAndMemoryFloor() {
        let subtitle = LocalInferenceDisplay.subtitle(
            downloadSizeBytes: 42,
            diskUsageBytes: nil,
            memoryClass: "needs 16 GB unified memory",
            format: bytes
        )
        XCTAssertEqual(subtitle, "42 B · needs 16 GB unified memory")
    }

    func testSubtitleFallsBackToDiskUsageForInstalledModels() {
        let subtitle = LocalInferenceDisplay.subtitle(
            downloadSizeBytes: nil,
            diskUsageBytes: 7,
            memoryClass: nil,
            format: bytes
        )
        XCTAssertEqual(subtitle, "7 B")
    }

    func testSubtitleOmitsWhatTheBackendDidNotState() {
        // A user-configured model in the store has neither a published size
        // nor a floor. Inventing either would be worse than saying nothing.
        XCTAssertEqual(
            LocalInferenceDisplay.subtitle(downloadSizeBytes: nil, diskUsageBytes: 0, memoryClass: "", format: bytes),
            ""
        )
    }

    func testCapabilityLabels() {
        XCTAssertEqual(LocalInferenceDisplay.capabilityLabel("vision"), "OCR / vision")
        XCTAssertEqual(LocalInferenceDisplay.capabilityLabel("audio"), "audio")
        XCTAssertEqual(LocalInferenceDisplay.capabilityLabel("text"), "text")
    }

    func testAnUnknownCapabilityReadsAsTextRatherThanBlank() {
        XCTAssertEqual(LocalInferenceDisplay.capabilityLabel("telepathy"), "text")
    }
}

/// The Whisper rows decode the honesty fields the backend now sends. An older
/// engine omits them entirely, and the row must still decode with safe
/// defaults rather than failing the whole Settings pane.
final class LocalModelStatusDecodingTests: XCTestCase {

    private func decode(_ json: String) throws -> LocalModelStatus {
        try JSONDecoder().decode(LocalModelStatus.self, from: Data(json.utf8))
    }

    func testDecodesTheUnavailableReasonAndNote() throws {
        let model = try decode("""
        {"model_id": "tiny", "model_type": "whisper", "display_name": "Whisper tiny",
         "size_bytes": 0, "is_downloaded": false, "expected_size_mb": 74, "path": null,
         "note": "Fastest and least accurate.", "available": false,
         "unavailable_reason": "The MLX runtime has no transcriber yet.",
         "download_state": "failed", "download_error": "RepositoryNotFoundError"}
        """)

        XCTAssertEqual(model.available, false)
        XCTAssertEqual(model.unavailableReason, "The MLX runtime has no transcriber yet.")
        XCTAssertEqual(model.note, "Fastest and least accurate.")
        XCTAssertEqual(model.downloadState, "failed")
        XCTAssertEqual(model.downloadError, "RepositoryNotFoundError")
    }

    func testAnOlderEngineWithoutTheHonestyFieldsStillDecodes() throws {
        let model = try decode("""
        {"model_id": "base", "model_type": "whisper", "display_name": "Whisper base",
         "size_bytes": 0, "is_downloaded": false, "expected_size_mb": 144, "path": null}
        """)

        XCTAssertNil(model.available, "absent means 'no opinion', which the row reads as available")
        XCTAssertNil(model.unavailableReason)
        XCTAssertNil(model.downloadState)
    }
}
