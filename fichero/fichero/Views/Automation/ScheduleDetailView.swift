import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ScheduleDetailView")

// Detail view for a schedule showing configuration and run history
// swiftlint:disable:next type_body_length
struct ScheduleDetailView: View {
    let schedule: ScheduleInfo
    @EnvironmentObject var apiClient: APIClient

    @State private var isLoading = false
    @State private var error: String?
    @State private var runs: [ScheduleRunInfo] = []

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header
                headerSection

                Divider()

                // Configuration
                configurationSection

                Divider()

                // Run History
                runHistorySection
            }
            .padding()
        }
        .task {
            guard !Task.isCancelled else { return }
            await loadRuns()
        }
    }

    // MARK: - Header Section

    @ViewBuilder
    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "clock.fill")
                    .font(.largeTitle)
                    .foregroundStyle(statusColor)

                VStack(alignment: .leading, spacing: 4) {
                    Text(schedule.name)
                        .font(.title2.bold())

                    HStack(spacing: 8) {
                        StatusBadge(status: scheduleStatus)

                        if let nextRun = schedule.nextRunAt {
                            Text("Next: \(nextRun)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                Spacer()

                // Action buttons
                actionButtons
            }

            if let errorMessage = schedule.errorMessage {
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
            if schedule.status == "active" {
                Button {
                    Task { await pauseSchedule() }
                } label: {
                    Label("Pause", systemImage: "pause.fill")
                }
                .buttonStyle(.bordered)
            } else if schedule.status == "paused" {
                Button {
                    Task { await resumeSchedule() }
                } label: {
                    Label("Resume", systemImage: "play.fill")
                }
                .buttonStyle(.bordered)
            }

            Button {
                Task { await triggerNow() }
            } label: {
                Label("Run Now", systemImage: "play.circle")
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
                configField("Workflow", schedule.workflowId)
                configField("Schedule Type", schedule.scheduleType)

                if let cron = schedule.cronExpression {
                    configField("Cron Expression", cron)
                }

                if let interval = schedule.intervalSeconds {
                    configField("Interval", formatInterval(interval))
                }

                if let runAt = schedule.runAt {
                    configField("Run At", runAt)
                }

                configField("Timezone", schedule.timezone)
                configField("Run Count", "\(schedule.runCount)")

                if let lastRun = schedule.lastRunAt {
                    configField("Last Run", lastRun)
                }
            }

            if schedule.useBatch {
                HStack {
                    Image(systemName: "square.stack.3d.up")
                        .foregroundStyle(Color.accentColor)
                    Text("Batch Mode")
                        .font(.subheadline)
                    Text("(max \(schedule.maxConcurrent) concurrent)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(8)
                .background(Color.accentColor.opacity(0.1))
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
        }
    }

    // MARK: - Run History Section

    @ViewBuilder
    private var runHistorySection: some View {
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

    // MARK: - Helpers

    private var statusColor: Color {
        switch schedule.status {
        case "active": return .green
        case "paused": return .yellow
        case "error": return .red
        default: return .secondary
        }
    }

    private var scheduleStatus: Status {
        switch schedule.status {
        case "active": return .completed
        case "paused": return .pending
        case "error": return .failed
        default: return .pending
        }
    }

    private func runStatusColor(_ status: String) -> Color {
        switch status {
        case "completed": return .green
        case "running": return .blue
        case "failed": return .red
        default: return .secondary
        }
    }

    private func formatInterval(_ seconds: Int) -> String {
        if seconds < 60 {
            return "\(seconds) seconds"
        } else if seconds < 3600 {
            return "\(seconds / 60) minutes"
        } else if seconds < 86400 {
            return "\(seconds / 3600) hours"
        } else {
            return "\(seconds / 86400) days"
        }
    }

    // MARK: - Actions

    private func loadRuns() async {
        isLoading = true
        error = nil

        do {
            let service = AutomationService(apiClient: apiClient)
            runs = try await service.getScheduleRuns(scheduleId: schedule.scheduleId, limit: 20)
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    private func pauseSchedule() async {
        do {
            let service = AutomationService(apiClient: apiClient)
            _ = try await service.pauseSchedule(scheduleId: schedule.scheduleId)
        } catch {
            logger.error("Failed to pause schedule: \(error.localizedDescription)")
        }
    }

    private func resumeSchedule() async {
        do {
            let service = AutomationService(apiClient: apiClient)
            _ = try await service.resumeSchedule(scheduleId: schedule.scheduleId)
        } catch {
            logger.error("Failed to resume schedule: \(error.localizedDescription)")
        }
    }

    private func triggerNow() async {
        do {
            let service = AutomationService(apiClient: apiClient)
            _ = try await service.triggerSchedule(scheduleId: schedule.scheduleId)
        } catch {
            logger.error("Failed to trigger schedule: \(error.localizedDescription)")
        }
    }
}

#Preview {
    ScheduleDetailView(
        schedule: ScheduleInfo(
            scheduleId: "test-1",
            name: "Daily Report",
            workflowId: "workflow-1",
            scheduleType: "cron",
            cronExpression: "0 9 * * *",
            intervalSeconds: nil,
            runAt: nil,
            timezone: "America/Halifax",
            status: "active",
            inputs: [:],
            useBatch: false,
            batchItems: nil,
            maxConcurrent: 5,
            createdAt: "2024-01-01T00:00:00Z",
            updatedAt: "2024-01-01T00:00:00Z",
            lastRunAt: "2024-01-25T09:00:00Z",
            nextRunAt: "2024-01-26T09:00:00Z",
            runCount: 25,
            errorMessage: nil
        )
    )
    .environmentObject(APIClient())
    .frame(width: 600, height: 500)
}
