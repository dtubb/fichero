import OSLog
import SwiftUI

let triggerDetailLogger = Logger(subsystem: "app.fichero.fichero", category: "TriggerDetailView")

/// Detail view for a file trigger showing configuration and execution history
struct TriggerDetailView: View {
    let trigger: TriggerInfo
    @Environment(APIClient.self) var apiClient

    // #4705 "4b-2": the ONE piece of state this view still owns for the
    // (now-extracted) run history — a manual "Refresh" tap bumps this,
    // and `.id(runHistoryRefreshToken)` below forces `TriggerRunHistoryView`
    // to remount, which re-triggers its own `.task(id: triggerId)` load.
    // Reuses the same `.id()`-forces-a-fresh-mount mechanism the Reader's
    // dispatcher uses for identity changes (`ReadingPaneView+Tabs.swift`)
    // rather than inventing a second refresh API on the shared component.
    @State private var runHistoryRefreshToken = UUID()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header
                headerSection

                Divider()

                // Configuration
                configurationSection

                Divider()

                // Execution History — #4705 "4b-2": extracted to
                // `TriggerRunHistoryView` so the SAME component also mounts
                // from the Reader's `.runHistory` surface
                // (`ReadingPaneView+Tabs.swift`).
                TriggerRunHistoryView(triggerId: trigger.triggerId)
                    .id(runHistoryRefreshToken)
            }
            .padding()
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
                // #4705 "4b-2": `loadExecutions()` moved to
                // `TriggerRunHistoryView` with its state — bump the token
                // that forces it to remount instead of calling it directly.
                runHistoryRefreshToken = UUID()
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
