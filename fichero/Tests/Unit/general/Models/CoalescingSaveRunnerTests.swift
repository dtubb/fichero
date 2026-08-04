@testable import Fichero
import XCTest

/// Behavioural race tests for `CoalescingSaveRunner` — the serial+coalescing
/// runner behind ArtifactPanel autosave (#2536, a data-loss race).
///
/// These exercise the real coalescing logic (not a string-match): each test
/// drives an edit that lands *during* an in-flight save and asserts the trailing
/// edit reaches "disk". They FAIL against the old drop-on-`isSaving` behaviour
/// and PASS with the coalescing fix.
@MainActor
final class CoalescingSaveRunnerTests: XCTestCase {

    /// THE regression: an edit + flush arriving while a save is in flight must
    /// be persisted, not dropped.
    func testTrailingEditDuringInFlightSaveIsPersisted() async {
        let runner = CoalescingSaveRunner()
        var draft = "v1"
        var persisted: [String] = []

        // Hold the first save in flight until the test releases it.
        var release: CheckedContinuation<Void, Never>?
        let reachedInFlight = expectation(description: "first save is in flight")

        let firstSave = Task { @MainActor in
            await runner.run {
                persisted.append(draft)               // persists the draft as it is NOW
                if persisted.count == 1 {
                    await withCheckedContinuation { cont in
                        release = cont
                        reachedInFlight.fulfill()
                    }
                }
            }
        }
        await fulfillment(of: [reachedInFlight], timeout: 2)
        XCTAssertTrue(runner.isSaving, "a save should be in flight")

        // Edit lands DURING the in-flight save, then a flush fires.
        draft = "v2"
        let flush = Task { @MainActor in await runner.run { persisted.append(draft) } }
        await Task.yield()   // let the flush coalesce (set pending) before release

        release?.resume()
        await firstSave.value
        await flush.value

        // Coalescing re-ran the work, re-reading draft → "v2" is persisted last.
        // Under the old drop bug this would be just ["v1"].
        XCTAssertEqual(persisted, ["v1", "v2"])
        XCTAssertFalse(runner.isSaving)
    }

    /// Edge: several rapid edits during one in-flight save collapse to a single
    /// coalesced re-save of the LATEST draft — none lost, no redundant storm.
    func testMultipleRapidEditsCoalesceToLatest() async {
        let runner = CoalescingSaveRunner()
        var draft = "0"
        var persisted: [String] = []

        var release: CheckedContinuation<Void, Never>?
        let reachedInFlight = expectation(description: "first save is in flight")

        let firstSave = Task { @MainActor in
            await runner.run {
                persisted.append(draft)
                if persisted.count == 1 {
                    await withCheckedContinuation { cont in
                        release = cont
                        reachedInFlight.fulfill()
                    }
                }
            }
        }
        await fulfillment(of: [reachedInFlight], timeout: 2)

        // Five rapid edits + flushes while the first save is still in flight.
        var flushes: [Task<Void, Never>] = []
        for index in 1...5 {
            draft = "\(index)"
            flushes.append(Task { @MainActor in await runner.run { persisted.append(draft) } })
            await Task.yield()
        }

        release?.resume()
        await firstSave.value
        for flush in flushes { await flush.value }

        // Exactly one coalesced re-save runs after the in-flight one, persisting
        // the latest draft. The trailing edit ("5") is never lost.
        XCTAssertEqual(persisted, ["0", "5"])
        XCTAssertFalse(runner.isSaving)
    }

    /// The loop must terminate: a no-op `work` (nothing changed) runs once and
    /// the runner goes idle — no infinite re-save.
    func testIdleWorkRunsOnceAndTerminates() async {
        let runner = CoalescingSaveRunner()
        var count = 0
        await runner.run { count += 1 }
        XCTAssertEqual(count, 1)
        XCTAssertFalse(runner.isSaving)
    }

    /// `isSaving` reflects the in-flight state for the UI spinner.
    func testIsSavingTrueDuringRunFalseAfter() async {
        let runner = CoalescingSaveRunner()
        var release: CheckedContinuation<Void, Never>?
        let reached = expectation(description: "in flight")

        let task = Task { @MainActor in
            await runner.run {
                await withCheckedContinuation { cont in
                    release = cont
                    reached.fulfill()
                }
            }
        }
        await fulfillment(of: [reached], timeout: 2)
        XCTAssertTrue(runner.isSaving)
        release?.resume()
        await task.value
        XCTAssertFalse(runner.isSaving)
    }
}
