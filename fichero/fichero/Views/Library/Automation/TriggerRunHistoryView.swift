import SwiftUI

/// A trigger's execution history — extracted from `TriggerDetailView` (#4705
/// "4b-2", #4741) so the SAME rendering mounts from the Preview `.nodeDetail`
/// detail view AND the Reader's `.runHistory` surface: one renderer, two
/// mounts, zero duplication. Verbatim move from `TriggerDetailView.
/// executionHistorySection`/`executionRow`/`executionStatusColor`/
/// `loadExecutions` (`TriggerDetailView+ExecutionHistory.swift`/
/// `+Helpers.swift`) — no logic rewrite, no restyle; only
/// `trigger.triggerId` became a plain `triggerId: String` parameter so this
/// view has no dependency on the whole `TriggerInfo` the detail view owns.
struct TriggerRunHistoryView: View {
    let triggerId: String
    @Environment(APIClient.self) var apiClient

    @State private var isLoading = false
    @State private var error: String?
    @State private var executions: [TriggerExecutionInfo] = []

    var body: some View {
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
        // #4705 "4b-2": keyed on `triggerId`, not a bare `.task` — the
        // Reader is a long-lived pane, so selecting trigger A then B must
        // reload, not keep showing A's rows under B's title (the classic
        // extraction-into-a-long-lived-host bug; `loadExecutions()` below
        // also clears `executions` before the await for the same reason).
        .task(id: triggerId) {
            guard !Task.isCancelled else { return }
            await loadExecutions()
        }
    }

    @ViewBuilder
    private func executionRow(_ execution: TriggerExecutionInfo) -> some View {
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

    private func executionStatusColor(_ status: String) -> Color {
        switch status {
        case "completed": return .green
        case "running": return .blue
        case "failed": return .red
        default: return .secondary
        }
    }

    private func loadExecutions() async {
        isLoading = true
        error = nil
        executions = []

        do {
            let service = AutomationService(apiClient: apiClient)
            let loaded = try await service.getTriggerExecutions(triggerId: triggerId, limit: 20)
            // `.task(id:)` cancels this load when the id changes. A cancelled
            // load must not write: its rows belong to the PREVIOUS id, and its
            // CancellationError would otherwise show as an error over the new
            // id's rows (the view keeps its state across ids in Preview).
            guard !Task.isCancelled else { return }
            executions = loaded
        } catch {
            guard !Task.isCancelled else { return }
            self.error = error.localizedDescription
        }

        isLoading = false
    }
}

#Preview {
    TriggerRunHistoryView(triggerId: "test-1")
        .environment(APIClient())
        .frame(width: 500, height: 400)
}
