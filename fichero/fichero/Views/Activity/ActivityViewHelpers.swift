import SwiftUI

@MainActor
@Observable
final class ActivityWindowSelectionState {
    static let shared = ActivityWindowSelectionState()
    static let monitorWindowID = "activity-monitor"
    static let detailWindowID = "activity-detail"

    var selectedRun: SelectedActivityRun?

    func select(_ run: SelectedActivityRun?) {
        selectedRun = run
    }
}

/// Shared helper functions for Activity views
enum ActivityViewHelpers {

    enum RunAction {
        case pause
        case resume
        case stop
        case delete
    }

    // MARK: - Status Helpers

    static func statusIcon(for status: SelectedActivityRun.ActivityRunStatusType) -> String {
        switch status {
        case .running: return "play.circle.fill"
        case .paused: return "pause.circle.fill"
        case .completed: return "checkmark.circle.fill"
        case .failed: return "xmark.circle.fill"
        case .cancelled: return "stop.circle.fill"
        }
    }

    static func statusColor(for status: SelectedActivityRun.ActivityRunStatusType) -> Color {
        switch status {
        case .running: return .blue
        case .paused: return .orange
        case .completed: return .green
        case .failed: return .red
        case .cancelled: return .orange
        }
    }

    static func statusText(for status: SelectedActivityRun.ActivityRunStatusType) -> String {
        switch status {
        case .running: return "Running"
        case .paused: return "Paused"
        case .completed: return "Completed"
        case .failed: return "Failed"
        case .cancelled: return "Cancelled"
        }
    }

    static func selectedRunStatus(
        selectedRun: SelectedActivityRun,
        liveExecution: WorkflowExecution?,
        persistedRun: WorkflowRunResponse?
    ) -> SelectedActivityRun.ActivityRunStatusType {
        if let liveExecution {
            return selectedRunStatus(for: liveExecution.status)
        }
        if let persistedRun {
            return selectedRunStatus(forRaw: persistedRun.status)
        }
        return selectedRun.status
    }

    static func selectedRunStatus(for status: WorkflowStatus) -> SelectedActivityRun.ActivityRunStatusType {
        switch status {
        case .running, .idle:
            return .running
        case .paused:
            return .paused
        case .completed:
            return .completed
        case .failed:
            return .failed
        }
    }

