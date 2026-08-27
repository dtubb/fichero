@testable import Fichero
import Foundation
import Testing

// The derived reads behind #4203's progress UI. The reported problem was that a
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

    // The walk hasn't finished counting yet. This is the exact moment the user
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

// The duration text the progress UI renders. Coarse by design: an ETA derived
// from a rate that swings with file size is an estimate, and rendering it to the
// second would overstate what we know (#4203).
@Suite("IngestProgressView.durationText (#4203)")
struct IngestDurationTextTests {

    @Test("seconds under a minute")
    func secondsGranularity() {
        #expect(IngestProgressView.durationText(5) == "5s")
        #expect(IngestProgressView.durationText(59) == "59s")
    }

    @Test("minutes up to an hour")
    func minutesGranularity() {
        #expect(IngestProgressView.durationText(60) == "1m")
        #expect(IngestProgressView.durationText(90) == "2m", "rounds to nearest")
        #expect(IngestProgressView.durationText(3599) == "60m")
    }

    @Test("hours for a long import")
    func hoursGranularity() {
        #expect(IngestProgressView.durationText(3600) == "1.0h")
        #expect(IngestProgressView.durationText(9000) == "2.5h")
    }

    // A 100k-file import at a slow rate produces a very large ETA; it must
    // still render as text rather than overflowing or showing a raw double.
    @Test("a very long ETA still renders")
    func longEtaRenders() {
        let text = IngestProgressView.durationText(500_000)
        #expect(text.hasSuffix("h"))
        #expect(text.count < 12)
    }

    @Test("zero and sub-second collapse to 0s, never a negative")
    func zeroIsStable() {
        #expect(IngestProgressView.durationText(0) == "0s")
        #expect(IngestProgressView.durationText(0.4) == "0s")
    }
}

// Republish discipline (#4203). The poll loop writes `activeIngest` twice a
// second for the whole import; observers must invalidate only when a number
// actually moved, or every progress surface re-renders 2x/sec for the duration.
@Suite("IngestTaskStatus equality gates republishing (#4203)")
struct IngestStatusEqualityTests {

    private func status(processed: Int, rate: Double = 2, failures: [IngestFailure] = []) -> IngestTaskStatus {
        IngestTaskStatus(
            taskId: "t1", status: "running", path: "/tmp/f", progress: nil,
            total: 100, processed: processed, error: nil, documentIds: [],
            failed: failures.count, failures: failures, filesPerSecond: rate
        )
    }

    @Test("two identical polls compare equal, so nothing republishes")
    func identicalPollsAreEqual() {
        #expect(status(processed: 10) == status(processed: 10))
    }

    @Test("a moved count compares unequal, so the UI updates")
    func movedCountIsUnequal() {
        #expect(status(processed: 10) != status(processed: 11))
    }

    // The rate moves even when the count doesn't; the ETA is derived from it, so
    // it has to count as a change or a stale ETA sticks on screen.
    @Test("a changed rate alone is still a change")
    func changedRateIsUnequal() {
        #expect(status(processed: 10, rate: 2) != status(processed: 10, rate: 5))
    }

    @Test("a new failure is a change even at the same processed count")
    func newFailureIsUnequal() {
        let failure = IngestFailure(path: "/tmp/a.pdf", error: "unreadable", documentId: "d1")
        #expect(status(processed: 10) != status(processed: 10, failures: [failure]))
    }
}
