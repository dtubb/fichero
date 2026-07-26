#if canImport(AppKit)
import Foundation
import OSLog
import SwiftUI

/// Owns the engine's lifecycle at APP scope, not window scope (#3945).
///
/// Before this, the engine was started from a `WindowGroup`'s `.task`
/// (`FicheroApp.swift`), so "who owns the engine" was really "whichever window
/// happened to open first" — and the reuse guard (`shouldReuseExistingConnection`)
/// existed only to stop every subsequent window/tab re-running connect+auth.
/// Opening a window is not an engine event.
///
/// This controller is created and held by `FicheroAppDelegate`, started from
/// `applicationDidFinishLaunching` and stopped from `applicationWillTerminate` —
/// symmetric, app-scoped, and impossible to lose by closing a window. It owns
/// the two halves that already existed in embryo:
///   • `EmbeddedBackendService` — spawn / watch / stop (the process, macOS-only).
///   • `AppState` — readiness probe, auth warm-up, heartbeat (the connection).
/// `EngineSession` (inside `AppState`) stays the single phase writer the window's
/// `BackendRootGate` observes; windows observe, they never trigger.
///
/// This is the PROCESS axis of the app-owns-engine design (#3947). The CONNECTION
/// axis — a per-library set of connections, each to the local process or a remote
/// engine — layers on in a later slice; today the controller holds exactly one
/// local engine plus `LibraryManager`'s existing per-library hosts.
@MainActor
@Observable
final class EngineLifecycleController {
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "EngineLifecycle")

    /// The process half — spawn/watch/stop of the embedded (or adopted external)
    /// engine. One per app.
    let backendService = EmbeddedBackendService()

    /// The connection half — readiness probe, auth, heartbeat, and the observable
    /// `EngineSession` phase the window gate renders.
    let appState = AppState()

    /// The open-library manager (shared singleton). Its ready side-effects fire
    /// through `refreshAfterBackendBecameReady()` once the engine authenticates.
    let libraryManager = LibraryManager.shared

    /// Guards against overlapping connect sequences (e.g. a Retry fired while the
    /// launch connect is still in flight). Replaces the role the per-window
    /// `shouldReuseExistingConnection` guard played when the trigger was a
    /// window `.task` — now the trigger is a single app-scoped `start()`.
    private var isConnecting = false

    init() {
        // Fetch the readiness probe through the app-wide generated client so it
        // rides the same transport (UDS / in-memory / HTTPS) and auth middleware
        // the app uses — a UDS-only engine never answered the old raw-URLSession
        // probe. Both properties are this controller's own, so wiring them here
        // keeps the process and connection halves pointed at one client.
        backendService.readinessClient = appState.ficheroClient
        // #4064: route a mid-session supervised-engine drop back here so the
        // supervisor can auto-restart the embedded backend (bounded retries +
        // backoff) before ever surfacing a manual-CLI diagnosis. The heartbeat
        // detects the drop; this controller owns the only spawn path (#2611),
        // so the hook is the seam between "I lost the backend" and "respawn it".
        // `[weak self]` so the controller's lifetime stays app-scoped, not
        // retained by AppState through the closure.
        appState.onSupervisedBackendDropped = { [weak self] in
            await self?.handleSupervisedBackendDropped()
        }
    }

    /// Kick the engine once at app launch. Called from
    /// `applicationDidFinishLaunching`, never from a window.
    func start() async {
        await connect(restart: false)
    }

    /// Re-run the connect sequence — respawns a wedged embedded engine (#3108).
    /// Backs the connection view's Retry button, so Retry never re-implements
    /// `start()`.
    func retry() async {
        await connect(restart: true)
    }

    /// Auto-restart the supervised embedded backend after a mid-session drop
    /// (#4064), REUSING the existing spawn supervisor (#2611) — never a new
    /// spawn mechanism. Bounded retries with backoff; only when they run out
    /// (or the crash-loop budget is spent) does the Retry/Quit modal surface
    /// over the live main GUI. The release/embedded build never shows a manual
    /// CLI: a drop here means "respawn it", not "run it by hand". Re-entrant
    /// guard so a second drop detected while a restart is already in flight is
    /// a no-op (the heartbeat can't re-fire the hook through `markStarting`).
    private var isHandlingSupervisedDrop = false
    static let supervisedAutoRestartAttempts = 3

    func handleSupervisedBackendDropped() async {
        // Only the spawning strategy can auto-restart. A debugExternal /
        // configuredRemote / iosCompanion drop has no local process to respawn
        // — those surface their existing diagnosis and the user retries by
        // hand. The heartbeat's `supervisedDropOutcome` already gates this, but
        // double-check here so a mis-routed call can't spawn in the wrong build.
        guard EngineConfig.engineProvisioningStrategy().spawnsBundledEngine else {
            logger.info("Supervised backend drop: strategy doesn't spawn — skipping auto-restart (#4064)")
            return
        }
        guard !isHandlingSupervisedDrop else {
            logger.info("Supervised backend drop: already handling — ignoring re-entrant call (#4064)")
            return
        }
        isHandlingSupervisedDrop = true
        defer { isHandlingSupervisedDrop = false }

        let maxAttempts = Self.supervisedAutoRestartAttempts
        var attemptsUsed = 0
        for attempt in 1...maxAttempts {
            // Crash-loop guard (#18): stop restarting a hot-crashing engine.
            let budgetRemaining = backendService.shouldAutoRestartAfterCrash()
            attemptsUsed = attempt
            guard budgetRemaining else {
                logger.error("Supervised backend drop: crash-loop budget exhausted before attempt \(attempt) — surfacing Retry/Quit modal (#4064)")
                // The engine is still down (we crashed) and the spawn supervisor
                // refused another restart — surface the modal; prefer-raise over
                // silent fallback (#4064).
                if !appState.isBackendRunning {
                    appState.showBackendDropModal = true
                }
                return
            }
            logger.warning("Supervised backend dropped — auto-restart attempt \(attempt)/\(maxAttempts) (#4064)")
            // `.starting` so the toolbar popover shows the booting splash
            // instead of the dead-engine diagnosis while we respawn; the
            // heartbeat's next `.ready` flips it back the moment the engine
            // answers.
            appState.engine.markStarting()
            await retry() // reuses the single connect sequence (#3108)
            if appState.isBackendRunning {
                logger.info("Supervised backend drop: auto-restart recovered on attempt \(attempt) (#4064)")
                return // recovered — no modal
            }
            // Backoff before the next attempt: 1s, 2s, 4s.
            if attempt < maxAttempts {
                let backoffSeconds = 1 << (attempt - 1)
                logger.info("Supervised backend drop: backing off for \(backoffSeconds)s before retry (#4064)")
                try? await Task.sleep(for: .seconds(backoffSeconds))
            }
        }
        logger.error("Supervised backend drop: auto-restart exhausted after \(attemptsUsed) attempts — surfacing Retry/Quit modal (#4064)")
        appState.showBackendDropModal = true
    }

    /// Pure: should the Retry/Quit modal be shown after a supervised
    /// auto-restart attempt (#4064)? True only when the engine is STILL not
    /// ready AND either the crash-loop budget is spent OR the bounded retry
    /// count is exhausted. Pure so the modal-gating decision is unit-testable
    /// without spawning a real engine.
    static func shouldShowBackendDropModal(
        isReady: Bool,
        crashBudgetExhausted: Bool,
        attemptsUsed: Int,
        maxAttempts: Int = supervisedAutoRestartAttempts
    ) -> Bool {
        if isReady { return false }
        return crashBudgetExhausted || attemptsUsed >= maxAttempts
    }

    /// Stop the engine. Called from `applicationWillTerminate`.
    func stop() {
        backendService.stop()
    }

    /// The single connect sequence shared by launch and Retry (#3108). Moved
    /// verbatim from `FicheroApp.connectBackend` when engine ownership left the
    /// window (#3945) — the only change is that `backendService`/`appState`/
    /// `libraryManager` are now this controller's own properties. Split into
    /// per-phase helpers below (spawn / probe / finish / failure) so the
    /// sequence stays readable; each helper preserves the original ordering
    /// and side effects exactly.
    private func connect(restart: Bool) async {
        // A single app-scoped controller means the old per-window reuse guard is
        // gone (#3394/#3407 can't occur — no window triggers connect). Keep only a
        // narrow overlap guard so a Retry fired mid-connect is a no-op.
        guard !isConnecting else {
            logger.info("connect: already connecting — ignoring re-entrant call")
            return
        }
        isConnecting = true
        defer { isConnecting = false }
        LaunchProfile.milestone("connect() entry — main actor reached")

        // Consume the single provisioning decision (#3109) instead of re-deriving
        // the mode here. `connectsToRemoteHost` is the old
        // `requiresExternalBackendConnection` branch.
        let strategy = EngineConfig.engineProvisioningStrategy()
        let usesExternal = strategy.connectsToRemoteHost
        logger.info("Launch provisioning strategy: \(String(describing: strategy), privacy: .public) (#3109)")
        // Back to `.starting` so the connection view shows the booting splash (and
        // clears any prior failure diagnosis) while we probe.
        appState.engine.markStarting()
        backendService.status = .starting
        backendService.errorMessage = nil

        let backendStart = Date()
        do {
            if !usesExternal {
                try await spawnEmbeddedEngine(restart: restart, backendStart: backendStart)
            }

            guard await probeBackendReadiness() else {
                // Keep re-probing in the background so we recover to the workspace
                // the moment the engine answers — never park forever on a healthy
                // engine (#3162). The heartbeat's own guard makes this idempotent.
                appState.startBackendHeartbeat()
                return
            }

            await finishSuccessfulConnect(backendStart: backendStart)
        } catch BackendError.portConflict(let pid) {
            handlePortConflict(pid: pid)
        } catch {
            handleConnectFailure(error)
        }
    }

    /// Respawn (on retry) and start the embedded engine process. The port
    /// pre-flight / orphan sweep lives in `start()`.
    private func spawnEmbeddedEngine(restart: Bool, backendStart: Date) async throws {
        // Respawn a stuck engine on an explicit retry; a fresh launch just
        // starts.
        if restart {
            backendService.stop()
        }
        LaunchProfile.milestone("engine spawn requested")
        try await backendService.start()
        let backendMs = Date().timeIntervalSince(backendStart) * 1000
        LaunchProfile.milestone("engine spawn returned")
        logger.info("⏱ backendService.start: \(backendMs, format: .fixed(precision: 1))ms")
    }

    /// Health probe after the engine is up — re-probing with backoff before
    /// parking, so a transient miss while the engine finishes startup (it's
    /// often serving 200s a beat later) doesn't wall a healthy engine (#3162).
    /// #3975: hand over the readiness the spawn ALREADY proved (health + nonce
    /// + authenticated /api/registry 200). When it's `.ready`, the connection
    /// layer skips the redundant re-probe + second health GET and goes straight
    /// to warm-up — removing ~3-4 serial round-trips between serving and ready.
    /// A nil/non-ready value (remote host, or a retry before start) falls
    /// through to the full probe, so the #3162 backoff is untouched there.
    /// Returns whether the backend is reachable; on failure it records the
    /// failed status/error itself so callers only need to react to `false`.
    private func probeBackendReadiness() async -> Bool {
        await appState.checkBackendHealthUntilReady(provenReadiness: backendService.lastReadiness)
        guard appState.isBackendRunning else {
            backendService.status = .failed
            backendService.errorMessage = appState.backendError
            logger.error(
                "Backend not reachable at \(EngineConfig.host.absoluteString, privacy: .public)"
            )
            return false
        }
        return true
    }

    /// The shared post-ready side effects: mark running, start the heartbeat,
    /// renew the device token, and restore libraries.
    private func finishSuccessfulConnect(backendStart: Date) async {
        let readyMs = Date().timeIntervalSince(backendStart) * 1000
        LaunchProfile.milestone("first authenticated ready")
        logger.info("⏱ engine authenticated and ready: \(readyMs, format: .fixed(precision: 1))ms")

        backendService.status = .running
        backendService.errorMessage = nil
        // The heartbeat is the single ongoing poller once ready (#3108); its own
        // guard makes repeated calls idempotent.
        appState.startBackendHeartbeat()
        // Proactively renew the device token if near expiry (#3096), before it
        // can lapse into a 401. A Mac can pair as a remote client too, so this
        // belongs on the macOS connect path as well as iOS — no-op for the
        // embedded/local host (loopback has no stored expiry); a failed renew
        // keeps the old token (the expired → re-pair path is the safety net).
        await DeviceTokenRenewal.renewIfNeeded(host: EngineConfig.host)
        // The one shared post-ready side-effect block (#3113); adopt is a no-op
        // on an embedded/local host, so no `usesExternal` branch here.
        let restorationStart = Date()
        await libraryManager.refreshAfterBackendBecameReady()
        let restorationMs = Date().timeIntervalSince(restorationStart) * 1000
        logger.info("⏱ post-ready library restoration: \(restorationMs, format: .fixed(precision: 1))ms")
    }

    /// A process we didn't spawn holds :8765 → surface the in-window decision
    /// (#3111): Stop it / Use it / Quit. Never a pre-window NSAlert, never
    /// self-terminate (#3042).
    private func handlePortConflict(pid: Int?) {
        logger.info("Port 8765 held by PID \(pid.map(String.init) ?? "unknown") — portConflict phase")
        appState.engine.markPortConflict(pid: pid)
        backendService.status = .failed
    }

    /// An adopted squatter that answers health but rejects our token is
    /// authRejected, not a generic failure — the authenticated probe is the
    /// gate (#2864/#3111).
    private func handleConnectFailure(_ error: Error) {
        if backendService.lastReadiness == .authRejected {
            appState.engine.markAuthRejected(
                "The engine already on port 8765 rejected this app's credentials."
            )
            backendService.status = .failed
        } else {
            logger.error("Failed to start backend: \(error.localizedDescription)")
            showBackendError(error)
        }
    }

    /// Surface a start failure through the window gate — never terminate the app
    /// (#3042). `BackendRootGate` renders `BackendConnectionView` (diagnosis +
    /// Retry) for any non-usable backend state.
    private func showBackendError(_ error: Error) {
        logger.error("Backend failed to start: \(error.localizedDescription, privacy: .public)")
        // The single phase owner drives the gate (#3107); service status is kept in
        // sync as secondary lifecycle bookkeeping.
        appState.engine.markFailed(error.localizedDescription)
        backendService.status = .failed
        backendService.errorMessage = error.localizedDescription
    }
}
#endif
