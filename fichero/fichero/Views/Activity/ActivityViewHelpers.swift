import SwiftUI

/// Shared helper functions for Activity views
enum ActivityViewHelpers {

    // MARK: - Status Helpers

    static func statusIcon(for status: SelectedActivityRun.ActivityRunStatusType) -> String {
        switch status {
        case .running: return "play.circle.fill"
        case .completed: return "checkmark.circle.fill"
        case .failed: return "xmark.circle.fill"
        case .cancelled: return "stop.circle.fill"
        }
    }

    static func statusColor(for status: SelectedActivityRun.ActivityRunStatusType) -> Color {
        switch status {
        case .running: return .blue
        case .completed: return .green
        case .failed: return .red
        case .cancelled: return .orange
        }
    }

    static func statusText(for status: SelectedActivityRun.ActivityRunStatusType) -> String {
        switch status {
        case .running: return "Running"
        case .completed: return "Completed"
        case .failed: return "Failed"
        case .cancelled: return "Cancelled"
        }
    }

    // MARK: - Level Helpers

    static func levelColor(_ level: String) -> Color {
        switch level {
        case "error", "critical": return .red
        case "warning": return .orange
        case "info": return .blue
        case "debug": return .secondary
        default: return .primary
        }
    }

    // MARK: - Duration Formatting

    static func formatDuration(_ milliseconds: Double) -> String {
        if milliseconds < 1000 {
            return String(format: "%.0fms", milliseconds)
        } else if milliseconds < 60000 {
            return String(format: "%.1fs", milliseconds / 1000)
        } else {
            let minutes = Int(milliseconds / 60000)
            let seconds = Int((milliseconds.truncatingRemainder(dividingBy: 60000)) / 1000)
            return "\(minutes)m \(seconds)s"
        }
    }
}

// MARK: - Activity Browser

/// Two-column activity layout: this view is the left-column run list.
/// Fetches its own data so it doesn't depend on SidebarView state.
struct ActivityBrowserView: View {
    let selectedRunId: String?
    let onSelectRun: (SelectedActivityRun) -> Void

    @Environment(WorkflowExecutionObserver.self) private var executionObserver
    @Environment(ActivityStore.self) private var activityStore
    @EnvironmentObject private var libraryManager: LibraryManager
    @Environment(\.openWindow) private var openWindow

