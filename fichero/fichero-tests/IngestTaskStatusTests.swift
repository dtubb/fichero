@testable import Fichero
import Foundation
import Testing

// The derived reads behind #4203's progress UI. Daniel's complaint was that a
// folder drop shows nothing: no library, no count, no rate, no failures, no way
// to stop it. These are the rules the UI renders from, tested without a network.
@Suite("IngestTaskStatus — what the progress UI reads (#4203)")
struct IngestTaskStatusTests {

    private func status(
        _ state: String = "running",
        total: Int? = 100,
        processed: Int? = 10,
        failed: Int = 0,
        failures: [IngestFailure] = [],
        rate: Double = 0
    ) -> IngestTaskStatus {
        IngestTaskStatus(
            taskId: "t1",
            status: state,
            path: "/tmp/folder",
            progress: nil,
            total: total,
            processed: processed,
            error: nil,
            documentIds: [],
            failed: failed,
            failures: failures,
            filesPerSecond: rate
        )
    }

    // The walk hasn't finished counting yet. This is the exact moment Daniel
    // sees nothing at all, so the UI must say "Scanning…" rather than "0 of 0".
    @Test("total == 0 is scanning, not an empty import")
    func zeroTotalIsScanning() {
        #expect(status(total: 0, processed: 0).isScanning)
        #expect(status(total: nil, processed: 0).isScanning)
        #expect(status(total: 1, processed: 0).isScanning == false)
    }

    @Test("ETA divides the remaining files by the measured rate")
    func etaFromRate() {
        let eta = status(total: 100, processed: 20, rate: 4).estimatedSecondsRemaining
        #expect(eta == 20, "80 files left at 4/sec")
    }

    // Every case where an ETA would be a lie or a divide-by-zero.
    @Test("no ETA while scanning, without a rate, or when nothing is left")
    func etaWithheldWhenMeaningless() {
        #expect(status(total: 0, processed: 0, rate: 9).estimatedSecondsRemaining == nil, "scanning")
        #expect(status(total: 100, processed: 20, rate: 0).estimatedSecondsRemaining == nil, "no rate yet")
        #expect(status(total: 100, processed: 100, rate: 4).estimatedSecondsRemaining == nil, "done")
        #expect(
            status(total: 100, processed: 120, rate: 4).estimatedSecondsRemaining == nil,
            "processed past total must not produce a negative ETA"
        )
    }

    @Test("cancelling is distinct from cancelled, and only cancelled is terminal")
    func cancellingIsNotTerminal() {
        #expect(status("cancelling").isCancelling)
        #expect(status("cancelling").isFinished == false, "the file in flight still has to land")
        #expect(status("cancelled").isFinished)
        #expect(status("cancelled").isCancelling == false)
    }

    @Test("completed and failed are terminal; running is not")
    func terminalStates() {
        #expect(status("completed").isFinished)
        #expect(status("failed").isFinished)
        #expect(status("running").isFinished == false)
        #expect(status("pending").isFinished == false)
    }

    // Failures are surfaced, not swallowed — a per-file failure must not be
    // hidden behind a task that still reports "completed".
    @Test("per-file failures survive alongside a completed task")
    func failuresSurviveCompletion() {
        let failure = IngestFailure(path: "/tmp/a.pdf", error: "unreadable", documentId: "d1")
        let done = status("completed", total: 2, processed: 2, failed: 1, failures: [failure])
        #expect(done.isFinished)
        #expect(done.failed == 1)
        #expect(done.failures.first?.error == "unreadable")
    }

    // Two failures in one import must be separately identifiable or a List
    // renders one row for both.
    @Test("failures identify by document id, falling back to path")
    func failureIdentity() {
        let withId = IngestFailure(path: "/tmp/a.pdf", error: "x", documentId: "d1")
        let withoutId = IngestFailure(path: "/tmp/b.pdf", error: "x", documentId: nil)
        #expect(withId.id == "d1")
        #expect(withoutId.id == "/tmp/b.pdf")
        #expect(withId.id != withoutId.id)
    }
}
