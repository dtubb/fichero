import FicheroAPIClient
import SwiftUI

extension BackendConnectionView {
    /// Red failure UI shows ONLY for an explicit terminal failure
    /// (`status == .failed`). During normal startup the service walks
    /// `.stopped → .starting → .running`, and `appState.isCheckingBackend`
    /// flips false in the 5 s gaps between health polls — keying failure off
    /// `(!isCheckingBackend && !isBackendRunning)` painted a misleading red
    /// "Engine Not Running" flash during those gaps while the engine was still
    /// cold-starting (#2664). Genuine failures still surface: external/custom
    /// hosts set `.failed` immediately, and the embedded poll loop below flips
    /// to `.failed` after the 60 s timeout.
    var showsFailureState: Bool {
        // Driven by the single phase owner (#3107): any non-ready, non-starting,
        // non-setup phase is a failure the user can act on.
        switch appState.engine.phase {
        case .portConflict, .authRejected, .unreachable, .failed:
            return true
        case .setupNeeded, .starting, .ready:
            return false
        }
    }

    var titleText: String {
        usesExternalBackendConnection ? "Connect to Fichero" : "Starting Fichero"
    }

    /// The holding PID when the engine is in the `portConflict` phase (#3111),
    /// else nil. Drives whether "Stop it" is offerable.
    ///
    /// nil does NOT mean "no conflict" — under App Sandbox the holder's PID is
    /// unknowable (no lsof), so the App Store build reports `portConflict(nil)`
    /// (#3749). Ask `isPortConflict` for "are we in the conflict phase"; ask this
    /// only for "do we know who to stop".
    var portConflictPID: Int? {
        if case .portConflict(let pid) = appState.engine.phase { return pid }
        return nil
    }

    /// In the `portConflict` phase, PID known or not. Gates the recovery actions
    /// — keyed off the phase rather than the PID so a sandboxed conflict renders
    /// Use it / Quit instead of an empty box.
    var isPortConflict: Bool {
        if case .portConflict = appState.engine.phase { return true }
        return false
    }

    var failureTitle: String {
        if isPortConflict {
            // Foreign holder of :8765 — the in-window replacement for the old
            // pre-window NSAlert (#3111).
            return "Port 8765 Is In Use"
        }
        return Self.connectionFailureTitle(
            accessError: failureAccessError,
            authBroken: appState.authBroken,
            usesExternalBackendConnection: usesExternalBackendConnection
        )
    }

    /// Pure phase → failure-title mapping (#3341). Extracted so the invariant
    /// "never claim the engine is NOT RUNNING when we only failed to CONNECT" is
    /// unit-testable. When the engine is reachable-but-unusable (unreachable /
    /// unclassified failure), the copy says "Can't Connect to Engine" — the
    /// engine may well be running (wrong port / transient / socket); the screen's
    /// Retry + Show Log let the user act, and the detail carries the real reason.
    static func connectionFailureTitle(
        accessError: AccessError?,
        authBroken: Bool,
        usesExternalBackendConnection: Bool
    ) -> String {
        switch accessError {
        case .staleBootstrapToken:
            return "Engine Token Mismatch"
        case .tlsPinFailure:
            return "Certificate Mismatch"
        case .deviceAccessExpired:
            return "Device Access Expired"
        case .forbidden:
            return "No Access to Engine"
        case .transport:
            return "Connection Failed"
        case .engineUnreachable:
            // Couldn't reach the engine — NOT the same as "not running" (#3341).
            return usesExternalBackendConnection ? "Backend Not Reachable" : "Can't Connect to Engine"
        case .unauthenticated, .none:
            break
        }
        if authBroken {
            // Health-200-but-auth-broken: the specific state that used to blank
            // the window with silent 401s (#2864). Connected to the engine, but
            // the saved sign-in is stale → the Reset Sign-In & Retry action.
            return "Can't Authenticate to Engine"
        }
        // Unclassified failure (e.g. `.failed`): we know we couldn't connect, not
        // that the engine is stopped — so never assert "Engine Not Running" (#3341).
        return usesExternalBackendConnection ? "Backend Not Reachable" : "Can't Connect to Engine"
    }

    /// Prefer the specific diagnosis (port occupied by PID / auth rejected /
    /// probe failed) over the generic error string (#2864).
    var failureDetail: String? {
        failureAccessError?.errorDescription ?? appState.backendDiagnosis ?? appState.backendError
    }

    var failureAccessError: AccessError? {
        appState.backendAccessError ?? (appState.authBroken ? .unauthenticated : nil)
    }

    var retryButtonTitle: String {
        if case .staleBootstrapToken? = failureAccessError {
            return usesExternalBackendConnection ? "Retry After Restarting Engine" : "Restart Engine"
        }
        return usesExternalBackendConnection ? "Retry Connection" : "Restart Engine"
    }

    var secondaryStatusText: String {
        usesExternalBackendConnection ? "Connect to a running Fichero engine to continue." : "This can take a moment."
    }
}
