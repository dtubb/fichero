import Foundation
import OSLog

/// One logger for every WebContent-death report, so a console filter on the
/// category shows the whole picture across the reader, browser and canvases.
let webContentRecoveryLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "WebContentRecovery"
)

/// What to do when a `WKWebView`'s WebContent process dies.
///
/// WebKit renders in separate WebContent processes, and macOS kills or
/// crashes them for reasons entirely outside the app — memory pressure,
/// sandbox bootstrap races, GPU resets. Apple's documented contract is that
/// the app finds out via `webViewWebContentProcessDidTerminate(_:)` and is
/// responsible for recovery; a web view whose process died renders NOTHING
/// until something reloads it. Before this policy existed, no Fichero surface
/// implemented that callback, so a dead renderer meant a permanently blank
/// reader/preview pane until the user changed documents (empirically
/// reproduced 2026-08-04: a minimal sandboxed WKWebView host on macOS 26.3
/// had its WebContent process terminate once during startup with zero app
/// code involved — see docs/contributor/qa/known-launch-log-noise.md).
///
/// The policy is deliberately bounded: reload on termination, but never more
/// than `maxAttempts` times within `attemptWindow`. A renderer that dies the
/// moment it is relaunched is crash-looping — reloading it forever would turn
/// one blank pane into a CPU-burning storm of spawning-and-dying WebContent
/// processes. Attempts reset once a window passes without a death, so an
/// occasional kill days apart always recovers.
enum WebContentProcessRecovery {

    /// Reload budget per web view within `attemptWindow`.
    static let maxAttempts = 3
    /// A termination this long after the previous one starts a fresh budget.
    static let attemptWindow: TimeInterval = 60

    /// Per-web-view recovery bookkeeping. Owned by the coordinator that owns
    /// the web view, so two panes never share a budget.
    struct State: Equatable {
        var attempts = 0
        var lastTermination: Date?
    }

    /// Record a termination and decide whether to reload. Pure given `now`.
    static func shouldReload(_ state: inout State, now: Date = Date()) -> Bool {
        if let last = state.lastTermination, now.timeIntervalSince(last) > attemptWindow {
            state.attempts = 0
        }
        state.lastTermination = now
        state.attempts += 1
        return state.attempts <= maxAttempts
    }
}
