import FicheroAPIClient
import Foundation
import Observation
import OSLog
import Security

private let logger = Logger(subsystem: "app.fichero.fichero", category: "EmbeddedBackend")

/// Debug-external readiness budget (#4056). The developer-run engine (Debug,
/// not bundled — #3042) can take longer than 5s to bind the UDS socket / HTTPS
/// listener and answer the authenticated probe, especially on a cold
/// `start_backend.sh` under a contended machine. 15s gives headroom without
/// loosening the Release/embedded budgets (see `spawnAndAdoptEmbeddedEngine`).
/// Pinned by `EmbeddedBackendDebugReadinessBudgetTests`.
private let debugExternalReadinessTimeout: TimeInterval = 15

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

extension EmbeddedBackendService {
    /// Whether a `connectBackend` trigger should ATTACH to the already-established
    /// app-level connection instead of re-running the connect+auth sequence
    /// (#3394/#3407). The main WindowGroup's `.task` fires once per window/tab, so
    /// without this every new window would flip the shared status back to
    /// `.starting` and re-probe/re-auth — the visible reconnect churn. True only
    /// when the backend is already connected AND this isn't an explicit Retry
    /// (`restart`), which must always re-run. Pure so window-lifecycle reuse is
    /// unit-testable without a live engine.
    static func shouldReuseExistingConnection(
        restart: Bool,
        status: BackendStatus,
        isBackendReady: Bool
    ) -> Bool {
        guard !restart, isBackendReady else { return false }
        if case .running = status { return true }
        return false
    }

    // MARK: - Lifecycle

    /// Start the embedded backend
    func start() async throws {
        // One spawn per host at a time (#3108): a retry fired while a start is
        // already in flight is a no-op, so N rapid retries never spawn a second
        // engine or race the first readiness probe.
        guard !isStarting else {
            logger.info("start() ignored — a start/retry is already in flight (#3108)")
            return
        }
        isStarting = true
        startAttemptsPassedGuard += 1
        defer { isStarting = false }

        // The provisioning mode is decided ONCE from explicit inputs (#3109) and
        // consumed here — no scattered #if DEBUG / usesCustomHost / preview
        // re-derivation. Loopback-only bind + pinned HTTPS are unchanged in every
        // mode (they live in launchEmbeddedBackend / the readiness probe).
        let strategy = EngineConfig.engineProvisioningStrategy()
        lastProvisioningStrategy = strategy
        lastTransportMode = EngineConfig.transportMode
        lastPortResolution = nil
        logger.info("Engine provisioning strategy: \(String(describing: strategy), privacy: .public) (#3109)")

        switch strategy {
        case .inert:
            await adoptInertHostForPreviewOrTest()
        case .configuredRemote, .iosCompanion:
            try await adoptConfiguredRemoteHost()
        #if os(macOS)
        case .debugExternal:
            try await adoptDebugExternalEngine()
        case .releaseEmbedded:
            try await spawnAndAdoptEmbeddedEngine()
        #else
        case .debugExternal, .releaseEmbedded:
            // iOS never runs a local engine; the strategy never yields these on
            // iOS, but the switch must stay exhaustive.
            status = .failed
            errorMessage = "No remote engine host configured. Set a custom host in Settings."
            throw BackendError.notRunning
        #endif
        }
    }

    /// `inert`: previews / XCTest host / UI-test. Adopt an external engine if
    /// one is up, else run with none — NEVER spawn or manage a lifecycle. The
    /// XCTest harness owns its own disposable engine; the host app must not
    /// launch the (often unbuilt) bundled engine nor terminate when it's missing.
    private func adoptInertHostForPreviewOrTest() async {
        expectedLaunchNonce = nil
        logger.info("Preview / playground / XCTest host / UI-test — connecting to external if up, else no-op")
        do {
            try await waitForBackend(timeout: 1.5)
            logger.info("Connected to external backend")
        } catch {
            logger.info("No external backend; host runs without managing one")
        }
        status = .running
    }

    /// `configuredRemote` / `iosCompanion`: connect to the explicit/paired host,
    /// never spawn a local engine. Throws on failure so `start()` surfaces the
    /// diagnosis instead of falling through to a local spawn.
    private func adoptConfiguredRemoteHost() async throws {
        expectedLaunchNonce = nil
        logger.info("Configured remote host: \(EngineConfig.host.absoluteString, privacy: .public)")
        do {
            try await waitForBackend(timeout: 5)
            status = .running
            logger.info("Connected to configured external backend")
        } catch {
            status = .failed
            errorMessage = error.localizedDescription
            logger.error("Configured external backend did not respond: \(error.localizedDescription, privacy: .public)")
            throw error
        }
    }

