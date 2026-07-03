import SwiftUI

// MARK: - Workflow Preview Sheet

/// A sheet showing an animated preview of workflow execution progress
struct WorkflowPreviewSheet: View {
    let execution: WorkflowExecution
    @Environment(\.dismiss) private var dismiss

    private var sortedNodeIds: [String] {
        execution.nodeStates.keys.sorted()
    }

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
                    ForEach(sortedNodeIds, id: \.self) { nodeId in
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
                        .fill(Color.accentColor.opacity(isPulsing ? 0.5 : 0.2))
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
        .background(isCurrentNode ? Color.accentColor.opacity(0.1) : Color(.controlBackgroundColor))
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
