@testable import Fichero
import XCTest

/// Pure-function coverage for `ActivityViewHelpers` — the status mappings and
/// duration formatter that back the Activity views. No network / SwiftUI needed:
/// every function here is a deterministic `static`. Guards the boundary logic in
/// `formatDuration` and the backend-spelling vocabulary in
/// `selectedRunStatus(forRaw:)` against silent regressions.
final class ActivityViewHelpersTests: XCTestCase {

    // MARK: - selectedRunStatus(forRaw:)

    func testRawStatusMapsKnownSpellings() {
        let map: [String: SelectedActivityRun.ActivityRunStatusType] = [
            "paused": .paused,
            "completed": .completed,
            "complete": .completed,
            "success": .completed,
            "succeeded": .completed,
            "failed": .failed,
            "error": .failed,
            "cancelled": .cancelled,
            "canceled": .cancelled
        ]
        for (raw, expected) in map {
            XCTAssertEqual(ActivityViewHelpers.selectedRunStatus(forRaw: raw), expected, "raw=\(raw)")
        }
    }

    func testRawStatusIsCaseInsensitive() {
        XCTAssertEqual(ActivityViewHelpers.selectedRunStatus(forRaw: "COMPLETED"), .completed)
        XCTAssertEqual(ActivityViewHelpers.selectedRunStatus(forRaw: "Error"), .failed)
        XCTAssertEqual(ActivityViewHelpers.selectedRunStatus(forRaw: "CanceLLed"), .cancelled)
    }

    func testRawStatusUnknownAndEmptyDefaultToRunning() {
        XCTAssertEqual(ActivityViewHelpers.selectedRunStatus(forRaw: ""), .running)
        XCTAssertEqual(ActivityViewHelpers.selectedRunStatus(forRaw: "queued"), .running)
        XCTAssertEqual(ActivityViewHelpers.selectedRunStatus(forRaw: "running"), .running)
        XCTAssertEqual(ActivityViewHelpers.selectedRunStatus(forRaw: "pending"), .running)
    }

    // MARK: - selectedRunStatus(for: WorkflowStatus)

    func testWorkflowStatusMapping() {
        XCTAssertEqual(ActivityViewHelpers.selectedRunStatus(for: .running), .running)
        // `idle` collapses to running (a run that exists but hasn't reported yet).
        XCTAssertEqual(ActivityViewHelpers.selectedRunStatus(for: .idle), .running)
        XCTAssertEqual(ActivityViewHelpers.selectedRunStatus(for: .paused), .paused)
        XCTAssertEqual(ActivityViewHelpers.selectedRunStatus(for: .completed), .completed)
        XCTAssertEqual(ActivityViewHelpers.selectedRunStatus(for: .failed), .failed)
    }

    // MARK: - selectedRunStatus(selectedRun:liveExecution:persistedRun:) precedence

    func testSelectedRunStatusPrefersFallbackToSelectedRun() {
        // With no live execution and no persisted run, it echoes the selected run.
        let run = SelectedActivityRun(
            id: "r1",
            name: "Run",
            workflowId: nil,
            threadId: nil,
            timestamp: Date(timeIntervalSince1970: 0),
            status: .paused,
            isLive: false,
            childType: nil
        )
        let resolved = ActivityViewHelpers.selectedRunStatus(
            selectedRun: run,
            liveExecution: nil,
            persistedRun: nil
        )
        XCTAssertEqual(resolved, .paused)
    }

    // MARK: - statusIcon / statusColor / statusText are total (every case mapped)

    func testStatusHelpersCoverEveryCase() {
        let all: [SelectedActivityRun.ActivityRunStatusType] =
            [.running, .paused, .completed, .failed, .cancelled]
        for status in all {
            XCTAssertFalse(ActivityViewHelpers.statusIcon(for: status).isEmpty, "icon \(status)")
            XCTAssertFalse(ActivityViewHelpers.statusText(for: status).isEmpty, "text \(status)")
        }
        // Spot-check the specific mappings that views depend on.
        XCTAssertEqual(ActivityViewHelpers.statusIcon(for: .completed), "checkmark.circle.fill")
        XCTAssertEqual(ActivityViewHelpers.statusIcon(for: .failed), "xmark.circle.fill")
        XCTAssertEqual(ActivityViewHelpers.statusText(for: .running), "Running")
        XCTAssertEqual(ActivityViewHelpers.statusText(for: .cancelled), "Cancelled")
    }

    // MARK: - levelColor default branch

    func testLevelColorDefaultsForUnknownLevel() {
        // Known levels don't crash; unknown falls to the default (.primary).
        XCTAssertEqual(ActivityViewHelpers.levelColor("error"), .red)
        XCTAssertEqual(ActivityViewHelpers.levelColor("warning"), .orange)
        XCTAssertEqual(ActivityViewHelpers.levelColor("info"), .blue)
        XCTAssertEqual(ActivityViewHelpers.levelColor("trace"), .primary)
        XCTAssertEqual(ActivityViewHelpers.levelColor(""), .primary)
    }

    // MARK: - formatDuration boundaries

    func testFormatDurationMilliseconds() {
        XCTAssertEqual(ActivityViewHelpers.formatDuration(0), "0ms")
        XCTAssertEqual(ActivityViewHelpers.formatDuration(1), "1ms")
        XCTAssertEqual(ActivityViewHelpers.formatDuration(999), "999ms")
    }

    func testFormatDurationSecondsBoundary() {
        // Exactly 1000ms crosses into the seconds format.
        XCTAssertEqual(ActivityViewHelpers.formatDuration(1000), "1.0s")
        XCTAssertEqual(ActivityViewHelpers.formatDuration(1500), "1.5s")
        XCTAssertEqual(ActivityViewHelpers.formatDuration(59999), "60.0s")
    }

    func testFormatDurationMinutesBoundary() {
        // Exactly 60000ms crosses into the minutes+seconds format.
        XCTAssertEqual(ActivityViewHelpers.formatDuration(60000), "1m 0s")
        XCTAssertEqual(ActivityViewHelpers.formatDuration(90000), "1m 30s")
        XCTAssertEqual(ActivityViewHelpers.formatDuration(3_661_000), "61m 1s")
    }
}
