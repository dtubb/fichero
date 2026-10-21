import FicheroAPIClient
import os
import SwiftUI

extension ConnectionPresentation {
    /// Why the app last restarted its engine, one sentence, set by the heartbeat when it hands the engine to the supervisor
    /// and cleared when the engine answers again (`activity.engine.restart-says-why`).
    /// Read from the heartbeat (any isolation) and the views; held behind a lock so it is concurrency-safe without pinning
    /// every caller of the pure presentation functions to the main actor.
    static var lastRestartReason: String? {
        get { restartReasonLock.withLock { $0 } }
        set { restartReasonLock.withLock { $0 = newValue } }
    }

    private static let restartReasonLock = OSAllocatedUnfairLock<String?>(initialState: nil)

    /// What the engine last said held its loop (`GET /api/health` `dependencies['previous_stall']`, #5843), kept from the
    /// health read so the next restart sentence can add it. The engine reports it once, in the life AFTER the stall.
    static var lastPreviousStall: String? {
        get { previousStallLock.withLock { $0 } }
        set { previousStallLock.withLock { $0 = newValue } }
    }

    private static let previousStallLock = OSAllocatedUnfairLock<String?>(initialState: nil)

    /// Reads the kept stall and clears it in ONE step, so a health read landing between a get and a set cannot be lost.
    static func takePreviousStall() -> String? {
        // A restart is a new engine life: the same "<N>s in <func>" from a second death is news again.
        lastSeenStallLock.withLock { $0 = nil }
        return previousStallLock.withLock { stall in
            defer { stall = nil }
            return stall
        }
    }

    private static let lastSeenStallLock = OSAllocatedUnfairLock<String?>(initialState: nil)

    /// A health read reports the previous engine's stall for this engine's whole life. Keeps it (for the next restart sentence)
    /// only when it is new; returns whether it was, so the caller logs it once, not at every Settings re-read.
    @discardableResult
    static func notePreviousStall(_ stall: String) -> Bool {
        let isNew = lastSeenStallLock.withLock { seen -> Bool in
            defer { seen = stall }
            return seen != stall
        }
        if isNew { lastPreviousStall = stall }
        return isNew
    }

    /// The failure half of the mapping, split out so `status(…)` stays one
    /// bounded switch.
    static func failureStatus(
        accessError: AccessError?,
        authBroken: Bool,
        ownership: EngineOwnership
    ) -> Display {
        let title = failureTitle(
            accessError: accessError,
            authBroken: authBroken,
            ownership: ownership
        )
        return Display(
            title: title,
            shortTitle: failureShortTitle(
                accessError: accessError,
                authBroken: authBroken,
                ownership: ownership
            ),
            detail: failureDetail(
                accessError: accessError,
                authBroken: authBroken,
                ownership: ownership
            ),
            symbol: "exclamationmark.triangle.fill",
            isError: true,
            // The embedded engine's supervisor auto-restarts a mid-session drop
            // (#4064) and the heartbeat lowers the alarm on its own (#4296), so
            // the app-managed failure says so rather than parking a popover the
            // user has to dismiss.
            isRecovering: ownership == .appManaged,
            action: failureAction(accessError: accessError, authBroken: authBroken, ownership: ownership)
        )
    }

    /// Pure phase → failure-title mapping (#3341, moved here from
    /// `BackendConnectionView` so there is ONE title source).
    ///
    /// The load-bearing invariant: never claim the engine is NOT RUNNING when
    /// we only failed to CONNECT. Reachable-but-unusable says "Can't Connect to
    /// Server" — the engine may well be running (wrong port / transient /
    /// socket) — and the action plus Show Log let the user act.
    static func failureTitle(
        accessError: AccessError?,
        authBroken: Bool,
        ownership: EngineOwnership
    ) -> String {
        let isAppManaged = ownership == .appManaged
        let isRemote = ownership == .remote
        switch accessError {
        case .staleBootstrapToken:
            return isAppManaged ? "Fichero Couldn't Refresh Its Server Token" : "Server Token Mismatch"
        case .tlsPinFailure:
            return isAppManaged ? "Fichero Couldn't Verify Its Server" : "Certificate Mismatch"
        case .deviceAccessExpired:
            return "Device Access Expired"
        case .forbidden:
            return "No Access to Server"
        case .transport:
            return "Connection Failed"
        case .engineUnreachable:
            return isRemote ? "Backend Not Reachable" : "Can't Connect to Server"
        case .unauthenticated, .none:
            break
        }
        if authBroken {
            return isAppManaged ? "Fichero Couldn't Authenticate to Its Server" : "Can't Authenticate to Server"
        }
        return isRemote ? "Backend Not Reachable" : "Can't Connect to Server"
    }

