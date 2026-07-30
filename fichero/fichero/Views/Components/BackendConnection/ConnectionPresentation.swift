import FicheroAPIClient
import SwiftUI

/// The ONE phase → presentation mapping every connection surface reads
/// (#4380, #4372).
///
/// Four surfaces used to answer the same question four different ways during a
/// single failure: the sidebar pill said "Live updates paused / Reconnect", the
/// engine popover said "Can't Connect to Server" and then narrated a startup
/// sequence it was not observing ("Starting Fichero → Opening the database… →
/// This can take a moment"), the popover's primary button offered a shell
/// command (`PYTHONPATH=src python -m fichero_server.api`) under a truncated
/// label, and the library pane spun a spinner forever. Three of those were
/// invented; the fourth outlived the failure.
///
/// The rule this type encodes: **say only what is known; offer only what
/// actually works.** Every string and every offered action is derived from the
/// engine's actual `EngineSession.Phase` plus who owns the engine process —
/// nothing else. There is no progress narration, because the app is not
/// observing the engine's internal startup steps, and no shell command,
/// because pasting one into Terminal is not a user action.
///
/// Pure and static on purpose, exactly like `StatusIslandMessage.resolve`: the
/// precedence between phases is real logic with real branches, and keeping it
/// out of the view bodies is what makes it assertable without an engine, a
/// store, or a rendered environment. The test that pins every phase to its
/// message and action is the thing that stops the surfaces drifting apart
/// again.
enum ConnectionPresentation {

    // MARK: - Who owns the engine process

    /// Whether the app can honestly offer to restart the engine.
    ///
    /// This is the difference between "Restart Engine" being a real action and
    /// being a lie. The app only owns the process in the embedded build; in
    /// every other configuration somebody else started the engine, and the
    /// only thing the app can do is try to connect again.
    enum EngineOwnership: Equatable {
        /// The app spawned and supervises the bundled engine — it can restart it.
        case appManaged
        /// A developer started the engine outside the app (macOS Debug), or the
        /// app is running inert. The app can connect, never restart.
        case externalLocal
        /// A configured remote host or a paired Mac. Another machine entirely.
        case remote

        /// Pure: strategy → ownership, so the release-vs-debug-vs-remote
        /// branching is testable without a launch or a build flag.
        static func resolve(
            _ strategy: EngineConfig.EngineProvisioningStrategy
        ) -> EngineOwnership {
            if strategy.spawnsBundledEngine { return .appManaged }
            if strategy.connectsToRemoteHost { return .remote }
            return .externalLocal
        }

        /// The live ownership for this build/launch. Impure boundary around
        /// `resolve(_:)`, mirroring `EngineConfig.engineProvisioningStrategy()`.
        static func current() -> EngineOwnership {
            resolve(EngineConfig.engineProvisioningStrategy())
        }
    }

    // MARK: - The one action a surface offers

    /// The single primary action a connection surface may offer.
    ///
    /// One case per thing that actually helps. There is deliberately no
    /// `.runShellCommand` case: developer detail belongs behind Show Log.
    enum Action: Equatable {
        /// Try the connection again — the one retry entry point (#3108).
        case reconnect
        /// Respawn the engine the app owns (also the one retry entry point,
        /// which respawns a wedged embedded engine).
        case restartEngine
        /// Port 8765 is held by somebody else; the popover offers the in-window
        /// three-way decision (#3111/#3749).
        case resolvePortConflict
        /// Clear a stale saved sign-in and connect again (#2864).
        case resetSignIn
        /// Clear a mismatched pinned certificate and connect again.
        case resetCertificate
        /// The paired host is gone; re-pair from scratch (#3971).
        case forgetPairing

        /// Button label. Length is a CONTRACT (#4366), not a styling accident:
        /// "Start Exte…" is the bug this replaces. Asserted against
        /// `Self.labelBudget` by the mapping test.
        var title: String {
            switch self {
            case .reconnect: return "Reconnect"
            case .restartEngine: return "Restart Engine"
            case .resolvePortConflict: return "Resolve Conflict"
            case .resetSignIn: return "Reset Sign-In"
            case .resetCertificate: return "Reset Certificate"
            case .forgetPairing: return "Forget This Mac"
            }
        }

        var systemImage: String {
            switch self {
            case .reconnect: return "arrow.clockwise"
            case .restartEngine: return "arrow.clockwise"
            case .resolvePortConflict: return "stop.circle"
            case .resetSignIn: return "person.badge.key"
            case .resetCertificate: return "lock.rotation"
            case .forgetPairing: return "xmark.circle"
            }
        }
    }

    // MARK: - What a surface renders

    /// One honest status: a short title, one sentence of detail, one small
    /// symbol, and at most one primary action.
    struct Status: Equatable {
        /// Short headline. Never narrates a step the app is not observing.
        let title: String
        /// One plain sentence: what happened, and whether the app is already
        /// retrying. Empty when there is nothing true to add.
        let detail: String
        /// A single small SF Symbol beside the title — consistent with the
        /// status island's error affordance. Never an illustration.
        let symbol: String
        /// Render the title/symbol in the error tint.
        let isError: Bool
        /// The app is already working on it (starting, or the heartbeat is
        /// re-probing and will lower the alarm on its own, #4296). Surfaces
        /// show a small spinner and let it happen instead of demanding a click.
        let isRecovering: Bool
        /// The one thing worth offering, or nil when nothing the app can do
        /// would help.
        let action: Action?
    }

    /// Button labels must fit their control at the narrowest supported window.
    static let labelBudget = 20
    /// Status titles must fit a 360pt popover header and the status island's
    /// 260pt message area. The longest is "Fichero Couldn't Authenticate to Its
    /// Server" at 43 characters; nothing may grow past it without shrinking the
    /// whole table first.
    static let titleBudget = 44
    /// One sentence, not a paragraph — the rest belongs behind Show Log.
    static let detailBudget = 140

