import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ActivityProgressView")

// MARK: - Data Models

struct ProgressTimeline: Codable {
    let nodes: [String: NodeProgressStats]
    let steps: [ExecutionStep]
}

struct NodeProgressStats: Codable {
    let totalFiles: Int
    let successCount: Int
    let errorCount: Int

    enum CodingKeys: String, CodingKey {
        case totalFiles = "total_files"
        case successCount = "success_count"
        case errorCount = "error_count"
    }
}

struct ExecutionStep: Codable {
    let type: String?  // nil for node steps, "file" for file steps
    let nodeId: String
    let filePath: String?
    let fileIndex: Int?
    let fileTotal: Int?
    let startedAt: String
    let completedAt: String?
    let status: String
    let durationMs: Double?
    let filesProcessed: Int?
    let artifactsCreated: Int?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case type, status, error
        case nodeId = "node_id"
        case filePath = "file_path"
        case fileIndex = "file_index"
        case fileTotal = "file_total"
        case startedAt = "started_at"
        case completedAt = "completed_at"
        case durationMs = "duration_ms"
        case filesProcessed = "files_processed"
        case artifactsCreated = "artifacts_created"
    }

    var isFileStep: Bool { type == "file" }
    var isNodeStep: Bool { type == nil }
}

// MARK: - View

/// Progress view showing workflow execution progress
struct ActivityProgressView: View {
    let selectedRun: SelectedActivityRun
    let liveExecution: WorkflowExecution?
    @EnvironmentObject var apiClient: APIClient

