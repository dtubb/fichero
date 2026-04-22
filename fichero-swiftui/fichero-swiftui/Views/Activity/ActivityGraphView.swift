import OSLog
import SwiftUI

private let logger = Logger(subsystem: "com.tubb.Fichero", category: "ActivityGraphView")

/// Shows the checkpoint history for a workflow run
struct ActivityGraphView: View {
    let selectedRun: SelectedActivityRun
    @EnvironmentObject var apiClient: APIClient

    @State private var history: CheckpointHistoryResponse?
    @State private var isLoading = false
    @State private var error: String?
    @State private var selectedCheckpoint: CheckpointSnapshot?

    var body: some View {
        HSplitView {
            // Left: Checkpoint list (timeline)
            checkpointList
                .frame(minWidth: 200, maxWidth: 300)

            // Right: Selected checkpoint details
            checkpointDetail
        }
        .task {
            guard !Task.isCancelled else { return }
            await loadHistory()
        }
    }

    @ViewBuilder
    private var checkpointList: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            HStack {
                Text("Execution Steps")
                    .font(.headline)
                Spacer()
                if let history = history {
                    Text("\(history.totalSteps) steps")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(.bar)

            Divider()

            if isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = error {
                VStack {
                    Image(systemName: "exclamationmark.triangle")
                        .foregroundStyle(.orange)
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let history = history {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 0) {
                        ForEach(history.checkpoints) { checkpoint in
                            checkpointRow(checkpoint)
                        }
                    }
                }
            } else {
                Text("No checkpoint history available")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
    }

    @ViewBuilder
    private func checkpointRow(_ checkpoint: CheckpointSnapshot) -> some View {
        Button {
            selectedCheckpoint = checkpoint
        } label: {
            HStack(spacing: 8) {
                // Step indicator with connection line
                VStack(spacing: 0) {
                    Circle()
                        .fill(checkpoint.nodeName != nil ? Color.accentColor : Color.secondary.opacity(0.5))
                        .frame(width: 10, height: 10)
                }

                VStack(alignment: .leading, spacing: 2) {
                    // Node name or step number
                    Text(checkpoint.nodeName ?? "Step \(checkpoint.step)")
                        .font(.subheadline)
                        .fontWeight(selectedCheckpoint?.id == checkpoint.id ? .semibold : .regular)

                    // State summary — omit LangGraph internal keys
                    let visibleWriteKeys = checkpoint.writes.keys.filter { !isInternalKey($0) }
                    if !visibleWriteKeys.isEmpty {
                        Text(visibleWriteKeys.sorted().joined(separator: ", "))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }

                Spacer()

                // Step number badge
                Text("\(checkpoint.step)")
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.secondary.opacity(0.1), in: Capsule())
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .background(selectedCheckpoint?.id == checkpoint.id ? Color.accentColor.opacity(0.15) : .clear)
    }

    @ViewBuilder
    private var checkpointDetail: some View {
        if let checkpoint = selectedCheckpoint {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    // Header
                    VStack(alignment: .leading, spacing: 4) {
                        Text(checkpoint.nodeName ?? "Step \(checkpoint.step)")
                            .font(.title2)

                        HStack {
                            Text("Checkpoint: \(checkpoint.checkpointId.prefix(8))...")
                                .font(.caption.monospaced())
                                .foregroundStyle(.secondary)

                            if let timestamp = checkpoint.timestamp {
                                Text("•")
                                    .foregroundStyle(.tertiary)
                                Text(timestamp)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }

                    Divider()

                    // Writes (what this node produced)
                    if !checkpoint.writes.isEmpty {
                        stateSection(title: "Output (Writes)", values: checkpoint.writes)
                    }

                    // State values
                    if !checkpoint.stateValues.isEmpty {
                        stateSection(title: "State", values: checkpoint.stateValues)
                    }

                    // Next nodes
                    if !checkpoint.nextNodes.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Next Nodes")
                                .font(.headline)

                            ForEach(Array(checkpoint.nextNodes.enumerated()), id: \.offset) { _, node in
                                HStack {
                                    Image(systemName: "arrow.right.circle")
                                        .foregroundStyle(.blue)
                                    Text(node)
                                        .font(.subheadline)
                                }
                            }
                        }
                    }
                }
                .padding()
            }
        } else {
            VStack {
                Image(systemName: "point.3.connected.trianglepath.dotted")
                    .font(.largeTitle)
                    .foregroundStyle(.secondary)
                Text("Select a step to view details")
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    // MARK: - Internal Key Filtering

    private static let internalChannelKeys: Set<String> = [
        "parallel_results", "__end__", "__start__"
    ]

    private func isInternalKey(_ key: String) -> Bool {
        Self.internalChannelKeys.contains(key)
            || key.hasSuffix("_aggregate")
            || key.hasPrefix("branch:to:")
    }

    @ViewBuilder
    private func stateSection(title: String, values: [String: CheckpointValue]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)

            // Create array with indices to ensure unique IDs; hide LangGraph internal keys.
            let sortedKeys = values.keys.sorted().filter { !isInternalKey($0) }
            ForEach(Array(sortedKeys.enumerated()), id: \.offset) { _, key in
                if let value = values[key] {
                    HStack(alignment: .top) {
                        Text(key)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .frame(width: 120, alignment: .leading)

                        Text(value.stringValue)
                            .font(.system(.subheadline, design: .monospaced))
                            .lineLimit(3)
                            .textSelection(.enabled)
                    }
                    .padding(.vertical, 2)
                }
            }
        }
        .padding()
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
    }

    private func loadHistory() async {
        guard let threadId = selectedRun.threadId else {
            error = "No thread ID available"
            return
        }

        isLoading = true
        error = nil

        do {
            let activityService = ActivityServiceGenerated(apiClient: apiClient)
            history = try await activityService.getCheckpointHistory(threadId: threadId)

            // Auto-select first checkpoint with a node name, or the last one
            if let checkpoints = history?.checkpoints {
                selectedCheckpoint = checkpoints.first(where: { $0.nodeName != nil })
                    ?? checkpoints.last
            }
        } catch {
            logger.error("Failed to load checkpoint history: \(error.localizedDescription)")
            self.error = error.localizedDescription
        }

        isLoading = false
    }
}
// MARK: - Preview

#Preview {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!

    let selectedRun = SelectedActivityRun(
        id: "test-run",
        name: "Test Workflow",
        workflowId: "workflow-123",
        threadId: "thread-456",
        timestamp: Date(),
        status: .completed,
        isLive: false,
        childType: nil
    )

    ActivityGraphView(selectedRun: selectedRun)
        .environmentObject(library.apiClient)
        .frame(width: 800, height: 600)
}