    // MARK: - The mapping

    /// Phase (+ who owns the engine, + the classified access error) → the one
    /// presentation every surface renders.
    static func status(
        phase: EngineSession.Phase,
        ownership: EngineOwnership,
        accessError: AccessError?,
        authBroken: Bool
    ) -> Status {
        switch phase {
        case .setupNeeded:
            return Status(
                title: "Not Connected Yet",
                detail: "Choose a Fichero server to connect to.",
                symbol: "link.badge.plus",
                isError: false,
                isRecovering: false,
                action: nil
            )

        case .starting:
            // The app knows it is connecting. It does NOT know whether the
            // engine is importing libraries or opening its database, so it says
            // neither (#4380).
            return Status(
                title: ownership == .appManaged ? "Starting engine…" : "Connecting…",
                detail: "",
                symbol: "ellipsis.circle",
                isError: false,
                isRecovering: true,
                action: nil
            )

        case .ready:
            return Status(
                title: "Connected",
                detail: "",
                symbol: "checkmark.circle",
                isError: false,
                isRecovering: false,
                action: nil
            )

        case .portConflict(let pid):
            // Under the App Sandbox the holder's PID is unknowable (#3749) —
            // the copy names it when we know it and never invents one when we
            // don't.
            let who: String
            if let pid {
                who = "Another process (PID \(pid))"
            } else {
                who = "Another process"
            }
            return Status(
                title: "Port 8765 Is In Use",
                detail: "\(who) is already using port 8765.",
                symbol: "exclamationmark.triangle.fill",
                isError: true,
                isRecovering: false,
                action: .resolvePortConflict
            )

        case .authRejected, .unreachable, .failed:
            return failureStatus(
                accessError: accessError,
                authBroken: authBroken,
                ownership: ownership
            )
        }
    }

    /// The failure half of the mapping, split out so `status(…)` stays one
    /// bounded switch.
    private static func failureStatus(
        accessError: AccessError?,
        authBroken: Bool,
        ownership: EngineOwnership
    ) -> Status {
        let title = failureTitle(
            accessError: accessError,
            authBroken: authBroken,
            ownership: ownership
        )
        return Status(
            title: title,
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

    /// One plain sentence. Derived from ownership, never from a raw transport
    /// error string — `HTTPClientError.deadlineExceeded` in a content pane is
    /// exactly what #4269 forbids, and a `PYTHONPATH=…` invocation is not a
    /// user action (#4380). Both live in the engine log, reachable via Show Log.
    static func failureDetail(
        accessError: AccessError?,
        authBroken: Bool,
        ownership: EngineOwnership
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
            return "Fichero's engine stopped responding. Reconnecting…"
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
            case .requestAccess:
                // Nothing the app can do mints authorization.
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

// MARK: - Library content loading (#4372)

/// What the library content area is honestly doing right now.
///
/// "Connecting to the library" and "loading its documents" are DIFFERENT
/// states, and the pane used to render both strings at once — a "Loading
/// Documents…" headline over a "Connecting to library data" subtitle — while a
/// third spinner spun forever whenever the engine never answered. One phase,
/// one line.
enum LibraryLoadPhase: Equatable {
    /// Talking to a server we do not own yet — no documents have been asked for.
    case connecting
    /// The app is bringing up the engine it owns.
    case startingEngine
    /// Connected; the tree/collection fetch is in flight.
    case loadingDocuments
    /// A final answer: there is nothing here. The empty state, not a spinner.
    case empty
    /// A final answer with rows.
    case loaded
    /// Something failed. The error affordance, NEVER a spinner.
    case failed(message: String)

    /// The one short line shown beside the spinner. Nil for the states that
    /// have their own dedicated view (empty / loaded / failed).
    var message: String? {
        switch self {
        case .connecting: return "Connecting…"
        case .startingEngine: return "Starting engine…"
        case .loadingDocuments: return "Loading documents…"
        case .empty, .loaded, .failed: return nil
        }
    }

    /// A spinner means "wait, this is coming". It is a lie in every other state.
    var showsSpinner: Bool { message != nil }

    /// Phase precedence: a failure outranks everything (a spinner over a dead
    /// engine is the #4372 bug), then the engine's own readiness, then the
    /// collection fetch, and only then the empty/loaded answer.
    ///
    /// - Parameters:
    ///   - enginePhase: the single connection-state source.
    ///   - ownership: decides "Starting engine…" vs "Connecting…".
    ///   - hasLoadedSuccessfully: a collection load has succeeded at least once.
    ///   - isFetching: a collection load is in flight.
    ///   - isEmpty: the loaded collection has no rows.
    ///   - engineDetail: the honest engine-failure sentence, supplied by
    ///     `ConnectionPresentation` so both surfaces read the same words.
    ///   - loadErrorMessage: a collection-level failure message, if any.
    static func resolve(
        enginePhase: EngineSession.Phase,
        ownership: ConnectionPresentation.EngineOwnership,
        hasLoadedSuccessfully: Bool,
        isFetching: Bool,
        isEmpty: Bool,
        engineDetail: String,
        loadErrorMessage: String?
    ) -> LibraryLoadPhase {
        switch enginePhase {
        case .portConflict, .authRejected, .unreachable, .failed:
            return .failed(message: engineDetail)
        case .setupNeeded:
            return .connecting
        case .starting:
            return ownership == .appManaged ? .startingEngine : .connecting
        case .ready:
            break
        }
        if let loadErrorMessage { return .failed(message: loadErrorMessage) }
        if isFetching || !hasLoadedSuccessfully { return .loadingDocuments }
        return isEmpty ? .empty : .loaded
    }
}