    #if os(macOS)
    /// `debugExternal`: the engine is deliberately NOT bundled in Debug (the
    /// embed phase is Release-only, #3042), so we NEVER spawn — adopt a
    /// developer-run engine on :8765. If nothing is up, fail with the actionable
    /// start_backend.sh message; the window renders the diagnosis + Retry and the
    /// app never terminates.
    private func adoptDebugExternalEngine() async throws {
        expectedLaunchNonce = nil
        // Log the ACTUAL transport the app will dial — a hardcoded ":8765" here
        // was misleading in UDS mode, where the client dials an AF_UNIX socket,
        // not TCP. Now the log names the exact socket path so a path mismatch is
        // obvious at a glance.
        let dialTarget: String
        if case let .uds(path) = EngineConfig.transportMode {
            dialTarget = "UDS socket \(path)"
        } else {
            dialTarget = "HTTPS :8765"
        }
        logger.info("DEBUG mode: adopting external engine over \(dialTarget, privacy: .public) (engine not bundled in Debug)")
        do {
            try await waitForBackend(timeout: debugExternalReadinessTimeout)
            if currentEngineOwnership == .ownedEmbedded {
                backendPID = await Self.ownedDebugEnginePID(transportMode: lastTransportMode ?? EngineConfig.transportMode)
            }
            status = .running
            let ownership = String(describing: currentEngineOwnership)
            logger.info("Connected to external backend over \(dialTarget, privacy: .public) (ownership: \(ownership, privacy: .public))")
        } catch {
            status = .failed
            // Distinguish "engine unreachable" from "engine reachable but rejected
            // our token" — the old message always said "isn't running", which is
            // false (and misleading) when the engine answered 401/403. lastReadiness
            // holds the final probe verdict.
            if lastReadiness == .authRejected {
                logger.error(
                    "Engine is reachable over \(dialTarget, privacy: .public) but rejected credentials — token/.api-key mismatch"
                )
                errorMessage = "The engine is running but rejected the app's credentials (401). "
                    + "The app's token doesn't match the engine's — this is an auth/.api-key "
                    + "mismatch, not a missing engine."
                throw BackendError.authenticationRequired
            }
            logger.error(
                "No external engine reachable over \(dialTarget, privacy: .public) in Debug — start it with start_backend.sh"
            )
            throw BackendError.backendAppNotFound
        }
    }

    /// `releaseEmbedded`: spawn the bundled engine, app-authoritative token
    /// (#2862). The ONLY strategy that spawns and manages a lifecycle.
    /// Briefcase-bundled engine cold-starts in ~25s on Apple Silicon (heavy ML
    /// imports + DB init); 90s gives margin on slower I/O and contended startup.
    private func spawnAndAdoptEmbeddedEngine() async throws {
        logger.info("Starting embedded backend...")
        status = .starting
        // Pre-flight the port (#2863). Sweep our own orphans, then if the port
        // is STILL held by a process we can't claim, ask the user (Stop it /
        // Use it / Quit) rather than silently adopting an engine that may
        // reject our token and leave a blank window.
        switch try await resolvePortConflict() {
        case .adoptExisting:
            lastPortResolution = .adoptExisting
            expectedLaunchNonce = nil
            // Adoption is gated on the authenticated probe: if the existing
            // engine rejects our token, waitForBackend throws and we surface
            // failure instead of a blank window.
            try await waitForBackend(timeout: 30)
            status = .running
            logger.info("Adopted user-approved existing engine on port 8765")
        case .spawnOurs:
            lastPortResolution = .spawnOurs
            try await launchEmbeddedBackend()
            // Bounded by the child, not a clock (#3930) — we spawned this engine,
            // so its liveness is knowable and a fixed budget is just the app
            // racing its own subprocess.
            try await waitForSpawnedBackend()
            // #3975: waitForSpawnedBackend already required an authenticated
            // /api/registry 200 (= token accepted), so the token is provably on
            // disk and working — the redundant waitForToken here was dead. Removed.
            status = .running
            logger.info("Embedded backend started successfully")
        }
    }
    #endif

