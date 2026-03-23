import SwiftUI
import OSLog

private let logger = Logger(subsystem: "com.tubb.Fichero", category: "ActivityDetailView")

/// Detail view for a selected activity run
/// Shows content based on sidebar selection (Console, Progress, Errors, or Overview)
struct ActivityDetailView: View {
    let selectedRun: SelectedActivityRun
    @EnvironmentObject var apiClient: APIClient
    @Environment(WorkflowExecutionObserver.self) private var executionObserver

    @State private var activityItems: [ActivityItem] = []
    @State private var isLoading = false
    @State private var error: String?

    /// Get the live execution if this run is currently active
    private var liveExecution: WorkflowExecution? {
        guard selectedRun.isLive else { return nil }
        return executionObserver.activeExecutions[selectedRun.id]
    }

    /// Error count from live execution or activity items
    private var errorCount: Int {
        if let execution = liveExecution {
            return execution.nodeStates.values.reduce(0) { $0 + $1.errorCount }
        }
        // Count items with error level OR items that have an error field set
        return activityItems.filter { $0.level == "error" || $0.level == "critical" || $0.error != nil }.count
    }

    var body: some View {
        VStack(spacing: 0) {
            // Stats bar (always visible)
            statsBar

            Divider()

            // Content based on selected child type
            contentView
        }
        .task {
            guard !Task.isCancelled else { return }
            await loadActivityDetails()
        }
        .onChange(of: selectedRun.id) { _, _ in
            Task {
                await loadActivityDetails()
            }
        }
    }

    // MARK: - Stats Bar

    @ViewBuilder
    private var statsBar: some View {
        HStack(spacing: 16) {
            // Status indicator
            HStack(spacing: 6) {
                if selectedRun.status == .running {
                    ProgressView()
                        .scaleEffect(0.7)
                        .frame(width: 14, height: 14)
                } else {
                    Circle()
                        .fill(ActivityViewHelpers.statusColor(for: selectedRun.status))
                        .frame(width: 10, height: 10)
                }

                Text(selectedRun.name)
                    .font(.headline)
                    .lineLimit(1)
            }

            Spacer()

            // Progress for running workflows
            if selectedRun.status == .running, let execution = liveExecution {
                progressStats(execution)
            }

            // Duration or timestamp
            if let execution = liveExecution, execution.isRunning {
                Text("Running \(execution.startTime, style: .relative)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                Text(selectedRun.timestamp, style: .relative)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            // Error badge
            if errorCount > 0 {
                HStack(spacing: 4) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.orange)
                    Text("\(errorCount)")
                        .font(.caption.monospacedDigit())
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.bar)
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

    // MARK: - Content View

    @ViewBuilder
    private var contentView: some View {
        switch selectedRun.childType {
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
        case .errors:
            ActivityErrorsView(
                selectedRun: selectedRun,
                activityItems: activityItems.filter {
                    $0.level == "error" || $0.level == "critical" || $0.error != nil
                },
                liveExecution: liveExecution
            )
        case .graph:
            ActivityGraphView(
                selectedRun: selectedRun
            )
        case .code:
            ActivityCodeView(
                selectedRun: selectedRun
            )
        case .diagram:
            ActivityDiagramView(
                selectedRun: selectedRun
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
                errorCount: errorCount
            )
        }
    }

    // MARK: - Data Loading

    private func loadActivityDetails() async {
        guard !selectedRun.isLive else {
            // Live runs get data from observer, not API
            return
        }

        isLoading = true
        error = nil

        do {
            let activityService = ActivityServiceGenerated(apiClient: apiClient)

            // Load all activity events for this run
            // Prefer threadId (identifies a specific run) over workflowId
            if let threadId = selectedRun.threadId {
                activityItems = try await activityService.getThreadActivities(
                    threadId: threadId,
                    limit: 500
                )
            } else if let workflowId = selectedRun.workflowId {
                activityItems = try await activityService.getWorkflowActivities(
                    workflowId: workflowId,
                    limit: 500
                )
            } else {
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
}

#Preview {
    ActivityDetailView(
        selectedRun: SelectedActivityRun(
            id: "test-1",
            name: "Test Workflow",
            workflowId: "workflow-1",
            threadId: "thread-1",
            timestamp: Date().addingTimeInterval(-3600),
            status: .completed,
            isLive: false,
            childType: nil
        )
    )
    .environmentObject(APIClient())
    .environment(WorkflowExecutionObserver())
    .frame(width: 600, height: 400)
}
