import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ActivityDetailView")

/// Detail view for a selected activity run
/// Shows content based on sidebar selection (Console, Progress, Errors, or Overview)
struct ActivityDetailView: View {
    let selectedRun: SelectedActivityRun
    @Environment(APIClient.self) var apiClient
    @Environment(WorkflowExecutionObserver.self) private var executionObserver

    /// Shared live-execution store keyed by threadId (#2546). Optional so the
    /// view never crashes where the store isn't injected (e.g. previews); the
    /// store is registered on `LibraryReference` and injected by
    /// `LibraryWorkspaceRoot`.
    @Environment(WorkflowExecutionStore.self) private var executionStore: WorkflowExecutionStore?

    @State private var activityItems: [ActivityItem] = []
    @State private var isLoading = false
    @State private var error: String?
    @State private var workflowRun: WorkflowRunResponse?
    @State private var selectedSectionId: String = "overview"
    @State private var isActingOnRun = false

    private var liveExecution: WorkflowExecution? {
        if let threadId = selectedRun.threadId,
           let stored = executionStore?.execution(forThreadId: threadId) {
            return stored
        }
        guard let workflowId = selectedRun.workflowId else { return nil }
        return executionObserver.getExecution(for: workflowId)
    }

    /// Error count from live execution or activity items
    private var errorCount: Int {
        if let execution = liveExecution {
            return execution.nodeStates.values.reduce(0) { $0 + $1.errorCount }
        }
        // Count items with error level OR items that have an error field set
        return activityItems.filter { $0.level == "error" || $0.level == "critical" || $0.error != nil }.count
    }

    private var effectiveStatus: SelectedActivityRun.ActivityRunStatusType {
        ActivityViewHelpers.selectedRunStatus(
            selectedRun: selectedRun,
            liveExecution: liveExecution,
            persistedRun: workflowRun
        )
    }

    private var startedAt: Date {
        if let liveExecution {
            return liveExecution.startTime
        }
        if let parsed = WorkflowExecution.parseISODate(workflowRun?.startedAt) {
            return parsed
        }
        return selectedRun.timestamp
    }

    private var stoppedAt: Date? {
        if liveExecution?.isRunning == true || effectiveStatus == .paused {
            return nil
        }
        if let parsed = WorkflowExecution.parseISODate(workflowRun?.completedAt) {
            return parsed
        }
        return selectedRun.timestamp
    }

    var body: some View {
        VStack(spacing: 0) {
            // Stats bar (always visible)
            statsBar

            Divider()

            sectionBar

            Divider()

            contentView
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .task(id: selectedRun.id) {
            guard !Task.isCancelled else { return }
            selectedSectionId = sectionId(for: selectedRun.childType)
            subscribeToLiveExecutionIfRunning()
            await loadActivityDetails()
        }
    }

    @ViewBuilder
    private var sectionBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                sectionButton("overview", label: "Overview", icon: "list.bullet.rectangle")

                ForEach(ActivityChildType.allCases, id: \.self) { childType in
                    sectionButton(
                        childType.rawValue,
                        label: childType.label,
                        icon: childType.icon
                    )
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
        }
        .background(Color(platformColor: .windowBackgroundColor))
    }

    private func sectionButton(_ id: String, label: String, icon: String) -> some View {
        let isSelected = selectedSectionId == id

        return Button {
            selectedSectionId = id
        } label: {
            Label(label, systemImage: icon)
                .font(.caption)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(isSelected ? Color.accentColor.opacity(0.2) : Color.clear)
                )
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Stats bar
extension ActivityDetailView {
    @ViewBuilder
    private var statsBar: some View {
        HStack(spacing: 16) {
            // Status indicator
            HStack(spacing: 6) {
                if effectiveStatus == .running {
                    ProgressView()
                        .scaleEffect(0.7)
                        .frame(width: 14, height: 14)
                } else {
                    Circle()
                        .fill(ActivityViewHelpers.statusColor(for: effectiveStatus))
                        .frame(width: 10, height: 10)
                }

                Text(selectedRun.name)
                    .font(.headline)
                    .lineLimit(1)
            }

            Spacer()

            // Progress for running workflows
            if effectiveStatus == .running || effectiveStatus == .paused, let execution = liveExecution {
                progressStats(execution)
            }

            timingSummary

            // Error badge
            if errorCount > 0 {
                HStack(spacing: 4) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.orange)
                    Text("\(errorCount)")
                        .font(.caption.monospacedDigit())
                }
            }

            runControls
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.bar)
    }

