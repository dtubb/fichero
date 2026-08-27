#if canImport(AppKit)
@testable import Fichero
import Foundation
import XCTest

/// #4291: ⌘Q beachballed because the whole engine teardown ran on the main
/// thread inside `applicationWillTerminate` — SIGTERM, then a `Thread.sleep`
/// poll loop of up to 5s (plus 1s after SIGKILL). Quit is now accepted with
/// `.terminateLater` and the teardown runs off-main under a hard deadline.
///
/// `TerminationDeadlinePolicy` is the pure decision at the centre of that loop,
/// so the deadline edge, the already-exited child, the escalation order, and a
/// clock that reads zero or backwards are all pinned here without spawning a
/// subprocess.
final class TerminationDeadlineTests: XCTestCase {

    private let policy = TerminationDeadlinePolicy(
        gracefulDeadline: 2,
        killGrace: 0.5,
        pollInterval: 0.05
    )

    // MARK: - Deadline boundary

    func testWaitsWhileInsideTheGracefulWindow() {
        XCTAssertEqual(
            policy.action(elapsed: 1.9, childHasExited: false, hasEscalated: false),
            .waitMore
        )
    }

    func testEscalatesExactlyAtTheGracefulDeadline() {
        // The boundary is inclusive: at 2.0s the graceful window is spent.
        XCTAssertEqual(
            policy.action(elapsed: 2.0, childHasExited: false, hasEscalated: false),
            .escalateToSIGKILL
        )
    }

    func testEscalatesPastTheGracefulDeadline() {
        XCTAssertEqual(
            policy.action(elapsed: 30, childHasExited: false, hasEscalated: false),
            .escalateToSIGKILL
        )
    }

    // MARK: - Already-exited child

    func testExitedChildRepliesImmediatelyBeforeTheDeadline() {
        XCTAssertEqual(
            policy.action(elapsed: 0, childHasExited: true, hasEscalated: false),
            .replyNow
        )
    }

    func testExitedChildRepliesEvenPastTheDeadline() {
        // A dead child never escalates — nothing to signal.
        XCTAssertEqual(
            policy.action(elapsed: 99, childHasExited: true, hasEscalated: false),
            .replyNow
        )
    }

    func testExitedChildAfterEscalationReplies() {
        XCTAssertEqual(
            policy.action(elapsed: 2.1, childHasExited: true, hasEscalated: true),
            .replyNow
        )
    }

    // MARK: - Escalation order

    func testEscalatesAtMostOnceThenWaitsOutTheKillGrace() {
        // Post-SIGKILL the policy must NOT ask for another SIGKILL; it polls
        // until the kill grace is spent.
        XCTAssertEqual(
            policy.action(elapsed: 2.2, childHasExited: false, hasEscalated: true),
            .waitMore
        )
    }

    func testRepliesWhenKillGraceIsSpentEvenIfChildStillAlive() {
        // 2.0 + 0.5 = 2.5s total ceiling. Past it we stop caring: the engine's
        // FICHERO_PARENT_PID watchdog backstops the straggler.
        XCTAssertEqual(
            policy.action(elapsed: 2.5, childHasExited: false, hasEscalated: true),
            .replyNow
        )
        XCTAssertEqual(
            policy.action(elapsed: 10, childHasExited: false, hasEscalated: true),
            .replyNow
        )
    }

    func testTotalDeadlineIsGracePlusKillGrace() {
        XCTAssertEqual(policy.totalDeadline, 2.5, accuracy: 0.0001)
    }

    /// Walks the exact sequence the teardown loop sees for a stubborn child:
    /// wait → wait → escalate → wait → reply. Guards the ORDER, not just the
    /// individual verdicts (a policy that replied before escalating would leave
    /// the engine unkilled).
    func testFullEscalationSequenceForAStubbornChild() {
        var actions: [TerminationDeadlinePolicy.Action] = []
        var hasEscalated = false
        for elapsed in [0.0, 1.0, 2.0, 2.3, 2.6] {
            let action = policy.action(
                elapsed: elapsed,
                childHasExited: false,
                hasEscalated: hasEscalated
            )
            if action == .escalateToSIGKILL { hasEscalated = true }
            actions.append(action)
        }
        XCTAssertEqual(actions, [.waitMore, .waitMore, .escalateToSIGKILL, .waitMore, .replyNow])
    }

