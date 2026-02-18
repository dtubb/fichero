import SwiftUI

/// View showing errors from workflow execution
struct ActivityErrorsView: View {
    let selectedRun: SelectedActivityRun
    let activityItems: [ActivityItem]
    let liveExecution: WorkflowExecution?

    /// Errors from live execution
    private var liveErrors: [(nodeId: String, file: String?, error: String)] {
        guard let execution = liveExecution else { return [] }
        var errors: [(nodeId: String, file: String?, error: String)] = []

        for (nodeId, state) in execution.nodeStates {
            if let error = state.errorMessage {
                errors.append((nodeId: nodeId, file: state.currentFile, error: error))
            }
        }

        for (file, progress) in execution.documentProgress {
            for (nodeId, status) in progress.stepStatuses {
                if case .failed(let error) = status, let errorMsg = error {
                    errors.append((nodeId: nodeId, file: file, error: errorMsg))
                }
            }
        }

        return errors
    }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 8) {
                if liveExecution != nil {
                    // Live errors
                    let errors = liveErrors
                    if errors.isEmpty {
                        noErrorsView
                    } else {
                        ForEach(errors.indices, id: \.self) { index in
                            errorRow(
                                nodeId: errors[index].nodeId,
                                file: errors[index].file,
                                error: errors[index].error
                            )
                        }
                    }
                } else if activityItems.isEmpty {
                    noErrorsView
                } else {
                    // Historical errors
                    ForEach(activityItems) { item in
                        historicalErrorRow(item)
                    }
                }
            }
            .padding()
        }
    }

    @ViewBuilder
    private var noErrorsView: some View {
        VStack(spacing: 8) {
            Image(systemName: "checkmark.circle")
                .font(.largeTitle)
                .foregroundStyle(.green)
            Text("No errors")
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    @ViewBuilder
    private func errorRow(nodeId: String, file: String?, error: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Image(systemName: "xmark.circle.fill")
                    .foregroundStyle(.red)

                Text(nodeId)
                    .font(.subheadline.bold())

                if let file = file {
                    Text("- \((file as NSString).lastPathComponent)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Text(error)
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(.secondary)
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.red.opacity(0.1), in: RoundedRectangle(cornerRadius: 6))
    }

    @ViewBuilder
    private func historicalErrorRow(_ item: ActivityItem) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Image(systemName: "xmark.circle.fill")
                    .foregroundStyle(.red)

                Text(item.message)
                    .font(.subheadline)
                    .lineLimit(2)

                Spacer()

                if let date = item.parsedTimestamp {
                    Text(date, style: .time)
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }
            }

            if let error = item.error {
                Text(error)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.red.opacity(0.1), in: RoundedRectangle(cornerRadius: 6))
    }
}

// MARK: - Preview

#Preview("No Errors") {
    ActivityErrorsView(
        selectedRun: .workflow(id: "test", batchId: nil),
        activityItems: [],
        liveExecution: nil
    )
    .frame(width: 600, height: 400)
}

#Preview("With Errors") {
    let mockItems = [
        ActivityItem(
            timestamp: "2024-01-15 10:30:00",
            level: "error",
            message: "Failed to transcribe document",
            source: "transcribe_node",
            error: "Connection timeout after 30 seconds"
        ),
        ActivityItem(
            timestamp: "2024-01-15 10:30:10",
            level: "error",
            message: "Document not found",
            source: "files_node",
            error: "File does not exist: /path/to/missing.pdf"
        )
    ]

    ActivityErrorsView(
        selectedRun: .workflow(id: "test", batchId: nil),
        activityItems: mockItems,
        liveExecution: nil
    )
    .frame(width: 600, height: 400)
}
