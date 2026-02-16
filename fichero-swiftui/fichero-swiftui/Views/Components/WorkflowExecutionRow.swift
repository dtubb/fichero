import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "WorkflowExecutionRow")

/// Reusable row view for a running workflow execution
/// Used by RunningSidebarContent and HistorySidebarContent
struct WorkflowExecutionRow: View {
    let execution: WorkflowExecution
    @Environment(WorkflowExecutionObserver.self) var executionObserver
    @State private var isPulsing = false
    @State private var showWorkflowPreview = false

    /// Compact mode hides some details for use in sidebar panels
    var compact: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: compact ? 8 : 12) {
            rowContent
        }
        .padding(.vertical, compact ? 4 : 8)
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
                    .font(compact ? .subheadline.weight(.medium) : .headline)

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

        // Current file being processed (skip in compact mode)
        if !compact, let fileName = execution.currentFileName {
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

        // Node progress summary (skip in compact mode)
        if !compact && !execution.nodeStates.isEmpty {
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

        // View workflow button (skip in compact mode)
        if !compact {
            Button {
                showWorkflowPreview = true
            } label: {
                Label("View Workflow", systemImage: "flowchart")
                    .font(.caption)
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
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

// MARK: - Backward Compatibility Alias

/// Alias for backward compatibility with existing code
typealias RunningWorkflowRow = WorkflowExecutionRow
