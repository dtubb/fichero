import FicheroAPIClient
import Foundation
import Observation
import OSLog
import Security

private let logger = Logger(subsystem: "app.fichero.fichero", category: "EmbeddedBackend")

/// True when this process is hosting an XCTest bundle. Detected via the XCTest
/// runtime class, which is loaded into the host the moment the test bundle is
/// injected (before `main`), so it's reliable regardless of how the host was
/// launched — unlike the `XCTest*` env vars, which don't always propagate.
///
/// Used to neutralize app-boot side effects during tests: the host must not
/// launch a backend (it would race / fatally terminate via showBackendError)
/// or open the user's real libraries. The integration harness (EngineHarness)
/// owns engine lifecycle and seeds its own disposable library.
func isRunningXCTests() -> Bool {
    if NSClassFromString("XCTestCase") != nil { return true }
    let env = ProcessInfo.processInfo.environment
    return env["XCTestConfigurationFilePath"] != nil || env["XCTestBundlePath"] != nil
}

// `isUITesting()` / `uiTestSupportDirectory()` live in UITestSupport.swift (#1230).

/// Manages the embedded Python backend lifecycle.
///
/// The class body here holds only stored state, nested types, and `deinit`;
/// the methods live in same-directory `EmbeddedBackendService+<Concern>.swift`
/// extension files (Lifecycle, Spawn, TLS, Readiness, Tokens, Ports).
@MainActor
@Observable
final class EmbeddedBackendService {
    var status: BackendStatus = .stopped
    var errorMessage: String?

    // Plumbing, not observed UI state — exclude from @Observable tracking, and
    // `nonisolated(unsafe)` so the nonisolated Swift-6 `deinit` can read it
    // (only mutated on the main actor; set only on the embedded-spawn path).
    // Promoted from `private` to internal: read/written by stop()/deinit/launch
    // across the Lifecycle and Spawn extension files.
    @ObservationIgnored nonisolated(unsafe) var backendPID: pid_t?
    // Promoted from `private` to internal: referenced by the Lifecycle / Spawn extensions.
    var isExternalBackend = false  // Track if using external vs embedded backend
    var isUsingExternalBackend: Bool { isExternalBackend }
    /// The FICHERO_LAUNCH_NONCE we passed to the engine we spawned (#2862).
    /// Readiness verifies /api/health echoes this exact value, proving the
    /// responder is the child we launched — not a stale process on the port.
    /// nil when we adopted an external engine (we didn't spawn it, so there's
    /// no nonce to match).
    /// Setter widened from `private(set)` to internal: set by the Lifecycle / Spawn extensions.
    var expectedLaunchNonce: String?
    // Promoted from `private` to internal: read by probeReadiness in the Readiness extension.
    var backendURL: URL {
        // Own-engine traffic stays on loopback, never the advertised public URL (#2604).
        EngineConfig.host
    }

    enum BackendStatus {
        case stopped
        case starting
        case running
        case failed
    }

    /// Outcome of an authenticated readiness probe (#2862) — now the shared
    /// `EngineReadiness` (#3106), verified by the one `EngineReadinessProbe`.
    typealias ReadinessResult = EngineReadiness

    /// The most recent readiness outcome, for #2864's diagnosis UI.
    /// Setter widened from `private(set)` to internal: set by the Readiness extension.
    var lastReadiness: ReadinessResult?

    /// Set true when WE initiate a stop (stop()), so the process
    /// terminationHandler doesn't misread an intentional shutdown as a crash
    /// and flip status to .failed (#2863).
    /// Promoted from `private` to internal: set by stop()/launch in the Lifecycle / Spawn extensions.
    var intentionalStop = false

    /// True while a start()/respawn is in flight. Guards against a second
    /// `retry()` spawning a duplicate engine or racing the first probe (#3108):
    /// a retry while starting is a no-op. Because `start()` is @MainActor, the
    /// guard+set at the top run without interleaving up to the first `await`,
    /// so concurrent retries deterministically see this true and bounce.
    /// Setter widened from `private(set)` to internal: set by start() in the Lifecycle extension.
    var isStarting = false

