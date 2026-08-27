@testable import Fichero
import Foundation
import XCTest

/// Tests for the Run model — workflow execution record. Locks the
/// RunStatus table (5 cases × displayName/icon/color/isTerminal),
/// snake_case decode (Python parity), Run helpers (duration,
/// progressPercent, costFormatted, canRetry).
final class RunModelTests: XCTestCase {

    // MARK: - RunStatus enum

    func testRunStatusRawValuesStable() {
        // Source-of-truth strings — must match Python RunStatus.
        XCTAssertEqual(RunStatus.queued.rawValue, "queued")
        XCTAssertEqual(RunStatus.running.rawValue, "running")
        XCTAssertEqual(RunStatus.completed.rawValue, "completed")
        XCTAssertEqual(RunStatus.failed.rawValue, "failed")
        XCTAssertEqual(RunStatus.cancelled.rawValue, "cancelled")
    }

    func testRunStatusAllCasesCount() {
        XCTAssertEqual(RunStatus.allCases.count, 5)
    }

    func testRunStatusDisplayName() {
        let pairs: [(RunStatus, String)] = [
            (.queued, "Queued"), (.running, "Running"),
            (.completed, "Completed"), (.failed, "Failed"),
            (.cancelled, "Cancelled")
        ]
        for (status, name) in pairs {
            XCTAssertEqual(status.displayName, name)
        }
    }

    func testRunStatusIcon() {
        let pairs: [(RunStatus, String)] = [
            (.queued, "clock"),
            (.running, "arrow.triangle.2.circlepath"),
            (.completed, "checkmark.circle"),
            (.failed, "exclamationmark.triangle"),
            (.cancelled, "xmark.circle")
        ]
        for (status, icon) in pairs {
            XCTAssertEqual(status.icon, icon, "status=\(status)")
        }
    }

    func testRunStatusColor() {
        let pairs: [(RunStatus, String)] = [
            (.queued, "gray"), (.running, "blue"),
            (.completed, "green"), (.failed, "red"),
            (.cancelled, "orange")
        ]
        for (status, color) in pairs {
            XCTAssertEqual(status.color, color, "status=\(status)")
        }
    }

    func testRunStatusIsTerminal() {
        XCTAssertTrue(RunStatus.completed.isTerminal)
        XCTAssertTrue(RunStatus.failed.isTerminal)
        XCTAssertTrue(RunStatus.cancelled.isTerminal)
        XCTAssertFalse(RunStatus.queued.isTerminal)
        XCTAssertFalse(RunStatus.running.isTerminal)
    }

    // MARK: - Run init defaults

    func testRunInitDefaults() {
        let r = Run(workflowId: "wf-1")
        XCTAssertFalse(r.id.isEmpty)
        XCTAssertTrue(r.documentIds.isEmpty)
        XCTAssertEqual(r.priority, 0)
        XCTAssertEqual(r.status, .queued)
        XCTAssertEqual(r.progress, 0.0)
        XCTAssertEqual(r.attempt, 1)
        XCTAssertEqual(r.maxAttempts, 3)
        XCTAssertNil(r.error)
        XCTAssertTrue(r.artifactIds.isEmpty)
        XCTAssertEqual(r.tokensUsed, 0)
        XCTAssertEqual(r.costUsd, 0.0)
    }

    // MARK: - Snake_case decode

    func testRunDecodesSnakeCase() throws {
        let json = """
        {
            "id": "r-1",
            "workflow_id": "wf-1",
            "document_ids": ["d-1", "d-2"],
            "priority": 5,
            "status": "running",
            "current_step": "extract",
            "progress": 0.4,
            "attempt": 2,
            "max_attempts": 5,
            "error": null,
            "artifact_ids": ["a-1"],
            "tokens_used": 1200,
            "cost_usd": 0.05,
            "config": {},
            "queued_at": "2026-05-11T08:00:00Z",
            "started_at": "2026-05-11T08:00:05Z",
            "completed_at": null
        }
        """.data(using: .utf8)!
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let run = try decoder.decode(Run.self, from: json)
        XCTAssertEqual(run.workflowId, "wf-1")
        XCTAssertEqual(run.documentIds, ["d-1", "d-2"])
        XCTAssertEqual(run.currentStep, "extract")
        XCTAssertEqual(run.maxAttempts, 5)
        XCTAssertEqual(run.tokensUsed, 1200)
        XCTAssertEqual(run.costUsd, 0.05)
        XCTAssertNil(run.completedAt)
    }