    @ViewBuilder
    private var runControls: some View {
        if let threadId = selectedRun.threadId {
            HStack(spacing: 8) {
                switch effectiveStatus {
                case .running:
                    Button("Pause") {
                        Task { await performRunAction(.pause, threadId: threadId) }
                    }
                    .disabled(isActingOnRun)

                    Button("Stop") {
                        Task { await performRunAction(.stop, threadId: threadId) }
                    }
                    .disabled(isActingOnRun)
                case .paused:
                    Button("Resume") {
                        Task { await performRunAction(.resume, threadId: threadId) }
                    }
                    .disabled(isActingOnRun)

                    Button("Stop") {
                        Task { await performRunAction(.stop, threadId: threadId) }
                    }
                    .disabled(isActingOnRun)
                case .cancelled, .completed, .failed:
                    Button("Delete") {
                        Task { await performRunAction(.delete, threadId: threadId) }
                    }
                    .disabled(isActingOnRun)
                }
            }
            .font(.caption)
        }
    }

    private var timingSummary: some View {
        VStack(alignment: .trailing, spacing: 2) {
            Text(ActivityViewHelpers.statusText(for: effectiveStatus))
                .font(.caption.weight(.semibold))
                .foregroundStyle(ActivityViewHelpers.statusColor(for: effectiveStatus))

            Text("Started \(startedAt, format: .dateTime)")
                .font(.caption)
                .foregroundStyle(.secondary)

            if let stoppedAt {
                Text("Stopped \(stoppedAt, format: .dateTime)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private func progressStats(_ execution: WorkflowExecution) -> some View {
        HStack(spacing: 12) {
            // Progress bar
            if let progress = execution.overallProgress {
                HStack(spacing: 6) {
                    ProgressView(value: progress)
                        .frame(width: 100)

                    Text("\(Int(progress * 100))%")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
            }

            // File counts
            if execution.totalFiles > 0 {
                Text("\(execution.processedFiles)/\(execution.totalFiles)")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }

            // Current file
            if let fileName = execution.currentFileName {
                Text(fileName)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .frame(maxWidth: 150)
            }
        }
    }
}

// MARK: - Content & data loading
extension ActivityDetailView {
    @ViewBuilder
    private var contentView: some View {
        switch selectedChildType {
        case .console:
            ActivityConsoleView(
                selectedRun: selectedRun,
                activityItems: activityItems,
                liveExecution: liveExecution
            )
        case .progress:
            ActivityProgressView(
                selectedRun: selectedRun,
                liveExecution: liveExecution
            )
        case .log:
            ActivityLogView(
                selectedRun: selectedRun
            )
        case nil:
            // Overview - show summary of all sections
            ActivityOverviewView(
                selectedRun: selectedRun,
                activityItems: activityItems,
                liveExecution: liveExecution,
                errorCount: errorCount,
                effectiveStatus: effectiveStatus,
                startedAt: startedAt,
                stoppedAt: stoppedAt
            )
        }
    }

    private var selectedChildType: ActivityChildType? {
        selectedSectionId == "overview" ? nil : ActivityChildType(rawValue: selectedSectionId)
    }

    private func sectionId(for childType: ActivityChildType?) -> String {
        childType?.rawValue ?? "overview"
    }

    private func subscribeToLiveExecutionIfRunning() {
        guard selectedRun.status == .running,
              let threadId = selectedRun.threadId,
              let store = executionStore else { return }
        store.subscribe(
            threadId: threadId,
            workflowId: selectedRun.workflowId ?? selectedRun.id,
            name: selectedRun.name
        )
    }

    private func loadActivityDetails() async {
        guard !selectedRun.isLive else {
            // Live runs get data from observer, not API
            return
        }

        isLoading = true
        error = nil

        do {
            let activityService = ActivityService(apiClient: apiClient)

            // Load all activity events for this run
            // Prefer threadId (identifies a specific run) over workflowId
            if let threadId = selectedRun.threadId {
                workflowRun = try await activityService.getWorkflowRun(threadId: threadId)
                activityItems = try await activityService.getThreadActivities(
                    threadId: threadId,
                    limit: 500
                )
            } else if let workflowId = selectedRun.workflowId {
                workflowRun = nil
                activityItems = try await activityService.getWorkflowActivities(
                    workflowId: workflowId,
                    limit: 500
                )
            } else {
                workflowRun = nil
                // Fall back to querying by ID
                activityItems = try await activityService.queryActivities(
                    threadId: selectedRun.id,
                    limit: 500
                )
            }

            logger.info("Loaded \(activityItems.count) activity items for run \(selectedRun.id)")
        } catch {
            logger.error("Failed to load activity details: \(error.localizedDescription)")
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    private func performRunAction(_ action: ActivityViewHelpers.RunAction, threadId: String) async {
        isActingOnRun = true
        defer { isActingOnRun = false }
        do {
            try await ActivityViewHelpers.performRunAction(action, threadId: threadId, apiClient: apiClient)
        } catch {
            self.error = error.localizedDescription
        }
    }
}
