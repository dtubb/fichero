import Foundation

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
/// The sidebar builder's `reason:` tag is not gated: it rides an existing debug-level log line.
enum RenderDiagnostics {
    static let printChanges = ProcessInfo.processInfo.environment["FICHERO_PRINT_CHANGES"] == "1"
}