    // MARK: - duration

    func testDurationWhileRunning() {
        // No completedAt → uses now(). Just verify non-nil + positive.
        let now = Date()
        let r = makeRun(startedAt: now.addingTimeInterval(-5), completedAt: nil)
        XCTAssertNotNil(r.duration)
        XCTAssertGreaterThan(r.duration ?? 0, 0)
    }

    func testDurationCompleted() {
        let start = Date(timeIntervalSince1970: 0)
        let end = Date(timeIntervalSince1970: 30)
        let r = makeRun(startedAt: start, completedAt: end)
        XCTAssertEqual(r.duration, 30)
    }

    func testDurationNilWhenNotStarted() {
        let r = makeRun(startedAt: nil)
        XCTAssertNil(r.duration)
    }

    // MARK: - durationString

    func testDurationStringNilWhenNotStarted() {
        XCTAssertNil(makeRun(startedAt: nil).durationString)
    }

    func testDurationStringNonNilWhenStarted() {
        // Formatter produces locale-sensitive output; assert non-nil + non-empty.
        let r = makeRun(
            startedAt: Date(timeIntervalSince1970: 0),
            completedAt: Date(timeIntervalSince1970: 65)
        )
        let str = r.durationString
        XCTAssertNotNil(str)
        XCTAssertFalse(str?.isEmpty ?? true)
    }

    // MARK: - progressPercent

    func testProgressPercentRounding() {
        XCTAssertEqual(makeRun(progress: 0.0).progressPercent, 0)
        XCTAssertEqual(makeRun(progress: 0.5).progressPercent, 50)
        XCTAssertEqual(makeRun(progress: 0.999).progressPercent, 99)
        XCTAssertEqual(makeRun(progress: 1.0).progressPercent, 100)
    }

    // MARK: - costFormatted

    func testCostFormattedFourDecimals() {
        XCTAssertEqual(makeRun(costUsd: 0.001).costFormatted, "$0.0010")
        XCTAssertEqual(makeRun(costUsd: 2.5).costFormatted, "$2.5000")
        XCTAssertEqual(makeRun(costUsd: 0).costFormatted, "$0.0000")
    }

    // MARK: - canRetry

    func testCanRetryFailedWithAttemptsRemaining() {
        XCTAssertTrue(makeRun(status: .failed, attempt: 1, maxAttempts: 3).canRetry)
    }

    func testCanRetryFalseAtMaxAttempts() {
        XCTAssertFalse(makeRun(status: .failed, attempt: 3, maxAttempts: 3).canRetry)
    }

    func testCanRetryFalseForNonFailedStatus() {
        for status in [RunStatus.queued, .running, .completed, .cancelled] {
            XCTAssertFalse(
                makeRun(status: status, attempt: 1, maxAttempts: 3).canRetry,
                "status=\(status)"
            )
        }
    }

    // MARK: - Helpers

    private func makeRun(
        status: RunStatus = .queued,
        attempt: Int = 1,
        maxAttempts: Int = 3,
        progress: Double = 0.0,
        costUsd: Double = 0.0,
        startedAt: Date? = nil,
        completedAt: Date? = nil
    ) -> Run {
        Run(
            workflowId: "wf-1",
            status: status,
            progress: progress,
            attempt: attempt,
            maxAttempts: maxAttempts,
            costUsd: costUsd,
            startedAt: startedAt,
            completedAt: completedAt
        )
    }
}