    @State private var progressTimeline: ProgressTimeline?
    @State private var isLoadingTimeline = false

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                if let execution = liveExecution {
                    liveProgressView(execution)
                } else {
                    historicalProgressView
                }
            }
            .padding()
        }
        .task {
            if liveExecution == nil {
                await loadProgressTimeline()
            }
        }
        .onChange(of: selectedRun.threadId) { _, _ in
            if liveExecution == nil {
                Task { await loadProgressTimeline() }
            }
        }
    }

    @ViewBuilder
    private func liveProgressView(_ execution: WorkflowExecution) -> some View {
        // Overall progress card
        VStack(alignment: .leading, spacing: 8) {
            Text("Overall Progress")
                .font(.headline)

            if let progress = execution.overallProgress {
                ProgressView(value: progress)
                    .scaleEffect(y: 2)

                HStack {
                    Text("\(Int(progress * 100))%")
                        .font(.title.monospacedDigit())

                    Spacer()

                    if execution.totalFiles > 0 {
                        Text("\(execution.processedFiles) of \(execution.totalFiles) files")
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .padding()
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))

        // Per-node progress
        if !execution.nodeStates.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("Node Progress")
                    .font(.headline)

                ForEach(
                    Array(execution.nodeStates.values.sorted(by: { $0.nodeId < $1.nodeId })),
                    id: \.nodeId
                ) { state in
                    nodeProgressRow(state)
                }
            }
            .padding()
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
        }

        // Document progress
        if !execution.documentProgress.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("Recent Files")
                    .font(.headline)

                ForEach(execution.orderedDocumentProgress.prefix(10)) { doc in
                    documentProgressRow(doc)
                }
            }
            .padding()
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
        }
    }

    @ViewBuilder
    private func nodeProgressRow(_ state: NodeExecutionState) -> some View {
        HStack {
            // Status icon
            statusIcon(for: state.status)

            Text(state.nodeId)
                .lineLimit(1)

            Spacer()

            // Progress or counts
            if state.fileTotal > 0 {
                Text("\(state.successCount)/\(state.fileTotal)")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)

                if state.errorCount > 0 {
                    Text("(\(state.errorCount) errors)")
                        .font(.caption)
                        .foregroundStyle(.red)
                }
            } else {
                ProgressView(value: state.progress)
                    .frame(width: 60)
            }
        }
    }

    @ViewBuilder
    private func documentProgressRow(_ doc: DocumentProgress) -> some View {
        HStack {
            // Overall status
            if doc.stepStatuses.values.contains(where: {
                if case .failed = $0 { return true }
                return false
            }) {
                Image(systemName: "xmark.circle.fill")
                    .foregroundStyle(.red)
            } else if doc.stepStatuses.values.contains(where: {
                if case .running = $0 { return true }
                return false
            }) {
                ProgressView()
                    .scaleEffect(0.6)
            } else {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(.green)
            }

            Text(doc.documentName)
                .lineLimit(1)

            Spacer()
        }
        .font(.caption)
    }

    @ViewBuilder
    private func statusIcon(for status: NodeExecutionStatus) -> some View {
        switch status {
        case .running, .parallelRunning:
            ProgressView()
                .scaleEffect(0.6)
                .frame(width: 16, height: 16)
        case .completed:
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(.green)
        case .failed:
            Image(systemName: "xmark.circle.fill")
                .foregroundStyle(.red)
        default:
            Image(systemName: "circle")
                .foregroundStyle(.secondary)
        }
    }

    @ViewBuilder
    private var historicalProgressView: some View {
        if isLoadingTimeline {
            ProgressView("Loading progress data...")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let timeline = progressTimeline {
            historicalTimelineView(timeline)
        } else {
            VStack(spacing: 12) {
                // Status badge
                HStack {
                    Image(systemName: ActivityViewHelpers.statusIcon(for: selectedRun.status))
                        .foregroundStyle(ActivityViewHelpers.statusColor(for: selectedRun.status))
                    Text(selectedRun.status.rawValue.capitalized)
                        .font(.headline)
                }

                Text("Completed \(selectedRun.timestamp, style: .relative)")
                    .foregroundStyle(.secondary)

                Text("Progress data not available")
                    .foregroundStyle(.tertiary)
                    .font(.caption)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    @ViewBuilder
    private func historicalTimelineView(_ timeline: ProgressTimeline) -> some View {
        VStack(alignment: .leading, spacing: 20) {
            // Node-level summary
            if !timeline.nodes.isEmpty {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Node Summary")
                        .font(.headline)

                    ForEach(Array(timeline.nodes.keys.sorted()), id: \.self) { nodeId in
                        if let stats = timeline.nodes[nodeId] {
                            nodeStatsRow(nodeId: nodeId, stats: stats)
                        }
                    }
                }
                .padding()
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
            }

            // Execution timeline (nodes + files)
            if !timeline.steps.isEmpty {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Execution Timeline")
                        .font(.headline)

                    ForEach(Array(timeline.steps.enumerated()), id: \.offset) { _, step in
                        if step.isNodeStep {
                            nodeExecutionRow(step)
                        } else if step.isFileStep {
                            fileProgressRow(step)
                                .padding(.leading, 20)  // Indent file steps
                        }
                    }
                }
                .padding()
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
            }
        }
    }

    @ViewBuilder
    private func nodeStatsRow(nodeId: String, stats: NodeProgressStats) -> some View {
        HStack {
            Image(systemName: "square.stack.3d.up")
                .foregroundStyle(.blue)

            VStack(alignment: .leading, spacing: 4) {
                Text(nodeId.prefix(8) + "...")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                HStack(spacing: 16) {
                    Label("\(stats.successCount) success", systemImage: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                    Label("\(stats.errorCount) errors", systemImage: "xmark.circle.fill")
                        .foregroundStyle(.red)
                    Text("of \(stats.totalFiles) total")
                        .foregroundStyle(.secondary)
                }
                .font(.caption)
            }

            Spacer()
        }
    }

    @ViewBuilder
    private func nodeExecutionRow(_ step: ExecutionStep) -> some View {
        HStack(spacing: 12) {
            Image(systemName: step.status == "success" ? "checkmark.circle.fill" :
                              step.status == "error" ? "xmark.circle.fill" : "circle")
                .foregroundStyle(step.status == "success" ? .green :
                                step.status == "error" ? .red : .secondary)

            VStack(alignment: .leading, spacing: 4) {
                Text("Node: \(step.nodeId.prefix(8))...")
                    .font(.caption)
                    .fontWeight(.semibold)

                HStack(spacing: 12) {
                    if let duration = step.durationMs {
                        Text(String(format: "%.1fs", duration / 1000))
                            .font(.caption2)
                    }
                    if let filesProcessed = step.filesProcessed {
                        Text("\(filesProcessed) files")
                            .font(.caption2)
                    }
                    if let artifactsCreated = step.artifactsCreated {
                        Text("\(artifactsCreated) artifacts")
                            .font(.caption2)
                    }
                }
                .foregroundStyle(.secondary)
            }

            Spacer()
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private func fileProgressRow(_ step: ExecutionStep) -> some View {
        HStack(spacing: 12) {
            // Status icon
            Image(systemName: step.status == "success" ? "checkmark.circle.fill" :
                              step.status == "error" ? "xmark.circle.fill" : "circle")
                .foregroundStyle(step.status == "success" ? .green :
                                step.status == "error" ? .red : .secondary)
                .font(.caption)

            VStack(alignment: .leading, spacing: 4) {
                if let filePath = step.filePath {
                    HStack(spacing: 4) {
                        if let fileIndex = step.fileIndex, let fileTotal = step.fileTotal {
                            Text("[\(fileIndex)/\(fileTotal)]")
                                .font(.caption2)
                                .foregroundStyle(.tertiary)
                        }
                        Text(URL(fileURLWithPath: filePath).lastPathComponent)
                            .font(.caption)
                            .lineLimit(1)
                    }
                }

                if let duration = step.durationMs {
                    Text(String(format: "%.2fs", duration / 1000))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                if let error = step.error {
                    Text(error)
                        .font(.caption2)
                        .foregroundStyle(.red)
                        .lineLimit(2)
                }
            }

            Spacer()
        }
        .padding(.vertical, 2)
    }

    private func loadProgressTimeline() async {
        guard let threadId = selectedRun.threadId else { return }

        isLoadingTimeline = true
        defer { isLoadingTimeline = false }

        do {
            let service = ActivityServiceGenerated(apiClient: apiClient)
            _ = try await service.getWorkflowRun(threadId: threadId)

            // Convert progress timeline from dictionary to typed model
            // Note: progressTimeline may not be available in current backend schema
            // TODO: Re-enable when backend schema is updated
            /*
            if let timelineDict = run.progressTimeline {
                let data = try JSONSerialization.data(withJSONObject: timelineDict)
                progressTimeline = try JSONDecoder().decode(ProgressTimeline.self, from: data)
            }
            */
            logger.info("Progress timeline loading disabled - waiting for backend schema update")
        } catch {
            logger.error("Failed to load progress timeline: \(error)")
        }
    }
}

