import OSLog
import SwiftUI

let workflowExecutionRowLogger = Logger(subsystem: "com.tubb.Fichero", category: "WorkflowExecutionRow")

/// Reusable row view for a running workflow execution
/// Used by RunningSidebarContent and HistorySidebarContent
struct WorkflowExecutionRow: View {
    let execution: WorkflowExecution
    @Environment(WorkflowExecutionObserver.self) var executionObserver
    @State var isPulsing = false
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

}

// MARK: - Backward Compatibility Alias

/// Alias for backward compatibility with existing code
typealias RunningWorkflowRow = WorkflowExecutionRow