    /// How many `start()` calls passed the re-entrancy guard — the spawn-attempt
    /// counter the concurrency-stress test asserts stays at 1 under N rapid
    /// retries (#3108).
    /// Setter widened from `private(set)` to internal: set by start() in the Lifecycle extension.
    var startAttemptsPassedGuard = 0

    /// The user's in-window decision for a foreign :8765 holder (#3111): Stop it
    /// (SIGTERM + respawn) or Use it (adopt, still gated on the authenticated
    /// probe). Quit is a pure UI action (user-chosen terminate), so it isn't
    /// modelled here. Set by the connection view's buttons before a retry;
    /// `resolvePortConflict` consumes it exactly once. nil → surface the
    /// portConflict phase instead of a pre-window NSAlert.
    enum PortConflictResolution { case stopIt, useIt }
    var pendingPortConflictResolution: PortConflictResolution?

    /// The provisioning strategy the most recent `start()` acted on (#3109),
    /// so the mode is inspectable rather than re-derived. nil before first start.
    /// Setter widened from `private(set)` to internal: set by start() in the Lifecycle extension.
    var lastProvisioningStrategy: EngineConfig.EngineProvisioningStrategy?

    deinit {
        // Clean up backend on service deallocation (shouldn't happen in normal app lifecycle).
        // `backendPID` is set only on the embedded-spawn path and stays nil for every
        // external-backend branch, so a non-nil pid already implies an embedded backend —
        // the former `!isExternalBackend` guard was redundant. Dropping that read keeps
        // `isExternalBackend` fully @Observable-tracked for the Settings views while letting
        // this nonisolated deinit compile (it no longer touches a main-actor-isolated prop).
        if let pid = backendPID {
            logger.warning("EmbeddedBackendService deinit - terminating backend (PID: \(pid))")
            logger.warning("This shouldn't happen in normal app lifecycle - backend should be stopped via stop()")
            kill(pid, SIGTERM)
        }
    }
}

// MARK: - Errors

enum BackendError: LocalizedError {
    case notRunning
    case backendAppNotFound
    case launchFailed(Error)
    case timeout
    /// The engine we SPAWNED never served: it exited, or stayed alive without
    /// ever binding until the insanity cap (#3930). `diagnosis` carries the
    /// engine.log tail, so a launch failure explains itself instead of reporting
    /// a bare timeout the user can do nothing with.
    case engineDidNotStart(diagnosis: String)
    /// A process we didn't spawn holds port 8765 (#3111). Carries the holder's
    /// PID (when known) so the in-window portConflict phase can name it. Handled
    /// by the launch orchestrator (→ `markPortConflict`), never shown as a raw
    /// error string.
    case portConflict(pid: Int?)

    var errorDescription: String? {
        switch self {
        case .notRunning:
            return "Backend is not running"
        case .portConflict(let pid):
            let who = pid.map(String.init) ?? "unknown"
            return "Port 8765 is held by another process (PID \(who))."
        case .backendAppNotFound:
            // Debug builds don't embed the engine (the embed phase is Release-only),
            // so the usual cause in a Debug ⌘R is simply no engine running on :8765.
            #if DEBUG
            return "The Fichero Engine isn't running. In a Debug build the engine is "
                + "not bundled — start it first with fichero-engine/scripts/start_backend.sh "
                + "(or briefcase dev), then Retry."
            #else
            return "Backend app not found in bundle. Build the engine with: "
                + "briefcase build macOS --app engine (in fichero-engine/), then rebuild Fichero in Xcode."
            #endif
        case .launchFailed(let error):
            return "Failed to launch backend app: \(error.localizedDescription)"
        case .timeout:
            return "Backend failed to start within timeout"
        case .engineDidNotStart(let diagnosis):
            return diagnosis
        }
    }
}
