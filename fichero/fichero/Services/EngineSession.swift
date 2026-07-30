import FicheroAPIClient
import Foundation
import Observation

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
@Observable
final class EngineSession {
    /// The engine's usability, as one value. Only `ready` serves data; every
    /// other case is reported as toolbar chrome (the status island's message
    /// and the engine popover's Retry) while the real UI stays on screen —
    /// a bad connection is visible, not blocking (#4036). The one exception is
    /// `setupNeeded` on iOS, which still routes to the pairing prompt because
    /// there is no host to talk to yet.
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

    private(set) var phase: Phase = .starting

    /// Which backend this session tracks (#3112). One session per engine root:
    /// the loopback/embedded engine plus one per remote host. Defaults to the
    /// app-global host so the single-host app is unchanged — `EngineSession()`
    /// is still the one loopback session AppState drives.
    let host: BackendHost

    init(host: BackendHost = .appDefault) {
        self.host = host
    }

    /// The credential THIS session authenticates with — resolved for its own
    /// host, never another's (#2866 per-host isolation). A request bound for
    /// host A can never carry host B's token because the lookup is keyed on
    /// this session's host string.
    func resolveToken() -> String? {
        AuthTokenMiddleware.readTokenFromDisk(hostString: host.url.absoluteString)
    }

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

// MARK: - Per-host session registry (#3112)

/// Holds every live `EngineSession` — the multi-remote seam (#2861/#2866).
///
/// The app can talk to several backends at once (an iPhone showing local items
/// plus two Macs), so backend usability is no longer ONE phase but one per
/// host. This registry keeps at most one loopback session (the embedded engine)
/// and N remote sessions, keyed so every loopback URL collapses to the same
/// session while each distinct remote host gets its own. Because sessions are
/// independent objects, a remote host's 401 flips only THAT session to
/// `authRejected` — the local session's phase is untouched, and vice versa.
///
/// Today `activeSession` is the app-global loopback session, so the single-host
/// app is byte-identical; the registry just makes room for the remotes to come
/// (fichero-web/#2883, the library picker) without another rewrite.
@MainActor
@Observable
final class EngineSessionRegistry {
    /// Collapses hosts to sessions: all loopback engines share one session,
    /// each remote host keys on its normalized host string (the same key
    /// `AuthTokenMiddleware` uses for that host's token — so a session and its
    /// credential can never disagree on which host they mean).
    enum Key: Hashable {
        case loopback
        case remote(String)
    }

    private(set) var sessions: [Key: EngineSession]
    /// The host the app currently renders. Switching it re-points every view
    /// that observes `activeSession` at a different backend's phase.
    private(set) var activeHost: BackendHost

    /// Seeds the registry with the app's default session (loopback on macOS, the
    /// configured host on iOS) so `activeSession` is that exact instance — the
    /// one AppState's heartbeat already drives.
    init(defaultSession: EngineSession = EngineSession()) {
        self.activeHost = defaultSession.host
        self.sessions = [Self.key(for: defaultSession.host): defaultSession]
    }

    static func key(for host: BackendHost) -> Key {
        host.isLocal
            ? .loopback
            : .remote(AuthTokenMiddleware.normalizedRemoteHostString(hostString: host.url.absoluteString))
    }

    /// Get-or-create the session for a host. Remote sessions are adopt-only —
    /// created lazily on first request for that host.
    @discardableResult
    func session(for host: BackendHost) -> EngineSession {
        let key = Self.key(for: host)
        if let existing = sessions[key] { return existing }
        let session = EngineSession(host: host)
        sessions[key] = session
        return session
    }

    /// The session the app observes right now (the active host's).
    var activeSession: EngineSession { session(for: activeHost) }

    /// Point the app at a different backend. No-op if already active.
    func activate(_ host: BackendHost) {
        guard host != activeHost else { return }
        session(for: host) // ensure it exists before views read activeSession
        activeHost = host
    }
}
