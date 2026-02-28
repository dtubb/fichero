import SwiftUI

extension BatchDetailView {
    @ViewBuilder
    var configurationSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Configuration")
                .font(.headline)

            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible())
            ], alignment: .leading, spacing: 12) {
                configField("Batch ID", displayBatch.batchId)
                configField("Workflow", displayBatch.workflowId)
                configField("Max Concurrent", "\(displayBatch.maxConcurrent)")
                configField("Created", displayBatch.createdAt)

                if let startedAt = displayBatch.startedAt {
                    configField("Started", startedAt)
                }

                if let completedAt = displayBatch.completedAt {
                    configField("Completed", completedAt)
                }
            }
        }
    }

    @ViewBuilder
    func configField(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.body)
                .textSelection(.enabled)
        }
    }
}