    /// The non-blocking half of a stop: flip the observable state and ask the
    /// child to exit. Returns the pid we signalled, or nil when there is nothing
    /// to reap (external/user-managed engine, or we never spawned one).
    ///
    /// Split out of `stop()` for #4291 so the quit path can send SIGTERM on the
    /// main actor — cheap, no wait — and then do the reaping off-main.
    @discardableResult
    func beginStop() -> pid_t? {
        // Don't stop external backends (user-managed)
        if isExternalBackend {
            logger.info("Using external backend - leaving it running (user-managed)")
            status = .stopped
            return nil
        }

        guard let pid = backendPID else {
            logger.info("ℹ️  No embedded backend PID tracked (may not have launched yet or using external)")
            status = .stopped
            return nil
        }

        logger.info("Stopping embedded backend (PID: \(pid))...")

        // Mark intentional so the terminationHandler doesn't flip .failed.
        intentionalStop = true

        // Clear state immediately
        backendPID = nil
        status = .stopped

        // Graceful shutdown - send SIGTERM
        kill(pid, SIGTERM)
        return pid
    }

    /// Stop the embedded backend and wait — without blocking a thread — until the
    /// child is gone or the deadline is spent (#4291). This is the quit path and
    /// the respawn path: both need the port released before they continue, but
    /// neither may beachball the main thread doing it. The waits are
    /// `Task.sleep`, so the main run loop keeps servicing events throughout.
    func stopAndAwaitExit(policy: TerminationDeadlinePolicy = .quit) async {
        guard let pid = beginStop() else { return }
        await Self.reapChild(pid: pid, policy: policy)
    }

    /// Stop the embedded backend, bounded by `TerminationDeadlinePolicy.quit`.
    ///
    /// Kept synchronous for the Settings/Sharing restart callers that stop and
    /// immediately `start()` again — they need the port released before the
    /// respawn. It DOES block the caller for up to the policy's total deadline,
    /// so anything that can await should call `stopAndAwaitExit()` instead; the
    /// quit path does (#4291).
    func stop(policy: TerminationDeadlinePolicy = .quit) {
        guard let pid = beginStop() else { return }
        let start = Date()
        var hasEscalated = false
        while true {
            let action = policy.action(
                elapsed: Date().timeIntervalSince(start),
                childHasExited: Self.childHasExited(pid: pid),
                hasEscalated: hasEscalated
            )
            switch action {
            case .replyNow:
                Self.logTeardownOutcome(pid: pid, hasEscalated: hasEscalated)
                return
            case .escalateToSIGKILL:
                hasEscalated = true
                logger.warning("Backend didn't exit within \(policy.gracefulDeadline)s, force killing (PID: \(pid))")
                kill(pid, SIGKILL)
            case .waitMore:
                Thread.sleep(forTimeInterval: policy.pollInterval)
            }
        }
    }

    /// Whether the child is gone. `kill(pid, 0)` failing means no such live
    /// process we can signal.
    nonisolated static func childHasExited(pid: pid_t) -> Bool {
        kill(pid, 0) != 0
    }

    /// The bounded reap loop, driven entirely by `TerminationDeadlinePolicy`.
    /// `nonisolated` so it runs off the main actor: nothing here touches
    /// main-actor state, only `kill()` and the clock.
    nonisolated static func reapChild(pid: pid_t, policy: TerminationDeadlinePolicy) async {
        let start = Date()
        var hasEscalated = false
        while true {
            let action = policy.action(
                elapsed: Date().timeIntervalSince(start),
                childHasExited: childHasExited(pid: pid),
                hasEscalated: hasEscalated
            )
            switch action {
            case .replyNow:
                logTeardownOutcome(pid: pid, hasEscalated: hasEscalated)
                return
            case .escalateToSIGKILL:
                hasEscalated = true
                logger.warning(
                    "Backend didn't exit within \(policy.gracefulDeadline)s of SIGTERM — SIGKILL (PID: \(pid)) (#4291)"
                )
                kill(pid, SIGKILL)
            case .waitMore:
                // Yields the thread instead of parking it — the whole point of
                // #4291. `try?`: a cancelled sleep just means "stop waiting",
                // and the next loop turn re-asks the policy.
                do {
                    try await Task.sleep(for: .seconds(policy.pollInterval))
                } catch {
                    // Cancelled mid-teardown: the child already has SIGTERM (and
                    // the parent-pid watchdog backstops it), so stop waiting.
                    logTeardownOutcome(pid: pid, hasEscalated: hasEscalated)
                    return
                }
            }
        }
    }

    /// One honest log line for how the teardown ended — reaped, killed, or still
    /// alive past the deadline (left to the engine's parent-pid watchdog).
    nonisolated private static func logTeardownOutcome(pid: pid_t, hasEscalated: Bool) {
        if childHasExited(pid: pid) {
            logger.info("Backend \(hasEscalated ? "force-killed" : "stopped gracefully") (PID: \(pid))")
        } else {
            logger.error(
                "Backend (PID: \(pid)) still alive past the termination deadline — leaving it to the engine's FICHERO_PARENT_PID watchdog"
            )
        }
    }
}
