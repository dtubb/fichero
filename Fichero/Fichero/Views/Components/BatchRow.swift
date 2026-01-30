import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "BatchRow")

/// Batch action types
enum BatchAction {
    case pause
    case cancel
    case delete
}

/// Reusable row view for a batch execution
/// Used by BatchesSidebarContent and other batch-related views
struct BatchRow: View {
    let batch: BatchInfo
    let onAction: (BatchAction) -> Void

    /// Compact mode hides some details for use in sidebar panels
    var compact: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: compact ? 6 : 8) {
            HStack {
                // Status icon
                Image(systemName: batch.statusIcon)
                    .foregroundColor(colorForStatus(batch.status))

                // Batch ID (truncated)
                Text(String(batch.batchId.prefix(8)))
                    .font(compact ? .subheadline.weight(.medium) : .headline)
                    .monospaced()

                Spacer()

                // Status badge
                Text(batch.status.uppercased())
                    .font(.caption)
                    .fontWeight(.medium)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(colorForStatus(batch.status).opacity(0.2))
                    .foregroundColor(colorForStatus(batch.status))
                    .cornerRadius(4)
            }

            // Progress bar
            ProgressView(value: batch.progressPercent, total: 100)
                .progressViewStyle(.linear)

            // Progress text
            HStack {
                Text("\(batch.completedItems)/\(batch.totalItems) completed")
                    .font(.caption)
                    .foregroundColor(.secondary)

                if batch.failedItems > 0 {
                    Text("\(batch.failedItems) failed")
                        .font(.caption)
                        .foregroundColor(.red)
                }

                Spacer()

                Text(String(format: "%.0f%%", batch.progressPercent))
                    .font(.caption)
                    .fontWeight(.medium)
            }

            // Actions (skip in compact mode if not running)
            if !compact || batch.status == "running" || batch.status == "pending" {
                if batch.status == "running" || batch.status == "pending" {
                    HStack {
                        Spacer()
                        Button("Pause") {
                            onAction(.pause)
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)

                        Button("Cancel") {
                            onAction(.cancel)
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .tint(.red)
                    }
                } else if !compact && batch.status != "running" {
                    HStack {
                        Spacer()
                        Button("Delete") {
                            onAction(.delete)
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .tint(.red)
                    }
                }
            }
        }
        .padding(.vertical, compact ? 4 : 8)
    }

    private func colorForStatus(_ status: String) -> Color {
        switch status {
        case "pending": return .gray
        case "running": return .blue
        case "paused": return .yellow
        case "completed": return .green
        case "partial_failure": return .orange
        case "failed": return .red
        case "cancelled": return .gray
        default: return .primary
        }
    }
}

// MARK: - Backward Compatibility Alias

/// Alias for backward compatibility with existing code
typealias BatchRowView = BatchRow
