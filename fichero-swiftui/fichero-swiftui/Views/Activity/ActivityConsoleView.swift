import SwiftUI

/// Console view showing activity log entries
struct ActivityConsoleView: View {
    let selectedRun: SelectedActivityRun
    let activityItems: [ActivityItem]
    let liveExecution: WorkflowExecution?

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 4) {
                if let execution = liveExecution {
                    // Live execution - show node progress
                    ForEach(Array(execution.nodeStates.values.sorted(by: { $0.nodeId < $1.nodeId })), id: \.nodeId) { state in
                        nodeLogEntry(state)
                    }

                    // Current file being processed
                    if let fileName = execution.currentFileName {
                        HStack(spacing: 6) {
                            ProgressView()
                                .scaleEffect(0.5)
                            Text("Processing: \(fileName)")
                                .font(.system(.caption, design: .monospaced))
                                .foregroundStyle(.secondary)
                        }
                        .padding(.horizontal, 8)
                    }
                } else if activityItems.isEmpty {
                    Text("No console output available")
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .center)
                        .padding()
                } else {
                    // Historical - show activity items as log entries
                    ForEach(activityItems) { item in
                        activityLogEntry(item)
                    }
                }
            }
            .padding(8)
        }
        .background(Color(nsColor: .textBackgroundColor))
    }

    @ViewBuilder
    private func nodeLogEntry(_ state: NodeExecutionState) -> some View {
        HStack(spacing: 6) {
            // Status icon
            switch state.status {
            case .running, .parallelRunning:
                ProgressView()
                    .scaleEffect(0.5)
                    .frame(width: 12)
            case .completed:
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(.green)
                    .font(.caption)
            case .failed:
                Image(systemName: "xmark.circle.fill")
                    .foregroundStyle(.red)
                    .font(.caption)
            default:
                Image(systemName: "circle")
                    .foregroundStyle(.secondary)
                    .font(.caption)
            }

            Text(state.nodeId)
                .font(.system(.caption, design: .monospaced))

            if state.fileTotal > 0 {
                Text("[\(state.successCount)/\(state.fileTotal)]")
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.secondary)
            }

            if let error = state.errorMessage {
                Text("- \(error)")
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.red)
                    .lineLimit(1)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 2)
    }

    @ViewBuilder
    private func activityLogEntry(_ item: ActivityItem) -> some View {
        HStack(alignment: .top, spacing: 6) {
            // Timestamp
            if let date = item.parsedTimestamp {
                Text(date, format: .dateTime.hour().minute().second())
                    .font(.system(.caption2, design: .monospaced))
                    .foregroundStyle(.tertiary)
            }

            // Level indicator
            Image(systemName: item.typeIcon)
                .font(.caption)
                .foregroundStyle(ActivityViewHelpers.levelColor(item.level))

            // Message
            Text(item.message)
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(item.level == "error" ? .red : .primary)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 2)
    }
}

// MARK: - Preview

#Preview("Empty") {
    ActivityConsoleView(
        selectedRun: .workflow(id: "test", batchId: nil),
        activityItems: [],
        liveExecution: nil
    )
    .frame(width: 600, height: 400)
}

#Preview("With Logs") {
    let mockItems = [
        ActivityItem(
            timestamp: "2024-01-15 10:30:00",
            level: "info",
            message: "Starting workflow execution",
            source: "workflow_engine"
        ),
        ActivityItem(
            timestamp: "2024-01-15 10:30:05",
            level: "error",
            message: "Failed to process document",
            source: "transcribe_node"
        )
    ]

    ActivityConsoleView(
        selectedRun: .workflow(id: "test", batchId: nil),
        activityItems: mockItems,
        liveExecution: nil
    )
    .frame(width: 600, height: 400)
}
