import OSLog
import SwiftUI

let triggerDetailLogger = Logger(subsystem: "app.fichero.fichero", category: "TriggerDetailView")

/// Detail view for a file trigger showing configuration and execution history
struct TriggerDetailView: View {
    let trigger: TriggerInfo
    @Environment(APIClient.self) var apiClient

    @State var isLoading = false
    @State var error: String?
    @State var executions: [TriggerExecutionInfo] = []

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
    .environment(APIClient())
    .frame(width: 600, height: 500)
}
