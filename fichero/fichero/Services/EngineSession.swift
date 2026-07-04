import Foundation

// MARK: - The one engine session state machine (#3107)

/// The single authority for "is the backend usable, and if not, why?" (#2861).
///
/// Before this type, backend usability was smeared across four owners —
/// `EmbeddedBackendService.status`, five `AppState` booleans, the
/// `BackendConnectionView` poll counter, and a hand-rolled iOS mirror — and the
/// root gate had to AND three of them together, so contradictory combinations
/// ("running" + "authBroken" + "isBackendRunning") were representable. Modelling
/// usability as ONE sum type (`Phase`) makes exactly one state true at a time,
/// so the root gate switches on it alone and every phase has explicit UI —
/// never a blank window (#2864/#2859), never library chrome over a dead engine.
///
/// `phase` is `private(set)`: only this type's `mark…`/`apply(_:)` methods write
/// it. `AppState` re-exports it under its legacy boolean names (read-only shims)
/// during the migration, so the ~20 call sites reading `appState.isBackendRunning`
/// keep working while the source of truth moves here.
@MainActor
final class EngineSession: ObservableObject {
    /// The engine's usability, as one value. Only `ready` renders real content;
    /// every other case renders the full-window connection/diagnosis UI (or, for
    /// `setupNeeded` on iOS, the pairing prompt).
    enum Phase: Equatable {
        /// No host is configured/paired yet — first-run pairing (iOS).
        case setupNeeded
        /// Launching / probing. Shows the connecting splash.
        case starting
        /// Port 8765 is held by a process we didn't spawn (#2863/#3111). `pid`
        /// is the responder when known.
        case portConflict(pid: Int?)
        /// Health-200 + identity + token accepted. The ONLY usable state.
        case ready
        /// Engine answers health but rejects the app's token (the blank-window-401
        /// cause, #2864). Carries a human diagnosis.
        case authRejected(diagnosis: String)
        /// Configured but not responding (down / TLS mismatch / lost mid-session).
        case unreachable(diagnosis: String)
        /// The engine failed to start or exited unexpectedly.
        case failed(diagnosis: String)
    }

    @Published private(set) var phase: Phase = .starting

    // MARK: - Derived (the read-only shims AppState re-exports)

    /// The one predicate the root gate needs: real content renders iff `ready`.
    var isReady: Bool { phase == .ready }

    /// True only while starting/probing — drives the "connecting…" splash.
    var isChecking: Bool { phase == .starting }

    /// True when the engine is up but rejecting our credentials (#2864).
    var isAuthRejected: Bool {
        if case .authRejected = phase { return true }
        return false
    }

    /// True when the user must run first-run pairing.
    var needsSetup: Bool { phase == .setupNeeded }

    /// The human-readable cause for the current non-usable state, or nil when
    /// starting/ready/setupNeeded. Feeds `AppState.backendDiagnosis` /
    /// `.backendError` and the connection view's failure detail.
    var diagnosis: String? {
        switch phase {
        case .authRejected(let message), .unreachable(let message), .failed(let message):
            return message
        case .portConflict(let pid):
            let who = pid.map(String.init) ?? "unknown"
            return "Port 8765 is held by another process (PID \(who))."
        case .setupNeeded, .starting, .ready:
            return nil
        }
    }

    // MARK: - Transitions (the ONLY writers of `phase`)

    func markSetupNeeded() { phase = .setupNeeded }
    func markStarting() { phase = .starting }
    func markPortConflict(pid: Int?) { phase = .portConflict(pid: pid) }
    func markReady() { phase = .ready }
    func markAuthRejected(_ diagnosis: String) { phase = .authRejected(diagnosis: diagnosis) }
    func markUnreachable(_ diagnosis: String) { phase = .unreachable(diagnosis: diagnosis) }
    func markFailed(_ diagnosis: String) { phase = .failed(diagnosis: diagnosis) }
}
