import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ActivityMonitorView")

/// Main activity monitor view showing real-time workflow and batch activity
struct ActivityMonitorView: View {
    @EnvironmentObject var apiClient: APIClient
    @Environment(WorkflowExecutionObserver.self) var executionObserver

    @State private var activities: [ActivityItem] = []
    @State private var stats: ActivityStats?
    @State private var batches: [BatchInfo] = []
    @State private var selectedTab: ActivityTab = .activities
    @State private var isLoading = false
    @State private var searchText = ""
    @State private var selectedLevel: String?
    @State private var autoRefresh = true

    private var activityService: ActivityService { ActivityService(apiClient: apiClient) }
    private let refreshTimer = Timer.publish(every: 5, on: .main, in: .common).autoconnect()

    enum ActivityTab: String, CaseIterable {
        case running = "Running"
        case activities = "History"
        case batches = "Batches"
        case stats = "Statistics"
    }

    var body: some View {
        VStack(spacing: 0) {
            // Tab picker
            Picker("View", selection: $selectedTab) {
                ForEach(ActivityTab.allCases, id: \.self) { tab in
                    HStack {
                        Text(tab.rawValue)
                        if tab == .running && executionObserver.isAnyWorkflowRunning {
                            Circle()
                                .fill(Color.green)
                                .frame(width: 6, height: 6)
                        }
                    }
                    .tag(tab)
                }
            }
            .pickerStyle(.segmented)
            .padding()

            // Content based on selected tab
            switch selectedTab {
            case .running:
                runningWorkflowsView
            case .activities:
                activitiesView
            case .batches:
                batchesView
            case .stats:
                statsView
            }
        }
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Toggle(isOn: $autoRefresh) {
                    Image(systemName: autoRefresh ? "arrow.clockwise.circle.fill" : "arrow.clockwise.circle")
                }
                .help(autoRefresh ? "Auto-refresh enabled" : "Auto-refresh disabled")
            }

            ToolbarItem(placement: .automatic) {
                Button {
                    Task { await refresh() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .disabled(isLoading)
            }
        }
        .task {
            guard !Task.isCancelled else { return }
            await refresh()
        }
        .onReceive(refreshTimer) { _ in
            if autoRefresh {
                Task { await refresh() }
            }
        }
    }

    // MARK: - Running Workflows View

    @ViewBuilder
    private var runningWorkflowsView: some View {
        let executions = Array(executionObserver.activeExecutions.values)

        if executions.isEmpty {
            ContentUnavailableView(
                "No Running Workflows",
                systemImage: "play.slash",
                description: Text("Run a workflow to see real-time progress here")
            )
        } else {
            List(executions, id: \.id) { execution in
                RunningWorkflowRow(execution: execution)
            }
        }
    }

    // MARK: - Activities View

    @ViewBuilder
    private var activitiesView: some View {
        VStack(spacing: 0) {
            // Search and filter bar
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(.secondary)
                TextField("Search activities...", text: $searchText)
                    .textFieldStyle(.plain)

                Picker("Level", selection: $selectedLevel) {
                    Text("All Levels").tag(nil as String?)
                    Text("Errors").tag("error" as String?)
                    Text("Warnings").tag("warning" as String?)
                    Text("Info").tag("info" as String?)
                }
                .frame(width: 120)
            }
            .padding(8)
            .background(Color(.controlBackgroundColor))

            Divider()

            if isLoading && activities.isEmpty {
                ProgressView("Loading activities...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if filteredActivities.isEmpty {
                ContentUnavailableView(
                    "No Activities",
                    systemImage: "chart.line.uptrend.xyaxis",
                    description: Text("No activities match your filter criteria")
                )
            } else {
                List(filteredActivities) { activity in
                    ActivityRowView(activity: activity)
                }
            }
        }
    }

    private var filteredActivities: [ActivityItem] {
        var result = activities

        if !searchText.isEmpty {
            result = result.filter { activity in
                activity.message.localizedCaseInsensitiveContains(searchText)
            }
        }

        if let level = selectedLevel {
            result = result.filter { $0.level == level }
        }

        return result
    }

    // MARK: - Batches View