    static func selectedRunStatus(forRaw raw: String) -> SelectedActivityRun.ActivityRunStatusType {
        switch raw.lowercased() {
        case "paused":
            return .paused
        case "completed", "complete", "success", "succeeded":
            return .completed
        case "failed", "error":
            return .failed
        case "cancelled", "canceled":
            return .cancelled
        default:
            return .running
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

    @MainActor
    static func performRunAction(
        _ action: RunAction,
        threadId: String,
        apiClient: APIClient
    ) async throws {
        let service = WorkflowExecutionService(
            baseURL: apiClient.baseURL,
            libraryPath: apiClient.currentLibraryPath
        )
        switch action {
        case .pause:
            try await service.pauseWorkflow(threadId: threadId)
        case .resume:
            _ = try await service.resumeWorkflow(threadId: threadId)
        case .stop:
            try await service.cancelWorkflow(threadId: threadId)
        case .delete:
            try await service.deleteThread(threadId: threadId)
        }
    }
}

// MARK: - Activity Browser

/// Two-column activity layout: this view is the left-column run list.
/// Fetches its own data so it doesn't depend on SidebarView state.
struct ActivityBrowserView: View {
    let selectedRunId: String?
    let onSelectRun: (SelectedActivityRun) -> Void
    var showsOpenWindowButton: Bool = true
    var opensDetailWindow: Bool = false

    @Environment(WorkflowExecutionObserver.self) private var executionObserver
    @Environment(ActivityStore.self) private var activityStore
    @Environment(LibraryManager.self) private var libraryManager
    @Environment(\.openWindow) private var openWindow
    @Environment(\.supportsMultipleWindows) private var supportsMultipleWindows
    @State private var selectionState = ActivityWindowSelectionState.shared

    // Run list + per-library failures now live on ActivityStore (#3231 p2); the
    // view observes them and calls rebuildRuns with its @Environment deps.
    @State private var listSelection: String?

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Activity")
                    .font(.headline)
                Spacer()
                if activityStore.isRebuildingRuns {
                    ProgressView().scaleEffect(0.6)
                }
                // Pop the live monitor into its own window (#2546 / B2). The
                // window's root is the hierarchical outline table. Hidden on
                // single-window platforms (iPhone) where it would be a dead
                // affordance (#2805).
                if showsOpenWindowButton && supportsMultipleWindows {
                    Button {
                        openWindow(id: ActivityWindowSelectionState.monitorWindowID)
                    } label: {
                        Label("Open Activity Monitor", systemImage: "arrow.up.forward.app")
                            .labelStyle(.iconOnly)
                    }
                    .buttonStyle(.borderless)
                    .accessibilityLabel("Open Activity Monitor")
                    .help("Open Activity Monitor in its own window")
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)

            Divider()

            if activityStore.runs.isEmpty && !activityStore.isRebuildingRuns {
                ContentUnavailableView(
                    "No Runs Yet",
                    systemImage: "clock",
                    description: Text("Run a workflow to see activity here")
                )
            } else {
                List(selection: $listSelection) {
                    ForEach(activityStore.runs) { run in
                        ActivityBrowserRow(
                            run: run,
                            showsDetailButton: opensDetailWindow && supportsMultipleWindows,
                            onOpenDetails: {
                                openDetails(for: run)
                            }
                        )
                            .tag(run.runId)
                            .listRowInsets(EdgeInsets(top: 4, leading: 8, bottom: 4, trailing: 8))
                            .listRowSeparator(.hidden)
                            .onTapGesture(count: 2) {
                                guard opensDetailWindow && supportsMultipleWindows else { return }
                                openDetails(for: run)
                            }
                    }
                }
                .listStyle(.plain)
                .onChange(of: listSelection) { _, newId in
                    guard let newId,
                          let run = activityStore.runs.first(where: { $0.runId == newId }) else { return }
                    onSelectRun(run.toSelectedRun())
                }
            }
        }
        .task { await reloadRuns() }
        // SSE-driven refresh: bumped by ActivityStore when activity events arrive
        .onChange(of: activityStore.refreshToken) { _, _ in
            Task { await reloadRuns() }
        }
        .onChange(of: selectedRunId) { _, newId in
            listSelection = newId
        }
        .onAppear { listSelection = selectedRunId }
        // No-silent-fallback (F7): if the activity SSE stream drops, the run list
        // stops refreshing — say so instead of showing a stale list silently.
        .overlay(alignment: .top) {
            VStack(spacing: 6) {
                if activityStore.liveUpdatesPaused {
                    LiveUpdatesPausedPill(onReconnect: { activityStore.reconnectLiveUpdates() })
                }
                // Live backend-work indicator (#2279): imports/batches/indexing
                // the engine or CLI kicked off out of band show here.
                if let work = activityStore.backendWork {
                    BackendWorkPill(status: work)
                }
                // Per-library history read failures (#3231): honest warning +
                // Retry instead of silently dropping that library's runs.
                ForEach(activityStore.runLoadFailures, id: \.self) { message in
                    HStack(spacing: 6) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundStyle(.orange)
                        Text(message)
                            .font(.caption)
                        Button("Retry") { Task { await reloadRuns() } }
                            .font(.caption)
                            .buttonStyle(.borderless)
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(.regularMaterial, in: Capsule())
                }
            }
        }
    }

    /// Rebuild the run list on the store from this window's live executions +
    /// the open libraries' history (#3231 p2). The store owns the merge; the view
    /// just feeds it the @Environment deps the store can't reach.
    private func reloadRuns() async {
        await activityStore.rebuildRuns(
            activeExecutions: Array(executionObserver.activeExecutions.values),
            openLibraries: libraryManager.openLibraries
        )
    }

    private func openDetails(for run: ActivityRun) {
        let selectedRun = run.toSelectedRun()
        selectionState.select(selectedRun)
        onSelectRun(selectedRun)
        openWindow(id: ActivityWindowSelectionState.detailWindowID)
    }
}

struct ActivityWindowLauncherView: View {
    let selectedRun: SelectedActivityRun?

    @Environment(\.openWindow) private var openWindow
    @State private var selectionState = ActivityWindowSelectionState.shared

    var body: some View {
        ContentUnavailableView(
            "Activity Lives in Its Own Window",
            systemImage: "arrow.up.forward.app",
            description: Text("Use the Activity window for run history, live updates, and details.")
        )
        .task(id: selectedRun?.id) {
            selectionState.select(selectedRun)
            openWindow(id: ActivityWindowSelectionState.monitorWindowID)
        }
    }
}

// MARK: - Activity Browser Row

private struct ActivityBrowserRow: View {
    let run: ActivityRun
    var showsDetailButton: Bool = false
    var onOpenDetails: (() -> Void)?

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: run.status.icon)
                .font(.body)
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

            if showsDetailButton, let onOpenDetails {
                Button(action: onOpenDetails) {
                    Image(systemName: "info.circle")
                        .font(.body)
                }
                .buttonStyle(.borderless)
                .accessibilityLabel("Open activity details")
                .help("Open activity details in a separate window")
            }
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
