import SwiftUI

// MARK: - Helpers

extension WorkflowExecutionRow {

    var statusColor: Color {
        switch execution.status {
        case .idle: return .gray
        case .running: return .blue
        case .paused: return .orange
        case .completed: return .green
        case .failed: return .red
        }
    }

    var statusInfo: (String, Color) {
        switch execution.status {
        case .idle: return ("Idle", .gray)
        case .running: return ("Running", .blue)
        case .paused: return ("Paused", .orange)
        case .completed: return ("Completed", .green)
        case .failed: return ("Failed", .red)
        }
    }

    func nodeStatusInfo(_ state: NodeExecutionState) -> (String, Color) {
        switch state.status {
        case .idle: return ("circle", .gray)
        case .running, .parallelRunning: return ("play.circle", .blue)
        case .completed: return ("checkmark.circle.fill", .green)
        case .failed: return ("xmark.circle.fill", .red)
        }
    }

    func formatDuration(since startTime: Date) -> String {
        let duration = Date().timeIntervalSince(startTime)
        if duration < 60 {
            return String(format: "%.0fs", duration)
        } else if duration < 3600 {
            let mins = Int(duration / 60)
            let secs = Int(duration.truncatingRemainder(dividingBy: 60))
            return String(format: "%d:%02d", mins, secs)
        } else {
            return String(format: "%.1fh", duration / 3600)
        }
    }
}
