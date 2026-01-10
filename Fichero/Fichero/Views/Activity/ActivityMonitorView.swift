import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ActivityMonitorView")

/// Main activity monitor view showing real-time workflow and batch activity
struct ActivityMonitorView: View {
    @EnvironmentObject var apiClient: APIClient

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
        case activities = "Activities"
        case batches = "Batches"
        case stats = "Statistics"
    }

    var body: some View {
        VStack(spacing: 0) {
            // Tab picker
            Picker("View", selection: $selectedTab) {
                ForEach(ActivityTab.allCases, id: \.self) { tab in
                    Text(tab.rawValue).tag(tab)
                }
            }
            .pickerStyle(.segmented)
            .padding()

            // Content based on selected tab
            switch selectedTab {
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

#Preview {
    ActivityMonitorView()
        .environmentObject(APIClient())
}