    @ViewBuilder
    private var batchesView: some View {
        if isLoading && batches.isEmpty {
            ProgressView("Loading batches...")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if batches.isEmpty {
            ContentUnavailableView(
                "No Batches",
                systemImage: "square.stack.3d.up",
                description: Text("No batch executions have been created yet")
            )
        } else {
            List(batches) { batch in
                BatchRowView(batch: batch, onAction: { action in
                    Task { await handleBatchAction(batch: batch, action: action) }
                })
            }
        }
    }

    // MARK: - Stats View

    @ViewBuilder
    private var statsView: some View {
        if let stats = stats {
            ScrollView {
                VStack(spacing: 20) {
                    // Summary cards
                    HStack(spacing: 16) {
                        StatCard(
                            title: "Total Activities",
                            value: "\(stats.totalActivities)",
                            icon: "chart.bar.fill",
                            color: .blue
                        )
                        StatCard(
                            title: "Success Rate",
                            value: String(format: "%.1f%%", stats.successRate),
                            icon: "checkmark.circle.fill",
                            color: .green
                        )
                        StatCard(
                            title: "Errors",
                            value: "\(stats.errorCount)",
                            icon: "xmark.circle.fill",
                            color: .red
                        )
                        StatCard(
                            title: "Warnings",
                            value: "\(stats.warningCount)",
                            icon: "exclamationmark.triangle.fill",
                            color: .orange
                        )
                    }
                    .padding(.horizontal)

                    // Average duration
                    if let avgDuration = stats.avgWorkflowDurationMs {
                        HStack {
                            Image(systemName: "clock")
                            Text("Average Workflow Duration: \(formatDuration(avgDuration))")
                        }
                        .font(.headline)
                        .padding()
                        .background(Color(.controlBackgroundColor))
                        .cornerRadius(8)
                    }

                    // Activity by type breakdown
                    if !stats.activitiesByType.isEmpty {
                        GroupBox("Activities by Type") {
                            VStack(alignment: .leading, spacing: 8) {
                                ForEach(stats.activitiesByType.sorted(by: { $0.value > $1.value }), id: \.key) { type, count in
                                    HStack {
                                        Text(formatActivityType(type))
                                        Spacer()
                                        Text("\(count)")
                                            .foregroundColor(.secondary)
                                    }
                                }
                            }
                            .padding()
                        }
                        .padding(.horizontal)
                    }

                    // Activity by level breakdown
                    if !stats.activitiesByLevel.isEmpty {
                        GroupBox("Activities by Level") {
                            VStack(alignment: .leading, spacing: 8) {
                                ForEach(stats.activitiesByLevel.sorted(by: { $0.value > $1.value }), id: \.key) { level, count in
                                    HStack {
                                        Circle()
                                            .fill(colorForLevel(level))
                                            .frame(width: 8, height: 8)
                                        Text(level.capitalized)
                                        Spacer()
                                        Text("\(count)")
                                            .foregroundColor(.secondary)
                                    }
                                }
                            }
                            .padding()
                        }
                        .padding(.horizontal)
                    }
                }
                .padding(.vertical)
            }
        } else {
            ProgressView("Loading statistics...")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    // MARK: - Actions

    private func refresh() async {
        isLoading = true
        defer { isLoading = false }

        do {
            async let activitiesTask = activityService.getRecentActivities(limit: 100)
            async let statsTask = activityService.getActivityStats(hours: 24)
            async let batchesTask = activityService.listBatches(limit: 50)

            let (newActivities, newStats, newBatches) = try await (activitiesTask, statsTask, batchesTask)

            activities = newActivities
            stats = newStats
            batches = newBatches
        } catch {
            logger.error("Failed to refresh activity data: \(String(describing: error))")
        }
    }

    private func handleBatchAction(batch: BatchInfo, action: BatchAction) async {
        do {
            switch action {
            case .pause:
                _ = try await activityService.pauseBatch(batchId: batch.batchId)
            case .cancel:
                _ = try await activityService.cancelBatch(batchId: batch.batchId)
            case .delete:
                try await activityService.deleteBatch(batchId: batch.batchId)
            }
            await refresh()
        } catch {
            logger.error("Batch action failed: \(String(describing: error))")
        }
    }

    // MARK: - Helpers

    private func formatDuration(_ ms: Double) -> String {
        if ms < 1000 {
            return String(format: "%.0fms", ms)
        } else if ms < 60000 {
            return String(format: "%.1fs", ms / 1000)
        } else {
            return String(format: "%.1fm", ms / 60000)
        }
    }

    private func formatActivityType(_ type: String) -> String {
        type.replacingOccurrences(of: "_", with: " ").capitalized
    }

    private func colorForLevel(_ level: String) -> Color {
        switch level {
        case "error", "critical": return .red
        case "warning": return .orange
        case "info": return .blue
        case "debug": return .gray
        default: return .primary
        }
    }
}

// MARK: - Supporting Views

/// Row view for a single activity item
struct ActivityRowView: View {
    let activity: ActivityItem

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            // Icon
            Image(systemName: activity.typeIcon)
                .font(.title2)
                .foregroundColor(colorForLevel(activity.level))
                .frame(width: 28)

            VStack(alignment: .leading, spacing: 4) {
                // Message
                Text(activity.message)
                    .font(.body)

                // Metadata
                HStack(spacing: 12) {
                    if let timestamp = activity.parsedTimestamp {
                        Text(timestamp, style: .relative)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }

                    if let duration = activity.durationMs {
                        Label(formatDuration(duration), systemImage: "clock")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }

                    if activity.workflowId != nil {
                        Label("Workflow", systemImage: "flowchart")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }

                    if activity.batchId != nil {
                        Label("Batch", systemImage: "square.stack.3d.up")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }

                // Error message if present
                if let error = activity.error {
                    Text(error)
                        .font(.caption)
                        .foregroundColor(.red)
                        .lineLimit(2)
                }
            }

            Spacer()

            // Level badge
            Text(activity.level.uppercased())
                .font(.caption2)
                .fontWeight(.medium)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(colorForLevel(activity.level).opacity(0.2))
                .foregroundColor(colorForLevel(activity.level))
                .cornerRadius(4)
        }
        .padding(.vertical, 4)
    }

    private func colorForLevel(_ level: String) -> Color {
        switch level {
        case "error", "critical": return .red
        case "warning": return .orange
        case "info": return .blue
        case "debug": return .gray
        default: return .primary
        }
    }

    private func formatDuration(_ ms: Double) -> String {
        if ms < 1000 {
            return String(format: "%.0fms", ms)
        } else {
            return String(format: "%.1fs", ms / 1000)
        }
    }
}

/// Batch action types
enum BatchAction {
    case pause
    case cancel
    case delete
}

/// Row view for a batch execution
struct BatchRowView: View {
    let batch: BatchInfo
    let onAction: (BatchAction) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                // Status icon
                Image(systemName: batch.statusIcon)
                    .foregroundColor(colorForStatus(batch.status))

                // Batch ID (truncated)
                Text(String(batch.batchId.prefix(8)))
                    .font(.headline)
                    .monospaced()

                Spacer()

                // Status badge
                Text(batch.status.uppercased())
                    .font(.caption)
                    .fontWeight(.medium)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(colorForStatus(batch.status).opacity(0.2))
                    .foregroundColor(colorForStatus(batch.status))
                    .cornerRadius(4)
            }

            // Progress bar
            ProgressView(value: batch.progressPercent, total: 100)
                .progressViewStyle(.linear)

            // Progress text
            HStack {
                Text("\(batch.completedItems)/\(batch.totalItems) completed")
                    .font(.caption)
                    .foregroundColor(.secondary)

                if batch.failedItems > 0 {
                    Text("\(batch.failedItems) failed")
                        .font(.caption)
                        .foregroundColor(.red)
                }

                Spacer()

                Text(String(format: "%.0f%%", batch.progressPercent))
                    .font(.caption)
                    .fontWeight(.medium)
            }

            // Actions
            if batch.status == "running" || batch.status == "pending" {
                HStack {
                    Spacer()
                    Button("Pause") {
                        onAction(.pause)
                    }
                    .buttonStyle(.bordered)

                    Button("Cancel") {
                        onAction(.cancel)
                    }
                    .buttonStyle(.bordered)
                    .tint(.red)
                }
            } else if batch.status != "running" {
                HStack {
                    Spacer()
                    Button("Delete") {
                        onAction(.delete)
                    }
                    .buttonStyle(.bordered)
                    .tint(.red)
                }
            }
        }
        .padding(.vertical, 8)
    }

    private func colorForStatus(_ status: String) -> Color {
        switch status {
        case "pending": return .gray
        case "running": return .blue
        case "paused": return .yellow
        case "completed": return .green
        case "partial_failure": return .orange
        case "failed": return .red
        case "cancelled": return .gray
        default: return .primary
        }
    }
}

