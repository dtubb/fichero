import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "TriggerDetailView")

/// Detail view for a file trigger showing configuration and execution history
struct TriggerDetailView: View {
    let trigger: TriggerInfo
    @EnvironmentObject var apiClient: APIClient

    @State private var isLoading = false
    @State private var error: String?
    @State private var executions: [TriggerExecutionInfo] = []

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header
                headerSection

                Divider()

                // Configuration
                configurationSection

                Divider()

                // Execution History
                executionHistorySection
            }
            .padding()
        }
        .task {
            guard !Task.isCancelled else { return }
            await loadExecutions()
        }
    }

    // MARK: - Header Section

    @ViewBuilder
    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "bolt.fill")
                    .font(.largeTitle)
                    .foregroundStyle(statusColor)

                VStack(alignment: .leading, spacing: 4) {
                    Text(trigger.name)
                        .font(.title2.bold())

                    HStack(spacing: 8) {
                        StatusBadge(status: triggerStatus)

                        Text("File Watcher")
                            .font(.caption)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(.secondary.opacity(0.2))
                            .cornerRadius(4)
                    }
                }

                Spacer()

                // Action buttons
                actionButtons
            }

            if let errorMessage = trigger.errorMessage {
                HStack {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.orange)
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(8)
                .background(.orange.opacity(0.1))
                .cornerRadius(8)
            }
        }
    }

    @ViewBuilder
    private var actionButtons: some View {
        HStack(spacing: 8) {
            if trigger.status == "active" {
                Button {
                    Task { await pauseTrigger() }
                } label: {
                    Label("Pause", systemImage: "pause.fill")
                }
                .buttonStyle(.bordered)
            } else if trigger.status == "paused" {
                Button {
                    Task { await resumeTrigger() }
                } label: {
                    Label("Resume", systemImage: "play.fill")
                }
                .buttonStyle(.bordered)
            }

            Button {
                Task { await loadExecutions() }
            } label: {
                Label("Refresh", systemImage: "arrow.clockwise")
            }
            .buttonStyle(.borderedProminent)
        }
    }

    // MARK: - Configuration Section

    @ViewBuilder
    private var configurationSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Configuration")
                .font(.headline)

            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible())
            ], alignment: .leading, spacing: 12) {
                configField("Workflow", trigger.workflowId)
                configField("Watch Path", trigger.watchPath)
                configField("Recursive", trigger.recursive ? "Yes" : "No")
                configField("Events", trigger.eventsDescription)
                configField("Filter Mode", trigger.filterMode.capitalized)
                configField("Filter", trigger.filterDescription)
                configField("Trigger Count", "\(trigger.triggerCount)")

                if let lastTriggered = trigger.lastTriggeredAt {
                    configField("Last Triggered", lastTriggered)
                }
            }

            // Exclude patterns
            if !trigger.excludePatterns.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Exclude Patterns")
                        .font(.subheadline)
                        .fontWeight(.medium)

                    ForEach(trigger.excludePatterns, id: \.self) { pattern in
                        HStack(spacing: 8) {
                            Image(systemName: "xmark.circle")
                                .foregroundStyle(.red)
                                .frame(width: 20)

                            Text(pattern)
                                .font(.caption)
                                .foregroundStyle(.secondary)

                            Spacer()
                        }
                        .padding(6)
                        .background(Color(nsColor: .controlBackgroundColor))
                        .cornerRadius(6)
                    }
                }
                .padding(.top, 8)
            }

            // Timing settings
            VStack(alignment: .leading, spacing: 8) {
                Text("Timing")
                    .font(.subheadline)
                    .fontWeight(.medium)

                HStack(spacing: 16) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Debounce")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(String(format: "%.1fs", trigger.debounceSeconds))
                            .font(.body)
                    }

                    VStack(alignment: .leading, spacing: 2) {
                        Text("Batch Delay")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(String(format: "%.1fs", trigger.batchDelaySeconds))
                            .font(.body)
                    }
                }
            }
            .padding(.top, 8)

            if trigger.useBatch {
                HStack {
                    Image(systemName: "square.stack.3d.up")
                        .foregroundStyle(.blue)
                    Text("Batch Mode")
                        .font(.subheadline)
                    Text("(max \(trigger.maxConcurrent) concurrent)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(8)
                .background(.blue.opacity(0.1))
                .cornerRadius(8)
            }
        }
    }

    @ViewBuilder
    private func configField(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.body)
                .lineLimit(2)
        }
    }

    // MARK: - Execution History Section

    @ViewBuilder
    private var executionHistorySection: some View {
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
        .background(Color(nsColor: .controlBackgroundColor))
        .cornerRadius(8)
    }

    // MARK: - Helpers

    private var statusColor: Color {
        switch trigger.status {
        case "active": return .green
        case "paused": return .yellow
        case "error": return .red
        default: return .secondary
        }
    }

    private var triggerStatus: Status {
        switch trigger.status {
        case "active": return .completed
        case "paused": return .pending
        case "error": return .failed
        default: return .pending
        }
    }

    private func executionStatusColor(_ status: String) -> Color {
        switch status {
        case "completed": return .green
        case "running": return .blue
        case "failed": return .red
        default: return .secondary
        }
    }

    // MARK: - Actions

    private func loadExecutions() async {
        isLoading = true
        error = nil

        do {
            let service = AutomationService(apiClient: apiClient)
            executions = try await service.getTriggerExecutions(triggerId: trigger.triggerId, limit: 20)
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    private func pauseTrigger() async {
        do {
            let service = AutomationService(apiClient: apiClient)
            _ = try await service.pauseTrigger(triggerId: trigger.triggerId)
        } catch {
            logger.error("Failed to pause trigger: \(error.localizedDescription)")
        }
    }

    private func resumeTrigger() async {
        do {
            let service = AutomationService(apiClient: apiClient)
            _ = try await service.resumeTrigger(triggerId: trigger.triggerId)
        } catch {
            logger.error("Failed to resume trigger: \(error.localizedDescription)")
        }
    }
}

#Preview {
    TriggerDetailView(
        trigger: TriggerInfo(
            triggerId: "test-1",
            name: "New Image Trigger",
            workflowId: "workflow-1",
            watchPath: "/Users/test/Photos",
            recursive: true,
            events: ["created", "modified"],
            filterMode: "extension",
            filterPattern: nil,
            filterExtensions: ["jpg", "png", "heic"],
            excludePatterns: [".DS_Store", "*.tmp"],
            debounceSeconds: 1.0,
            batchDelaySeconds: 5.0,
            inputsTemplate: [:],
            status: "active",
            useBatch: false,
            maxConcurrent: 5,
            createdAt: "2024-01-01T00:00:00Z",
            updatedAt: "2024-01-01T00:00:00Z",
            lastTriggeredAt: "2024-01-25T14:30:00Z",
            triggerCount: 42,
            errorMessage: nil
        )
    )
    .environmentObject(APIClient())
    .frame(width: 600, height: 500)
}
