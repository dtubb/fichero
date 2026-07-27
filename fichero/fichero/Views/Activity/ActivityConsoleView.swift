import SwiftUI

/// Console view showing activity log entries
struct ActivityConsoleView: View {
    let selectedRun: SelectedActivityRun
    let activityItems: [ActivityItem]
    let liveExecution: WorkflowExecution?

    private var sortedNodeStates: [NodeExecutionState] {
        liveExecution?.nodeStates.values.sorted(by: { $0.nodeId < $1.nodeId }) ?? []
    }

    var body: some View {
        List {
            if let execution = liveExecution {
                // Live execution - show node progress
                ForEach(sortedNodeStates, id: \.nodeId) { state in
                    nodeLogEntry(state)
                        .listRowInsets(EdgeInsets(top: 1, leading: 8, bottom: 1, trailing: 8))
                        .listRowSeparator(.hidden)
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
                    .listRowInsets(EdgeInsets(top: 1, leading: 8, bottom: 1, trailing: 8))
                    .listRowSeparator(.hidden)
                }
            } else if activityItems.isEmpty {
                Text("No console output available")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding()
                    .listRowSeparator(.hidden)
            } else {
                // Historical - show activity items as log entries
                ForEach(activityItems) { item in
                    activityLogEntry(item)
                        .listRowInsets(EdgeInsets(top: 1, leading: 8, bottom: 1, trailing: 8))
                        .listRowSeparator(.hidden)
                }
            }
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
        .background(Color(platformColor: .textBackgroundColor))
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

            Text(state.displayName ?? state.nodeId)
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
    let selectedRun = SelectedActivityRun(
        id: "test-run",
        name: "Test Workflow",
        workflowId: "workflow-123",
        threadId: "thread-456",
        timestamp: Date(),
        status: .running,
        isLive: false,
        childType: nil
    )

    ActivityConsoleView(
        selectedRun: selectedRun,
        activityItems: [],
        liveExecution: nil
    )
    .frame(width: 600, height: 400)
}

#Preview("With Logs") {
    let selectedRun = SelectedActivityRun(
        id: "test-run",
        name: "Test Workflow",
        workflowId: "workflow-123",
        threadId: "thread-456",
        timestamp: Date(),
        status: .running,
        isLive: false,
        childType: nil
    )

    let mockItems = [
        ActivityItem(
            id: "item-1",
            type: "log",
            level: "info",
            timestamp: "2024-01-15 10:30:00",
            message: "Starting workflow execution",
            workflowId: nil,
            batchId: nil,
            threadId: nil,
            nodeId: nil,
            metadataRaw: nil,
            durationMs: nil,
            error: nil
        ),
        ActivityItem(
            id: "item-2",
            type: "log",
            level: "error",
            timestamp: "2024-01-15 10:30:05",
            message: "Failed to process document",
            workflowId: nil,
            batchId: nil,
            threadId: nil,
            nodeId: nil,
            metadataRaw: nil,
            durationMs: nil,
            error: nil
        )
    ]

    ActivityConsoleView(
        selectedRun: selectedRun,
        activityItems: mockItems,
        liveExecution: nil
    )
    .frame(width: 600, height: 400)
}
