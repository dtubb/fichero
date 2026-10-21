import FicheroAPIClient
import os
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

        /// Strategy → ownership for the surfaces that only render a TITLE.
        ///
        /// Delegates to the full `resolve(strategy:transportMode:portResolution:)`
        /// so there is exactly one derivation (#4400); a `nil` port resolution
        /// reads as "not adopted", which is what a launch that has not resolved
        /// a port yet honestly means. Surfaces that offer an ACTION must use
        /// `EmbeddedBackendService.connectionOwnership` instead — the live
        /// value knows whether this launch adopted somebody else's engine.
        static func resolve(
            _ strategy: EngineConfig.EngineProvisioningStrategy
        ) -> EngineOwnership {
            resolve(
                strategy: strategy,
                transportMode: EngineConfig.transportMode(for: strategy),
                portResolution: nil
            )
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
    /// Renamed from `Status` (#4380 follow-up): the generated client already
    /// declares `Components.Schemas.Status`, and two types one word apart —
    /// one an API payload, one a presentation model — cannot be told apart at
    /// a call site. `check_openapi_shadow_types` flags exactly that collision.
    struct Display: Equatable {
        /// Popover headline. Never narrates a step the app is not observing.
        let title: String
        /// The SAME state, written for the status island's ~260pt line
        /// (#4366). Length there is a contract: the island renders one
        /// truncating line, so a title written for a 380pt popover header
        /// arrives as a fragment. The line gets this; the popover gets
        /// `title`; the full sentence stays in `detail`.
        let shortTitle: String
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
    /// Characters that fit the status island's message line (#4366).
    ///
    /// Derived, not guessed: the island renders `.subheadline` inside
    /// `.frame(minWidth: 120, maxWidth: 260)` with `lineLimit(1)`. At ~11pt SF
    /// an average mixed-case advance is a shade under 6pt, so 260pt holds
    /// roughly 44 average characters — and rather less once a string leans on
    /// wide glyphs. 38 is that figure with margin, so a message at the budget
    /// still reads whole in the narrowest window the app supports.
    /// `StatusIslandMessageTests` asserts the island's declared width still
    /// matches the width this was derived from.
    static let islandBudget = 38
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
        authBroken: Bool,
        conflict: EngineSession.Conflict = .port8765
    ) -> Display {
        switch phase {
        case .setupNeeded:
            return Display(
                title: "Not Connected Yet",
                shortTitle: "Not connected",
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
            return Display(
                title: ownership == .appManaged ? "Starting the Fichero server…" : "Connecting…",
                shortTitle: ownership == .appManaged ? "Starting server…" : "Connecting…",
                detail: ownership == .appManaged
                    ? "Your projects run on a local server. This can take a few moments."
                    : "",
                symbol: "ellipsis.circle",
                isError: false,
                isRecovering: true,
                action: nil
            )

        case .ready:
            // #4391: a glyph can only HINT at local vs remote; the words here
            // settle it. Same ownership input every surface already receives,
            // so the island glyph, VoiceOver and this popover text agree
            // (#4380/#4400 single source). Local deliberately does not split
            // app-managed from external — "this Mac" is the fact the user
            // cares about; who may restart it is the Action layer's business.
            let isRemote = ownership == .remote
            return Display(
                title: "Connected",
                shortTitle: "Connected",
                detail: isRemote
                    ? "Connected to a Fichero server on another machine."
                    : "Connected to the Fichero server on this Mac.",
                symbol: isRemote
                    ? ToolbarSymbols.engineReadyRemote
                    : ToolbarSymbols.engineReadyLocal,
                isError: false,
                isRecovering: false,
                action: nil
            )

        case .portConflict where conflict != .port8765:
            return Display(
                title: "Another Fichero Is Running",
                shortTitle: "Another engine running",
                detail: conflict.sentence,
                symbol: "exclamationmark.triangle.fill",
                isError: true,
                isRecovering: false,
                action: .resolvePortConflict
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
            return Display(
                title: "Port 8765 Is In Use",
                shortTitle: "Port 8765 in use",
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
}