    /// The island form of `failureTitle` (#4366).
    ///
    /// Same table, same branches, written for a one-line 260pt slot instead of
    /// a popover header. "Fichero Couldn't Authenticate to Its Server" is 43
    /// characters and arrives in the island as a fragment; "Sign-in rejected"
    /// says the same thing and fits. This is the issue's rule applied to the
    /// engine's own strings: the LINE gets the short form, the popover carries
    /// the full one, and the sentence lives in `detail`.
    ///
    /// Sentence case on purpose — these sit in a status line beside progress
    /// text ("Importing 4 of 900…"), not as a headline.
    static func failureShortTitle(
        accessError: AccessError?,
        authBroken: Bool,
        ownership: EngineOwnership
    ) -> String {
        switch accessError {
        case .staleBootstrapToken:
            return "Server token out of date"
        case .tlsPinFailure:
            return "Certificate mismatch"
        case .deviceAccessExpired:
            return "Device access expired"
        case .forbidden:
            return "No access to server"
        case .transport:
            return "Connection failed"
        case .engineUnreachable:
            return "Can't connect to server"
        case .unauthenticated, .none:
            break
        }
        if authBroken {
            return "Sign-in rejected"
        }
        return "Can't connect to server"
    }

    /// One plain sentence. Derived from ownership, never from a raw transport
    /// error string — `HTTPClientError.deadlineExceeded` in a content pane is
    /// exactly what #4269 forbids, and a `PYTHONPATH=…` invocation is not a
    /// user action (#4380). Both live in the engine log, reachable via Show Log.
    static func failureDetail(
        accessError: AccessError?,
        authBroken: Bool,
        ownership: EngineOwnership,
        restartReason: String? = ConnectionPresentation.lastRestartReason
    ) -> String {
        switch accessError {
        case .staleBootstrapToken:
            return "The saved server token is out of date."
        case .tlsPinFailure:
            return "The server's certificate didn't match the pinned one."
        case .deviceAccessExpired:
            return "This device's access has expired. Pair with the Mac again to continue."
        case .forbidden:
            return "This account doesn't have access to that."
        case .unauthenticated:
            return "The server is running but didn't accept this app's sign-in."
        case .transport, .engineUnreachable, .none:
            break
        }
        if authBroken {
            return "The server is running but didn't accept this app's sign-in."
        }
        switch ownership {
        case .appManaged:
            // The supervisor is already respawning it (#4064/#4296) — say so
            // and let it happen rather than demanding a click.
            // Why, in words, when the heartbeat knows (`activity.engine.restart-says-why`).
            return restartReason.map { "\($0) Reconnecting…" } ?? "Fichero's engine stopped responding. Reconnecting…"
        case .externalLocal:
            // The truth, with no command attached: the app did not start this
            // engine and cannot restart it.
            return "The engine you started outside the app has stopped."
        case .remote:
            return "The Fichero server isn't responding right now."
        }
    }

    /// The one action worth offering for a failure.
    ///
    /// `.reconnect` and `.restartEngine` both run the SAME single retry entry
    /// point (#3108) — the difference is only what the app can honestly claim
    /// it is about to do. This is what makes the popover agree with the
    /// sidebar's "Live updates paused / Reconnect" pill instead of offering
    /// something different.
    static func failureAction(
        accessError: AccessError?,
        authBroken: Bool,
        ownership: EngineOwnership
    ) -> Action? {
        // Recoveries that only exist for an engine somebody else owns: the
        // app-managed engine mints its own credentials and pins its own
        // certificate, so offering to reset either would be theatre (#3944).
        if ownership != .appManaged {
            switch accessError?.recovery {
            case .signIn:
                return .resetSignIn
            case .resetPin:
                return .resetCertificate
            case .rePair:
                return .forgetPairing
            case .requestAccess, .grantAccess:
                // Nothing the app can do mints authorization; a folder grant is the library view's to offer.
                return nil
            case .restartEngine, .retry, .none:
                break
            }
            if authBroken { return .resetSignIn }
        } else if accessError?.recovery == .requestAccess {
            return nil
        }
        if ownership == .appManaged { return .restartEngine }
        return .reconnect
    }
}