/// Statistics card view
struct StatCard: View {
    let title: String
    let value: String
    let icon: String
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: icon)
                    .foregroundColor(color)
                Text(title)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            Text(value)
                .font(.title)
                .fontWeight(.bold)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(Color(.controlBackgroundColor))
        .cornerRadius(8)
    }
}

/// Row view for a running workflow execution
struct RunningWorkflowRow: View {
    let execution: WorkflowExecution
    @Environment(WorkflowExecutionObserver.self) var executionObserver
    @State private var isPulsing = false
    @State private var showWorkflowPreview = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            rowContent
        }
        .padding(.vertical, 8)
        .onAppear {
            if execution.isRunning {
                isPulsing = true
            }
        }
        .onChange(of: execution.isRunning) { _, isRunning in
            isPulsing = isRunning
        }
        .sheet(isPresented: $showWorkflowPreview) {
            WorkflowPreviewSheet(execution: execution)
        }
    }

    @ViewBuilder
    private var rowContent: some View {
        // Header with controls
        HStack {
            // Pulsing indicator
                Circle()
                    .fill(statusColor.opacity(isPulsing ? 0.8 : 0.4))
                    .frame(width: 10, height: 10)
                    .animation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true), value: isPulsing)

                VStack(alignment: .leading, spacing: 2) {
                    Text(execution.name)
                        .font(.headline)

                    // Current step indicator
                    if let nodeName = execution.currentNodeName {
                        Text("Step: \(nodeName)")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }

                Spacer()

                // Control buttons
                if execution.isRunning {
                    Button {
                        executionObserver.cancelExecution(workflowId: execution.id)
                    } label: {
                        Image(systemName: "stop.fill")
                            .foregroundColor(.red)
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .help("Stop workflow")
                }

                // Status badge
                statusBadge
            }

            // Progress section
            VStack(alignment: .leading, spacing: 4) {
                // Progress bar
                if let progress = execution.overallProgress {
                    ProgressView(value: progress)
                        .progressViewStyle(.linear)
                        .tint(statusColor)
                } else if execution.isRunning {
                    ProgressView()
                        .progressViewStyle(.linear)
                }

                // Progress text
                HStack {
                    if execution.totalFiles > 0 {
                        Text("\(execution.processedFiles)/\(execution.totalFiles) files")
                            .font(.caption)
                            .foregroundColor(.secondary)

                        if let progress = execution.overallProgress {
                            Text("(\(Int(progress * 100))%)")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }

                    Spacer()

                    // Duration
                    Text(formatDuration(since: execution.startTime))
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .monospacedDigit()
                }
            }

            // Current file being processed
            if let fileName = execution.currentFileName {
                HStack(spacing: 4) {
                    ProgressView()
                        .controlSize(.mini)
                    Text("Processing: \(fileName)")
                        .font(.caption)
                        .foregroundColor(.blue)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color.blue.opacity(0.1))
                .cornerRadius(4)
            }

            // Node progress summary
            if !execution.nodeStates.isEmpty {
                HStack(spacing: 8) {
                    ForEach(Array(execution.nodeStates.keys.sorted()), id: \.self) { nodeId in
                        if let state = execution.nodeStates[nodeId] {
                            nodeStatusPill(state)
                        }
                    }
                }
            }

        // Error message
        if let error = execution.workflowError {
            HStack {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundColor(.red)
                Text(error)
                    .font(.caption)
                    .foregroundColor(.red)
            }
            .padding(8)
            .background(Color.red.opacity(0.1))
            .cornerRadius(4)
        }

        // View workflow button
        Button {
            showWorkflowPreview = true
        } label: {
            Label("View Workflow", systemImage: "flowchart")
                .font(.caption)
        }
        .buttonStyle(.bordered)
        .controlSize(.small)
    }

    // MARK: - Subviews

    @ViewBuilder
    private func nodeStatusPill(_ state: NodeExecutionState) -> some View {
        let (icon, color) = nodeStatusInfo(state)
        HStack(spacing: 4) {
            if state.status == .running || state.status == .parallelRunning {
                ProgressView()
                    .controlSize(.mini)
            } else {
                Image(systemName: icon)
                    .font(.caption2)
            }

            if state.fileTotal > 0 {
                Text("\(state.successCount)/\(state.fileTotal)")
                    .font(.caption2)
            }
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 3)
        .background(color.opacity(0.2))
        .foregroundColor(color)
        .cornerRadius(4)
    }

    @ViewBuilder
    private var statusBadge: some View {
        let (text, color) = statusInfo
        Text(text)
            .font(.caption)
            .fontWeight(.medium)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(color.opacity(0.2))
            .foregroundColor(color)
            .cornerRadius(4)
    }

    // MARK: - Helpers

    private var statusColor: Color {
        switch execution.status {
        case .idle: return .gray
        case .running: return .blue
        case .paused: return .orange
        case .completed: return .green
        case .failed: return .red
        }
    }

    private var statusInfo: (String, Color) {
        switch execution.status {
        case .idle: return ("Idle", .gray)
        case .running: return ("Running", .blue)
        case .paused: return ("Paused", .orange)
        case .completed: return ("Completed", .green)
        case .failed: return ("Failed", .red)
        }
    }

    private func nodeStatusInfo(_ state: NodeExecutionState) -> (String, Color) {
        switch state.status {
        case .idle: return ("circle", .gray)
        case .running, .parallelRunning: return ("play.circle", .blue)
        case .completed: return ("checkmark.circle.fill", .green)
        case .failed: return ("xmark.circle.fill", .red)
        }
    }

    private func formatDuration(since startTime: Date) -> String {
        let duration = Date().timeIntervalSince(startTime)
        if duration < 60 {
            return String(format: "%.0fs", duration)
        } else if duration < 3600 {
            let mins = Int(duration / 60)
            let secs = Int(duration.truncatingRemainder(dividingBy: 60))
            return String(format: "%d:%02d", mins, secs)
        } else {
            return String(format: "%.1fh", duration / 3600)
        }
    }
}

