import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ScheduleRow")

/// Schedule action types
enum ScheduleAction {
    case pause
    case resume
    case trigger
    case delete
}

/// Reusable row view for a schedule
/// Used by AutomationSidebarContent and other automation-related views
struct ScheduleRow: View {
    let schedule: ScheduleInfo
    let onAction: (ScheduleAction) -> Void

    /// Compact mode hides some details for use in sidebar panels
    var compact: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: compact ? 6 : 8) {
            HStack {
                Image(systemName: schedule.statusIcon)
                    .foregroundColor(colorForStatus(schedule.status))

                Text(schedule.name)
                    .font(compact ? .subheadline.weight(.medium) : .headline)

                Spacer()

                Text(schedule.status.uppercased())
                    .font(.caption)
                    .fontWeight(.medium)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(colorForStatus(schedule.status).opacity(0.2))
                    .foregroundColor(colorForStatus(schedule.status))
                    .cornerRadius(4)
            }

            HStack(spacing: 16) {
                Label(schedule.scheduleDescription, systemImage: scheduleTypeIcon(schedule.scheduleType))
                    .font(.caption)
                    .foregroundColor(.secondary)

                if let nextRun = schedule.nextRunAt {
                    Label(nextRun, systemImage: "clock")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                if !compact {
                    Text("\(schedule.runCount) runs")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }

            if let error = schedule.errorMessage {
                Text(error)
                    .font(.caption)
                    .foregroundColor(.red)
                    .lineLimit(1)
            }

            // Actions (simplified in compact mode)
            if !compact {
                HStack {
                    Spacer()

                    if schedule.status == "active" {
                        Button("Pause") { onAction(.pause) }
                            .buttonStyle(.bordered)
                            .controlSize(.small)

                        Button("Run Now") { onAction(.trigger) }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                    } else if schedule.status == "paused" {
                        Button("Resume") { onAction(.resume) }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                    }

                    Button("Delete") { onAction(.delete) }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .tint(.red)
                }
            } else {
                // Compact: only show essential actions
                HStack {
                    Spacer()

                    if schedule.status == "active" {
                        Button("Pause") { onAction(.pause) }
                            .buttonStyle(.borderless)
                            .font(.caption)
                    } else if schedule.status == "paused" {
                        Button("Resume") { onAction(.resume) }
                            .buttonStyle(.borderless)
                            .font(.caption)
                    }
                }
            }
        }
        .padding(.vertical, compact ? 4 : 8)
    }

    private func colorForStatus(_ status: String) -> Color {
        switch status {
        case "active": return .green
        case "paused": return .yellow
        case "completed": return .gray
        case "error": return .red
        default: return .primary
        }
    }

    private func scheduleTypeIcon(_ type: String) -> String {
        switch type {
        case "cron": return "calendar.badge.clock"
        case "interval": return "repeat"
        case "once": return "calendar"
        default: return "clock"
        }
    }
}

// MARK: - Backward Compatibility Alias

/// Alias for backward compatibility with existing code
typealias ScheduleRowView = ScheduleRow