    @State private var runs: [ActivityRun] = []
    @State private var isLoading = false
    @State private var listSelection: String?

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Activity")
                    .font(.headline)
                Spacer()
                if isLoading {
                    ProgressView().scaleEffect(0.6)
                }
                // Pop the live monitor into its own window (#2546 / B2). The
                // window's root is the hierarchical outline table.
                Button {
                    openWindow(id: "activity-monitor")
                } label: {
                    Image(systemName: "arrow.up.forward.app")
                }
                .buttonStyle(.borderless)
                .help("Open Activity Monitor in its own window")
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)

            Divider()

            if runs.isEmpty && !isLoading {
                ContentUnavailableView(
                    "No Runs Yet",
                    systemImage: "clock",
                    description: Text("Run a workflow to see activity here")
                )
            } else {
                List(selection: $listSelection) {
                    ForEach(runs) { run in
                        ActivityBrowserRow(run: run)
                            .tag(run.runId)
                            .listRowInsets(EdgeInsets(top: 4, leading: 8, bottom: 4, trailing: 8))
                            .listRowSeparator(.hidden)
                    }
                }
                .listStyle(.plain)
                .onChange(of: listSelection) { _, newId in
                    guard let newId, let run = runs.first(where: { $0.runId == newId }) else { return }
                    onSelectRun(run.toSelectedRun())
                }
            }
        }
        .task { await loadRuns() }
        // SSE-driven refresh: bumped by ActivityStore when workflow events arrive
        .onChange(of: activityStore.refreshToken) { _, _ in
            Task { await loadRuns() }
        }
        // Live polling while runs are active; one delayed reload after completion
        // to pick up the `workflow_completed` backend record (#2448).
        .task(id: executionObserver.activeExecutions.isEmpty) {
            if executionObserver.activeExecutions.isEmpty {
                // Executions just drained — wait for the backend to write the
                // completion record before reloading (covers the DB-write race).
                try? await Task.sleep(for: .seconds(2))
                guard !Task.isCancelled else { return }
                await loadRuns()
            } else {
                // Active run: poll every 5 s to surface progress / status changes.
                while !Task.isCancelled && !executionObserver.activeExecutions.isEmpty {
                    await loadRuns()
                    try? await Task.sleep(for: .seconds(5))
                }
            }
        }
        .onChange(of: selectedRunId) { _, newId in
            listSelection = newId
        }
        .onAppear { listSelection = selectedRunId }
    }

    private func loadRuns() async {
        isLoading = true
        defer { isLoading = false }

        var result = executionObserver.activeExecutions.values.map { liveRunFromExecution($0) }
        let seenThreadIds = Set(result.map { $0.runId })
        let historical = await loadHistoricalRuns(excluding: seenThreadIds)
        result.append(contentsOf: historical)
        runs = result.sorted { $0.timestamp > $1.timestamp }
    }

    private func liveRunFromExecution(_ execution: WorkflowExecution) -> ActivityRun {
        ActivityRun(
            id: execution.threadId,
            runId: execution.threadId,
            workflowId: execution.id,
            threadId: execution.threadId,
            workflowName: activityCleanWorkflowName(execution.name),
            timestamp: execution.startTime,
            status: .running,
            progress: execution.overallProgress,
            currentStep: execution.currentNodeName,
            errorCount: execution.nodeStates.values.reduce(0) { $0 + $1.errorCount },
            fileCount: execution.totalFiles,
            isLive: true
        )
    }

    private func loadHistoricalRuns(excluding seenThreadIds: Set<String>) async -> [ActivityRun] {
        let types = ["workflow_completed", "workflow_failed", "workflow_cancelled"]
        let since = Date().addingTimeInterval(-7 * 24 * 3600)
        var result: [ActivityRun] = []
        for library in libraryManager.openLibraries {
            guard !Task.isCancelled else { break }
            do {
                let items = try await library.activityService.queryActivities(
                    types: types,
                    since: since,
                    limit: 100
                )
                for item in items {
                    let threadId = item.threadId ?? item.batchId.map { "batch:\($0)" }
                    guard let threadId, !seenThreadIds.contains(threadId) else { continue }
                    result.append(ActivityRun(
                        id: threadId,
                        runId: threadId,
                        workflowId: item.workflowId,
                        threadId: threadId,
                        workflowName: activityCleanWorkflowName(activityExtractWorkflowName(from: item)),
                        timestamp: item.parsedTimestamp ?? Date(),
                        status: activityMapActivityType(item.type),
                        progress: nil,
                        currentStep: nil,
                        errorCount: 0,
                        fileCount: 0,
                        isLive: false
                    ))
                }
            } catch {
                // Individual library failure is non-fatal
            }
        }
        return result
    }
}

// MARK: - Activity Browser Row

private struct ActivityBrowserRow: View {
    let run: ActivityRun

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: run.status.icon)
                .font(.system(size: 16))
                .foregroundStyle(run.status.color)
                .frame(width: 20)

            VStack(alignment: .leading, spacing: 2) {
                Text(run.workflowName)
                    .font(.subheadline)
                    .lineLimit(1)

                HStack(spacing: 4) {
                    if run.isLive {
                        Text(run.timestamp, style: .relative)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    } else {
                        Text(coarseTimeAgo(run.timestamp))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    if run.isLive, let progress = run.progress, progress > 0 {
                        ProgressView(value: progress)
                            .frame(maxWidth: 60)
                            .scaleEffect(y: 0.7)
                    }
                }
            }

            Spacer()
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
    }

    /// Stable coarse timestamp — does not update every second like Text(.relative).
    private func coarseTimeAgo(_ date: Date) -> String {
        let seconds = Int(-date.timeIntervalSinceNow)
        switch seconds {
        case ..<60:      return "just now"
        case ..<3600:    return "\(seconds / 60) min ago"
        case ..<86400:   return "\(seconds / 3600) hr ago"
        default:         return "\(seconds / 86400) days ago"
        }
    }
}
