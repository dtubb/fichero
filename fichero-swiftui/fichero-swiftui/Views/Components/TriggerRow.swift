import OSLog
import SwiftUI

private let logger = Logger(subsystem: "com.tubb.Fichero", category: "TriggerRow")

/// Trigger action types
enum TriggerAction {
    case pause
    case resume
    case delete
}

/// Reusable row view for a file trigger
/// Used by AutomationSidebarContent and other automation-related views
struct TriggerRow: View {
    let trigger: TriggerInfo
    let onAction: (TriggerAction) -> Void

    /// Compact mode hides some details for use in sidebar panels
    var compact: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: compact ? 6 : 8) {
            HStack {
                Image(systemName: trigger.statusIcon)
                    .foregroundColor(colorForStatus(trigger.status))

                Text(trigger.name)
                    .font(compact ? .subheadline.weight(.medium) : .headline)

                Spacer()

                Text(trigger.status.uppercased())
                    .font(.caption)
                    .fontWeight(.medium)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(colorForStatus(trigger.status).opacity(0.2))
                    .foregroundColor(colorForStatus(trigger.status))
                    .cornerRadius(4)
            }

            HStack(spacing: 16) {
                Label(trigger.watchPath, systemImage: "folder")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .lineLimit(1)

                Label(trigger.eventsDescription, systemImage: "bolt")
                    .font(.caption)
                    .foregroundColor(.secondary)

                if !compact {
                    Text("\(trigger.triggerCount) triggered")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }

            if !compact {
                HStack(spacing: 16) {
                    Label(trigger.filterDescription, systemImage: "doc.text.magnifyingglass")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    if trigger.recursive {
                        Label("Recursive", systemImage: "arrow.triangle.branch")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }

            if let error = trigger.errorMessage {
                Text(error)
                    .font(.caption)
                    .foregroundColor(.red)
                    .lineLimit(1)
            }

            // Actions (simplified in compact mode)
            if !compact {
                HStack {
                    Spacer()

                    if trigger.status == "active" {
                        Button("Pause") { onAction(.pause) }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                    } else if trigger.status == "paused" {
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

                    if trigger.status == "active" {
                        Button("Pause") { onAction(.pause) }
                            .buttonStyle(.borderless)
                            .font(.caption)
                    } else if trigger.status == "paused" {
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
        case "error": return .red
        default: return .primary
        }
    }
}

// MARK: - Backward Compatibility Alias

/// Alias for backward compatibility with existing code
typealias TriggerRowView = TriggerRow