    // MARK: - Clock edge cases

    func testZeroElapsedWaits() {
        XCTAssertEqual(
            policy.action(elapsed: 0, childHasExited: false, hasEscalated: false),
            .waitMore
        )
    }

    func testNegativeElapsedClampsToJustStartedRatherThanOverdue() {
        // A clock that goes backwards must never read as "deadline exceeded".
        XCTAssertEqual(
            policy.action(elapsed: -5, childHasExited: false, hasEscalated: false),
            .waitMore
        )
        XCTAssertEqual(
            policy.action(elapsed: -5, childHasExited: false, hasEscalated: true),
            .waitMore
        )
    }

    func testNegativeDurationsClampToZeroSoTeardownEscalatesImmediately() {
        let degenerate = TerminationDeadlinePolicy(
            gracefulDeadline: -1,
            killGrace: -1,
            pollInterval: -1
        )
        XCTAssertEqual(degenerate.gracefulDeadline, 0)
        XCTAssertEqual(degenerate.killGrace, 0)
        XCTAssertEqual(degenerate.pollInterval, 0)
        XCTAssertEqual(
            degenerate.action(elapsed: 0, childHasExited: false, hasEscalated: false),
            .escalateToSIGKILL
        )
        XCTAssertEqual(
            degenerate.action(elapsed: 0, childHasExited: false, hasEscalated: true),
            .replyNow
        )
    }

    func testZeroKillGraceRepliesRightAfterEscalating() {
        let noGrace = TerminationDeadlinePolicy(gracefulDeadline: 2, killGrace: 0, pollInterval: 0.05)
        XCTAssertEqual(
            noGrace.action(elapsed: 2, childHasExited: false, hasEscalated: false),
            .escalateToSIGKILL
        )
        XCTAssertEqual(
            noGrace.action(elapsed: 2, childHasExited: false, hasEscalated: true),
            .replyNow
        )
    }

    // MARK: - Quit budget

    /// Pins the quit budget the app actually ships. If someone widens this back
    /// toward the old 5s+1s, ⌘Q gets slow again — this fails first.
    func testQuitPolicyBudgetIsShort() {
        XCTAssertEqual(TerminationDeadlinePolicy.quit.gracefulDeadline, 2, accuracy: 0.0001)
        XCTAssertEqual(TerminationDeadlinePolicy.quit.killGrace, 0.5, accuracy: 0.0001)
        XCTAssertLessThanOrEqual(TerminationDeadlinePolicy.quit.totalDeadline, 3)
        XCTAssertGreaterThan(TerminationDeadlinePolicy.quit.pollInterval, 0)
    }

    // MARK: - Reap loop

    /// The real reap loop against a child that is already gone: it must return
    /// promptly (no sleeping out the deadline) and must not hang.
    func testReapChildReturnsImmediatelyForAnAlreadyDeadChild() async {
        // A pid we can never signal — `kill(pid, 0)` fails, so the policy sees
        // `childHasExited` on the first turn.
        let deadPID = pid_t(Int32.max)
        let start = Date()
        await EmbeddedBackendService.reapChild(pid: deadPID, policy: .quit)
        XCTAssertLessThan(Date().timeIntervalSince(start), 1.0)
        XCTAssertTrue(EmbeddedBackendService.childHasExited(pid: deadPID))
    }

    /// `stopAndAwaitExit` with no tracked child is a no-op that still parks the
    /// observable status at `.stopped` — the quit path must never wait on a
    /// service that never spawned anything.
    @MainActor
    func testStopAndAwaitExitWithNoTrackedChildIsImmediate() async {
        let service = EmbeddedBackendService()
        service.status = .running
        let start = Date()
        await service.stopAndAwaitExit()
        XCTAssertEqual(service.status, .stopped)
        XCTAssertLessThan(Date().timeIntervalSince(start), 1.0)
    }
}
#endif
