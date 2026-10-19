@testable import Fichero
import Testing

/// `source.recipe.download-failure-waits` (#5352): the run summary's `download_failed` rows become Retry and the
/// step's next candidate; the engine's `download_failures` words and orders them.
@MainActor
struct DownloadFailedSummaryTests {
    private let row: [String: Any] = [
        "steps": ["read"], "model": "es-hand", "reason": "connection lost", "retry_job_id": "dl1",
        "next_candidate": ["id": "mlx-qwen", "model": ["name": "qwen"], "runs_on": "this-mac", "needs_permission": false],
    ]

    @Test func aFailedDownloadReadsAsRetryAndTheNextCandidate() throws {
        let rows = ActivityDetails.downloadFailures([row])
        let first = try #require(rows.first)
        #expect(first.retryJobId == "dl1" && first.steps == ["read"])
        #expect(first.text == "es-hand did not download: connection lost")
        #expect(first.next == .init(card: "mlx-qwen", name: "qwen", needsPermission: false))
    }

    @Test func aCloudCandidateKeepsItsNeedForPermission() {
        var cloud = row
        cloud["next_candidate"] = ["id": "claude-vision", "needs_permission": true] as [String: Any]
        #expect(ActivityDetails.downloadFailures([cloud]).first?.next
                == .init(card: "claude-vision", name: "claude-vision", needsPermission: true))
    }

    @Test func noOtherCandidateStillOffersRetry() {
        var last = row
        last["next_candidate"] = nil
        let rows = ActivityDetails.downloadFailures([last])
        #expect(rows.count == 1 && rows[0].next == nil)
    }

    @Test func aRowWithoutAStepOrARetryJobIsDropped() {
        var noJob = row
        noJob["retry_job_id"] = nil
        var noSteps = row
        noSteps["steps"] = [String]()
        #expect(ActivityDetails.downloadFailures([noJob, noSteps]).isEmpty)
    }
}