// MARK: - Workflow Preview Sheet

/// A sheet showing an animated preview of workflow execution progress
struct WorkflowPreviewSheet: View {
    let execution: WorkflowExecution
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                VStack(alignment: .leading) {
                    Text(execution.name)
                        .font(.headline)
                    if let nodeName = execution.currentNodeName {
                        Text("Current step: \(nodeName)")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }

                Spacer()

                Button("Done") {
                    dismiss()
                }
            }
            .padding()
            .background(Color(.controlBackgroundColor))

            Divider()

            // Workflow visualization
            ScrollView([.horizontal, .vertical]) {
                VStack(alignment: .leading, spacing: 20) {
                    ForEach(Array(execution.nodeStates.keys.sorted()), id: \.self) { nodeId in
                        if let state = execution.nodeStates[nodeId] {
                            PreviewNodeView(
                                nodeId: nodeId,
                                state: state,
                                isCurrentNode: nodeId == execution.currentNodeId
                            )
                        }
                    }

                    if execution.nodeStates.isEmpty {
                        ContentUnavailableView(
                            "No Node Data",
                            systemImage: "flowchart",
                            description: Text("Node execution data will appear here as the workflow runs")
                        )
                    }
                }
                .padding()
            }

            Divider()

            // Progress footer
            HStack {
                if execution.totalFiles > 0 {
                    Text("\(execution.processedFiles)/\(execution.totalFiles) files")
                }

                Spacer()

                if let progress = execution.overallProgress {
                    ProgressView(value: progress)
                        .frame(width: 100)
                    Text("\(Int(progress * 100))%")
                        .monospacedDigit()
                }
            }
            .font(.caption)
            .foregroundColor(.secondary)
            .padding()
            .background(Color(.controlBackgroundColor))
        }
        .frame(minWidth: 400, minHeight: 300)
    }
}

