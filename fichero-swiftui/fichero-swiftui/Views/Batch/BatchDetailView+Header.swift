import SwiftUI

extension BatchDetailView {
    @ViewBuilder
    var headerSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: displayBatch.statusIcon)
                    .font(.largeTitle)
                    .foregroundStyle(statusColor)

                VStack(alignment: .leading, spacing: 4) {
                    Text("Batch \(String(displayBatch.batchId.prefix(8)))")
                        .font(.title2.bold())
                        .monospaced()

                    HStack(spacing: 8) {
                        StatusBadge(status: batchStatus)

                        Text("Workflow: \(displayBatch.workflowId)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                Spacer()

                actionButtons
            }
        }
    }

    @ViewBuilder
    var actionButtons: some View {
        HStack(spacing: 8) {
            if displayBatch.status == "running" || displayBatch.status == "pending" {
                Button {
                    Task { await pauseBatch() }
                } label: {
                    Label("Pause", systemImage: "pause.fill")
                }
                .buttonStyle(.bordered)

                Button {
                    Task { await cancelBatch() }
                } label: {
                    Label("Cancel", systemImage: "stop.fill")
                }
                .buttonStyle(.bordered)
                .tint(.red)
            } else if displayBatch.status == "paused" {
                Button {
                    Task { await resumeBatch() }
                } label: {
                    Label("Resume", systemImage: "play.fill")
                }
                .buttonStyle(.borderedProminent)
            } else if displayBatch.status == "partial_failure" || displayBatch.failedItems > 0 {
                Button {
                    Task { await retryBatch() }
                } label: {
                    Label("Retry Failed", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.borderedProminent)
            }

            Button {
                Task { await refreshBatch() }
            } label: {
                Label("Refresh", systemImage: "arrow.clockwise")
            }
            .buttonStyle(.bordered)
            .disabled(isLoading)
        }
    }
}
