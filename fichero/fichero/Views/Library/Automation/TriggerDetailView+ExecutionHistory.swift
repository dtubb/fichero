import SwiftUI

extension TriggerDetailView {

    // MARK: - Execution History Section

    @ViewBuilder
    var executionHistorySection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Execution History")
                    .font(.headline)

                Spacer()

                if isLoading {
                    ProgressView()
                        .scaleEffect(0.7)
                }
            }

            if let error = error {
                HStack {
                    Image(systemName: "exclamationmark.triangle")
                        .foregroundStyle(.orange)
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            } else if executions.isEmpty {
                Text("No executions yet")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .italic()
            } else {
                ForEach(executions) { execution in
                    executionRow(execution)
                }
            }
        }
    }

    @ViewBuilder
    func executionRow(_ execution: TriggerExecutionInfo) -> some View {
        HStack(spacing: 12) {
            Circle()
                .fill(executionStatusColor(execution.status))
                .frame(width: 8, height: 8)

            VStack(alignment: .leading, spacing: 2) {
                Text(execution.triggeredAt)
                    .font(.subheadline)

                HStack(spacing: 8) {
                    Text(execution.status)
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    if !execution.filePaths.isEmpty {
                        Text("\(execution.filePaths.count) file(s)")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }

                    if let batchId = execution.batchId {
                        Text("Batch: \(String(batchId.prefix(8)))...")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }

                if let error = execution.error {
                    Text(error)
                        .font(.caption2)
                        .foregroundStyle(.red)
                        .lineLimit(2)
                }
            }

            Spacer()

            if let completed = execution.completedAt {
                Text(completed)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(8)
        .background(Color(platformColor: .controlBackgroundColor))
        .cornerRadius(8)
    }
}
