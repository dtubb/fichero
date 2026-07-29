@testable import Fichero
import Foundation
import Testing

// The debounce rule behind #4203's headline complaint: "I drop a folder and the
// sidebar is not updated as things are brought in, but at the end."
//
// `ReloadDebouncer` was a pure trailing debounce — every event cancelled the
// pending flush and rescheduled it. An import committing 400-900 files/sec emits
// `document.created` every 1-2ms, far inside the 300ms window, so the flush
// could never win the race and the sidebar populated only once the import
// stopped. The maxWait ceiling is what makes a continuous stream flush anyway.
//
// These assert the RULE, not the timing: sleep-based debounce tests are flaky by
// construction, so the decision is a pure function and this suite calls it
// directly.
@Suite("ReloadDebouncer.wait — a burst cannot postpone forever (#4203)")
struct ReloadDebouncerWaitTests {

    private let delay = Duration.milliseconds(300)
    private let maxWait = Duration.seconds(1)

    @Test("a fresh burst waits the full trailing window")
    func freshBurstWaitsFullDelay() {
        let wait = ReloadDebouncer.wait(delay: delay, maxWait: maxWait, sinceBurstStart: .zero)
        #expect(wait == delay)
    }

    @Test("a young burst still coalesces — the #1973 behaviour is unchanged")
    func youngBurstStillCoalesces() {
        let wait = ReloadDebouncer.wait(
            delay: delay, maxWait: maxWait, sinceBurstStart: .milliseconds(100)
        )
        #expect(wait == delay, "quiet-burst coalescing must not regress")
    }

    // The starvation case: events keep arriving, so elapsed keeps growing. The
    // wait must shrink rather than staying at 300ms forever.
    @Test("the wait shrinks as the burst approaches the ceiling")
    func waitShrinksNearCeiling() {
        let wait = ReloadDebouncer.wait(
            delay: delay, maxWait: maxWait, sinceBurstStart: .milliseconds(900)
        )
        #expect(wait == .milliseconds(100))
        #expect(wait < delay)
    }

    @Test("at the ceiling the action fires immediately")
    func atCeilingFiresImmediately() {
        #expect(
            ReloadDebouncer.wait(delay: delay, maxWait: maxWait, sinceBurstStart: .seconds(1)) == .zero
        )
    }

    // A burst longer than maxWait must not produce a NEGATIVE sleep — that would
    // either trap or (worse) sleep for an enormous unsigned duration.
    @Test("past the ceiling the wait is clamped at zero, never negative")
    func pastCeilingClampsToZero() {
        let wait = ReloadDebouncer.wait(
            delay: delay, maxWait: maxWait, sinceBurstStart: .seconds(30)
        )
        #expect(wait == .zero)
        #expect(wait >= .zero)
    }

    // The rule must hold for the real event cadence, not just round numbers:
    // 926 files/sec is ~1.08ms between events, so elapsed grows continuously and
    // the wait must reach zero rather than resetting to 300ms each time.
    @Test("a 926 files/sec stream reaches a flush instead of being starved")
    func highThroughputStreamFlushes() {
        var elapsed = Duration.zero
        var flushes = 0
        // Simulate 2 seconds of continuous events at ~1ms apart.
        for _ in 0..<2000 {
            let wait = ReloadDebouncer.wait(delay: delay, maxWait: maxWait, sinceBurstStart: elapsed)
            if wait == .zero {
                flushes += 1
                elapsed = .zero          // the burst restarts when the action runs
            } else {
                elapsed += .milliseconds(1)
            }
        }
        #expect(flushes >= 1, "a continuous stream must flush, not starve")
        #expect(flushes <= 3, "but it must still coalesce — not one flush per event")
    }

    @Test("a zero maxWait degenerates to fire-immediately, not to negative waits")
    func zeroMaxWaitFiresImmediately() {
        let wait = ReloadDebouncer.wait(delay: delay, maxWait: .zero, sinceBurstStart: .zero)
        #expect(wait == .zero)
    }
}

// MARK: - Overdue flushes must not be rescheduled (#4203 follow-up)

/// The maxWait ceiling was computed correctly and then thrown away: `schedule`
/// cancelled the pending task on every event, and `Task.sleep` suspends even
/// for `.zero`, so under an import's 1-2ms event spacing the next event always
/// cancelled the flush before it resumed. Rows appeared only when the stream
/// stopped — the exact starvation maxWait exists to prevent, surviving the fix
/// and looking like batching.
///
/// These pin the rule the scheduler now consults. `wait(...)` alone could not
/// catch it: that function was always right; the bug was in what `schedule`
/// did with its answer.
@Suite("ReloadDebouncer overdue-flush rule")
struct ReloadDebouncerOverdueFlushTests {

    @Test("an overdue burst with a flush pending yields — the pending flush must run")
    func overdueWithPendingYields() {
        #expect(ReloadDebouncer.yieldsToPendingFlush(wait: .zero, hasPending: true))
    }

    @Test("an overdue burst with NO flush pending schedules one — otherwise nothing ever flushes")
    func overdueWithoutPendingSchedules() {
        #expect(!ReloadDebouncer.yieldsToPendingFlush(wait: .zero, hasPending: false))
    }

    @Test("a young burst always reschedules, which is what makes it a debounce")
    func youngBurstReschedules() {
        #expect(!ReloadDebouncer.yieldsToPendingFlush(wait: .milliseconds(300), hasPending: true))
        #expect(!ReloadDebouncer.yieldsToPendingFlush(wait: .milliseconds(1), hasPending: true))
    }

    @Test("the rule composes with wait(): a burst past maxWait yields to its pending flush")
    func composesWithWait() {
        // 1.5s into a burst with a 1s ceiling: overdue.
        let overdue = ReloadDebouncer.wait(
            delay: .milliseconds(300), maxWait: .seconds(1), sinceBurstStart: .milliseconds(1500)
        )
        #expect(overdue == .zero)
        #expect(ReloadDebouncer.yieldsToPendingFlush(wait: overdue, hasPending: true))

        // 100ms in: still inside the window, still debouncing.
        let young = ReloadDebouncer.wait(
            delay: .milliseconds(300), maxWait: .seconds(1), sinceBurstStart: .milliseconds(100)
        )
        #expect(young == .milliseconds(300))
        #expect(!ReloadDebouncer.yieldsToPendingFlush(wait: young, hasPending: true))
    }
}
