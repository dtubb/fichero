import SwiftUI

/// A schedule's run history — extracted from `ScheduleDetailView` (#4705
/// "4b-2", #4741) so the SAME rendering mounts from the Preview `.nodeDetail`
/// detail view AND the Reader's `.runHistory` surface: one renderer, two
/// mounts, zero duplication. Verbatim move from `ScheduleDetailView.
/// runHistorySection`/`runRow`/`runStatusColor`/`loadRuns` — no logic
/// rewrite, no restyle; only `schedule.scheduleId` became a plain
/// `scheduleId: String` parameter so this view has no dependency on the
/// whole `ScheduleInfo` the detail view owns.
struct ScheduleRunHistoryView: View {
    let scheduleId: String
    @Environment(APIClient.self) var apiClient

    @State private var isLoading = false
    @State private var error: String?
    @State private var runs: [ScheduleRunInfo] = []

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Run History")
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
            } else if runs.isEmpty {
                Text("No runs yet")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .italic()
            } else {
                ForEach(runs, id: \.runId) { run in
                    runRow(run)
                }
            }
        }
        // #4705 "4b-2": keyed on `scheduleId`, not a bare `.task` — the
        // Reader is a long-lived pane, so selecting schedule A then B must
        // reload, not keep showing A's rows under B's title (the classic
        // extraction-into-a-long-lived-host bug; `loadRuns()` below also
        // clears `runs` before the await for the same reason).
        .task(id: scheduleId) {
            guard !Task.isCancelled else { return }
            await loadRuns()
        }
    }

    @ViewBuilder
    private func runRow(_ run: ScheduleRunInfo) -> some View {
        HStack(spacing: 12) {
            Circle()
                .fill(runStatusColor(run.status))
                .frame(width: 8, height: 8)

            VStack(alignment: .leading, spacing: 2) {
                Text(run.startedAt)
                    .font(.subheadline)

                HStack(spacing: 8) {
                    Text(run.status)
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    if let batchId = run.batchId {
                        Text("Batch: \(batchId.prefix(8))...")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }

                if let error = run.error {
                    Text(error)
                        .font(.caption2)
                        .foregroundStyle(.red)
                        .lineLimit(2)
                }
            }

            Spacer()

            if let completed = run.completedAt {
                Text(completed)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(8)
        .background(Color(platformColor: .controlBackgroundColor))
        .cornerRadius(8)
    }

    private func runStatusColor(_ status: String) -> Color {
        switch status {
        case "completed": return .green
        case "running": return .blue
        case "failed": return .red
        default: return .secondary
        }
    }

    private func loadRuns() async {
        isLoading = true
        error = nil
        runs = []

        do {
            let service = AutomationService(apiClient: apiClient)
            let loaded = try await service.getScheduleRuns(scheduleId: scheduleId, limit: 20)
            // `.task(id:)` cancels this load when the id changes. A cancelled
            // load must not write: its rows belong to the PREVIOUS id, and its
            // CancellationError would otherwise show as an error over the new
            // id's rows (the view keeps its state across ids in Preview).
            guard !Task.isCancelled else { return }
            runs = loaded
        } catch {
            guard !Task.isCancelled else { return }
            self.error = error.localizedDescription
        }

        isLoading = false
    }
}

#Preview {
    ScheduleRunHistoryView(scheduleId: "test-1")
        .environment(APIClient())
        .frame(width: 500, height: 400)
}
