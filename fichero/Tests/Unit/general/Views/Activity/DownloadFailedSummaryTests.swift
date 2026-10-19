@testable import Fichero
import FicheroAPIClient
import Testing

/// `source.recipe.download-failure-waits` (#5352): the run summary's typed `download_failed` rows become Retry and
/// the step's next candidate; the engine's `download_failures` words and orders them, and names the candidate.
@MainActor
struct DownloadFailedSummaryTests {
    private typealias Row = Components.Schemas.DownloadFailed
    private typealias Candidate = Components.Schemas.NextCandidate

    private func row(steps: [String] = ["read"], next: Candidate? = nil) -> Row {
        Row(steps: steps, model: "es-hand", reason: "connection lost", retryJobId: "dl1", nextCandidate: next)
    }

    private let local = Candidate(id: "mlx-qwen", name: "qwen", runsOn: "this-mac", needsPermission: false)

    @Test func aFailedDownloadReadsAsRetryAndTheNextCandidate() throws {
        let rows = ActivityDetails.downloadFailures([row(next: local)])
        let first = try #require(rows.first)
        #expect(first.retryJobId == "dl1" && first.steps == ["read"])
        #expect(first.text == "es-hand did not download: connection lost")
        #expect(first.next == .init(card: "mlx-qwen", name: "qwen", needsPermission: false))
    }

    @Test func aCloudCandidateKeepsItsNeedForPermission() {
        let cloud = Candidate(id: "claude-vision", name: "Claude Vision", runsOn: "cloud:anthropic", needsPermission: true)
        #expect(ActivityDetails.downloadFailures([row(next: cloud)]).first?.next
                == .init(card: "claude-vision", name: "Claude Vision", needsPermission: true))
    }

    @Test func noOtherCandidateStillOffersRetry() {
        let rows = ActivityDetails.downloadFailures([row()])
        #expect(rows.count == 1 && rows[0].next == nil)
    }

    @Test func aRowWithoutAStepIsDropped() {
        #expect(ActivityDetails.downloadFailures([row(steps: [])]).isEmpty)
    }
}
