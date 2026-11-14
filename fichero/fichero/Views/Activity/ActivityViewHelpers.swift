import SwiftUI

/// The ONE Activity window's selection (`activity.window.is-the-pane-plus-inspector`): the window is a single `Window`
/// scene, so its selection is one too. `reveal` is a row Show in Activity asks the window to select; `pick` is what the
/// pane has selected, which the window's Inspector shows.
@MainActor
@Observable
final class ActivityWindowSelectionState {
    static let shared = ActivityWindowSelectionState()
    static let monitorWindowID = "activity-monitor"

    /// The row to select when the window shows it (a job id and its project).
    var reveal: ActivitySelection?
    /// The pane's selected row, for the Inspector.
    var pick: ActivityPaneSelection?

    /// Show in Activity: the window selects this row (the caller then opens the window).
    func select(_ selection: ActivitySelection?) { reveal = selection }
}

/// Shared helper functions for Activity views
enum ActivityViewHelpers {

    // MARK: - Level Helpers

    static func levelColor(_ level: String) -> Color {
        switch level {
        case "error", "critical": return .red
        case "warning": return .orange
        case "info": return .blue
        case "debug": return .secondary
        default: return .primary
        }
    }

    // MARK: - Duration Formatting

    static func formatDuration(_ milliseconds: Double) -> String {
        if milliseconds < 1000 {
            return String(format: "%.0fms", milliseconds)
        } else if milliseconds < 60000 {
            return String(format: "%.1fs", milliseconds / 1000)
        } else {
            let minutes = Int(milliseconds / 60000)
            let seconds = Int((milliseconds.truncatingRemainder(dividingBy: 60000)) / 1000)
            return "\(minutes)m \(seconds)s"
        }
    }

    // `performRunAction` (fire-and-forget, throwaway service, no state applied)
    // was retired in #4321 — run actions are transactional now: see
    // `WorkflowExecutionStore.perform(_:threadId:)` and `RunControls`.
}