/// Individual node in the workflow preview
struct PreviewNodeView: View {
    let nodeId: String
    let state: NodeExecutionState
    let isCurrentNode: Bool
    @State private var isPulsing = false

    var body: some View {
        HStack(spacing: 12) {
            // Status icon with animation
            ZStack {
                if isCurrentNode && (state.status == .running || state.status == .parallelRunning) {
                    Circle()
                        .fill(Color.blue.opacity(isPulsing ? 0.5 : 0.2))
                        .frame(width: 40, height: 40)
                        .animation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true), value: isPulsing)
                }

                Image(systemName: statusIcon)
                    .font(.title2)
                    .foregroundColor(statusColor)
                    .frame(width: 30, height: 30)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text(nodeId)
                    .font(.headline)
                    .lineLimit(1)

                // File progress if parallel
                if state.fileTotal > 0 {
                    HStack {
                        ProgressView(value: state.progress)
                            .frame(width: 100)
                        Text("\(state.successCount)/\(state.fileTotal)")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }

                // Error if present
                if let error = state.errorMessage {
                    Text(error)
                        .font(.caption)
                        .foregroundColor(.red)
                        .lineLimit(2)
                }
            }

            Spacer()
        }
        .padding()
        .background(isCurrentNode ? Color.blue.opacity(0.1) : Color(.controlBackgroundColor))
        .cornerRadius(8)
        .onAppear {
            if isCurrentNode {
                isPulsing = true
            }
        }
        .onChange(of: isCurrentNode) { _, current in
            isPulsing = current
        }
    }

    private var statusIcon: String {
        switch state.status {
        case .idle: return "circle"
        case .running, .parallelRunning: return "play.circle.fill"
        case .completed: return "checkmark.circle.fill"
        case .failed: return "xmark.circle.fill"
        }
    }

    private var statusColor: Color {
        switch state.status {
        case .idle: return .gray
        case .running, .parallelRunning: return .blue
        case .completed: return .green
        case .failed: return .red
        }
    }
}

#Preview {
    ActivityMonitorView()
        .environmentObject(APIClient())
        .environment(WorkflowExecutionObserver())
}
