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

    /// Stop the embedded backend
    func stop() {
        // Don't stop external backends (user-managed)
        if isExternalBackend {
            logger.info("Using external backend - leaving it running (user-managed)")
            status = .stopped
            return
        }

        guard let pid = backendPID else {
            logger.info("ℹ️  No embedded backend PID tracked (may not have launched yet or using external)")
            status = .stopped
            return
        }

        logger.info("Stopping embedded backend (PID: \(pid))...")

        // Mark intentional so the terminationHandler doesn't flip .failed.
        intentionalStop = true

        // Clear state immediately
        backendPID = nil
        status = .stopped

        // Graceful shutdown - send SIGTERM
        kill(pid, SIGTERM)

        // Wait up to 5 seconds for graceful shutdown (synchronous)
        // This must be synchronous so applicationWillTerminate waits for it
        for attempt in 0..<50 {
            // Check if process is still running
            if kill(pid, 0) != 0 {
                // Process no longer exists
                logger.info("Backend stopped gracefully after \(attempt * 100)ms")
                return
            }
            // Sleep for 100ms
            Thread.sleep(forTimeInterval: 0.1)
        }

        // Force kill if still running after 5 seconds
        if kill(pid, 0) == 0 {
            logger.warning("Backend didn't shut down gracefully after 5s, force killing...")
            kill(pid, SIGKILL)

            // Give it one more second to die
            Thread.sleep(forTimeInterval: 1.0)

            if kill(pid, 0) == 0 {
                logger.error("Failed to kill backend process (PID: \(pid))")
            } else {
                logger.info("Backend force-killed successfully")
            }
        }
    }
}
