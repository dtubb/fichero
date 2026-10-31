import Foundation

/// The pure deadline/escalation decision for shutting the engine child down
/// (#4291). Quit must feel instant, so the teardown is bounded by a short clock
/// rather than by however long the engine feels like taking: SIGTERM, wait a
/// couple of seconds, SIGKILL, then stop caring. Waiting longer buys nothing —
/// the engine's own `FICHERO_PARENT_PID` watchdog self-terminates any child that
/// outlives the app, so an unreaped straggler is not an orphan.
///
/// Pure and clock-injected so every boundary (deadline edge, already-exited
/// child, escalation order, a clock that goes backwards) is unit-testable
/// without a real subprocess — `TerminationDeadlineTests`.
struct TerminationDeadlinePolicy: Equatable {
    /// What the teardown loop should do next.
    enum Action: Equatable {
        /// The child may still exit on its own — sleep `pollInterval` and re-ask.
        case waitMore
        /// The graceful window is spent: SIGKILL the child, then keep polling
        /// (bounded by `killGrace`) so the common case still reports a reap.
        case escalateToSIGKILL
        /// Stop waiting and let the app finish terminating.
        case replyNow
    }

    /// How long the child gets to honour SIGTERM before we escalate.
    let gracefulDeadline: TimeInterval
    /// How long we keep polling after SIGKILL before replying regardless.
    let killGrace: TimeInterval
    /// Gap between liveness checks.
    let pollInterval: TimeInterval

    /// Negative inputs are meaningless as durations and would invert the
    /// comparisons below, so they clamp to zero (= escalate/reply immediately).
    init(gracefulDeadline: TimeInterval, killGrace: TimeInterval, pollInterval: TimeInterval) {
        self.gracefulDeadline = max(0, gracefulDeadline)
        self.killGrace = max(0, killGrace)
        self.pollInterval = max(0, pollInterval)
    }

    /// The quit-path budget: ~2s of grace, half a second to observe the kill.
    static let quit = TerminationDeadlinePolicy(gracefulDeadline: 2, killGrace: 0.5, pollInterval: 0.05)

    /// The restart budget (`engine.restart-waits-for-the-work`, #6176): 30 s for the engine to stop by itself before a
    /// kill, so a restart never SIGKILLs a process still writing. A gone process ends the wait at once.
    static let restart = TerminationDeadlinePolicy(gracefulDeadline: 30, killGrace: 0.5, pollInterval: 0.25)

    /// Total wall-clock ceiling on a teardown — grace plus kill observation.
    var totalDeadline: TimeInterval { gracefulDeadline + killGrace }

    /// - Parameters:
    ///   - elapsed: seconds since SIGTERM was sent. Clamped at 0, so a
    ///     backwards/zero clock reads as "just started", never as "overdue".
    ///   - childHasExited: `kill(pid, 0) != 0` — the child is gone/reaped.
    ///   - hasEscalated: SIGKILL has already been sent for this teardown.
    func action(elapsed: TimeInterval, childHasExited: Bool, hasEscalated: Bool) -> Action {
        // A dead child ends the wait immediately, whatever the clock says.
        if childHasExited { return .replyNow }
        let waited = max(0, elapsed)
        if hasEscalated {
            return waited >= totalDeadline ? .replyNow : .waitMore
        }
        return waited >= gracefulDeadline ? .escalateToSIGKILL : .waitMore
    }
}
