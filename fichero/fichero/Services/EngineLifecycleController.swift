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

    /// Stop the engine. Called from `applicationWillTerminate`.
    func stop() {
        backendService.stop()
    }

    // swiftlint:disable function_body_length
    // connect() is a faithful relocation of FicheroApp.connectBackend: one linear
    // happy path plus its catch arms; splitting it would obscure the sequence.
    /// The single connect sequence shared by launch and Retry (#3108). Moved
    /// verbatim from `FicheroApp.connectBackend` when engine ownership left the
    /// window (#3945) — the only change is that `backendService`/`appState`/
    /// `libraryManager` are now this controller's own properties.
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
                // Respawn a stuck engine on an explicit retry; a fresh launch just
                // starts. The port pre-flight / orphan sweep lives in start().
                if restart {
                    backendService.stop()
                }
                LaunchProfile.milestone("engine spawn requested")
                try await backendService.start()
                let backendMs = Date().timeIntervalSince(backendStart) * 1000
                LaunchProfile.milestone("engine spawn returned")
                logger.info("⏱ backendService.start: \(backendMs, format: .fixed(precision: 1))ms")
            }

            // Health probe after the engine is up — re-probing with backoff before
            // parking, so a transient miss while the engine finishes startup (it's
            // often serving 200s a beat later) doesn't wall a healthy engine (#3162).
            // #3975: hand over the readiness the spawn ALREADY proved (health + nonce
            // + authenticated /api/registry 200). When it's `.ready`, the connection
            // layer skips the redundant re-probe + second health GET and goes straight
            // to warm-up — removing ~3-4 serial round-trips between serving and ready.
            // A nil/non-ready value (remote host, or a retry before start) falls
            // through to the full probe, so the #3162 backoff is untouched there.
            await appState.checkBackendHealthUntilReady(provenReadiness: backendService.lastReadiness)
            guard appState.isBackendRunning else {
                backendService.status = .failed
                backendService.errorMessage = appState.backendError
                logger.error(
                    "Backend not reachable at \(EngineConfig.host.absoluteString, privacy: .public)"
                )
                // Keep re-probing in the background so we recover to the workspace
                // the moment the engine answers — never park forever on a healthy
                // engine (#3162). The heartbeat's own guard makes this idempotent.
                appState.startBackendHeartbeat()
                return
            }

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
        } catch BackendError.portConflict(let pid) {
            // A process we didn't spawn holds :8765 → surface the in-window decision
            // (#3111): Stop it / Use it / Quit. Never a pre-window NSAlert, never
            // self-terminate (#3042).
            logger.info("Port 8765 held by PID \(pid.map(String.init) ?? "unknown") — portConflict phase")
            appState.engine.markPortConflict(pid: pid)
            backendService.status = .failed
        } catch {
            // An adopted squatter that answers health but rejects our token is
            // authRejected, not a generic failure — the authenticated probe is the
            // gate (#2864/#3111).
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
    }
    // swiftlint:enable function_body_length

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
