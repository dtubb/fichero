import Foundation
import OSLog

/// Opt-in render diagnostics for a slowdown investigation: launch with
/// `FICHERO_PRINT_CHANGES=1` (Xcode scheme → Run → Arguments → Environment Variables).
///
/// Read ONCE per process. Unset, every call site is a single `Bool` test — no logging, no
/// string building, no `_printChanges()`.
///
/// What it turns on:
/// - `ContentView.body` prints which property made it re-evaluate (`Self._printChanges()`).
/// - `SidebarView` logs when it appears and disappears — a disappear/appear pair on a click is a
///   re-mount, which replays the sidebar's whole `.task` (every library's activity, workflows,
///   automation) and resets its selection bookkeeping.
/// - `SidebarView.handleSelectionChange` logs WHY it ran (a live click, or a restored-selection
///   reconcile).
///
/// - `BodyCount` tallies the `body` evaluations of the main views and the row types, and logs
///   one line per run-loop turn that re-evaluated many of them: which views, how many times. A
///   click or a resize frame that rebuilds the window says what it rebuilt.
///
/// The sidebar builder's `reason:` tag is not gated: it rides an existing debug-level log line.
enum RenderDiagnostics {
    static let printChanges = ProcessInfo.processInfo.environment["FICHERO_PRINT_CHANGES"] == "1"
}

private let bodyCountLogger = Logger(subsystem: "app.fichero.fichero", category: "BodyCount")

/// Per-turn `body` evaluation counts, on only with `FICHERO_PRINT_CHANGES=1`.
///
/// A view calls `BodyCount.tick("Name")` at the top of its `body`. The first tick of a turn queues
/// one block on the main queue, which runs in the next turn, after the update that evaluated
/// those bodies, and logs the tally if it is large enough to matter.
@MainActor
enum BodyCount {
    /// Below this many evaluations in one turn a line is noise: a hover, a single row.
    static let reportThreshold = 20

    private static var tally: [String: Int] = [:]
    private static var flushQueued = false

    static func tick(_ name: String) {
        guard RenderDiagnostics.printChanges else { return }
        tally[name, default: 0] += 1
        guard !flushQueued else { return }
        flushQueued = true
        DispatchQueue.main.async {
            MainActor.assumeIsolated { flush() }
        }
    }

    private static func flush() {
        let counts = tally
        tally = [:]
        flushQueued = false
        guard let line = summary(counts, threshold: reportThreshold) else { return }
        bodyCountLogger.info("◆ bodies this turn: \(line, privacy: .public)")
    }

    /// "142 · SidebarItemRow 120 · LibraryView 2", largest first, names breaking ties; nil when
    /// the turn evaluated fewer than `threshold` bodies.
    nonisolated static func summary(_ counts: [String: Int], threshold: Int) -> String? {
        let total = counts.values.reduce(0, +)
        guard total >= threshold else { return nil }
        let ranked = counts.sorted { $0.value != $1.value ? $0.value > $1.value : $0.key < $1.key }
        return ([String(total)] + ranked.map { "\($0.key) \($0.value)" }).joined(separator: " · ")
    }
}
