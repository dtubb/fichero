import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "WorkflowOutputLog")

/// Output log showing workflow execution progress
struct WorkflowOutputLog: View {
    let workflow: Workflow

    /// Optional passed-in state (for when execution is in progress)
    var executionStateOverride: WorkflowExecutionState?

    /// Access the observer for persisted state
    @Environment(WorkflowExecutionObserver.self) var executionObserver

    /// Effective execution state - prefer observer state for persistence
    private var executionState: WorkflowExecutionState? {
        // Try observer first (persists across view switches)
        if let observerState = executionObserver.getExecutionState(for: workflow.id) {
            return observerState
        }
        // Fall back to passed state
        if let override = executionStateOverride {
            return override
        }
        return nil
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            headerView
            Divider()
            contentView
        }
        .background(Color(.windowBackgroundColor))
    }

    // MARK: - Header

    private var headerView: some View {
        HStack {
            Label("Output Log", systemImage: "list.bullet.rectangle")
                .font(.subheadline)
                .fontWeight(.medium)

            Spacer()

            if let state = executionState {
                statusBadge(for: state.status)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color(.windowBackgroundColor))
    }

    // MARK: - Content

    @ViewBuilder
    private var contentView: some View {
        if let state = executionState, !state.documentProgress.isEmpty {
            progressTable(state: state)
        } else {
            emptyStateView
        }
    }

    private func progressTable(state: WorkflowExecutionState) -> some View {
        VStack(spacing: 0) {
            // Error banner if workflow failed
            if state.status == .failed, let error = state.error {
                errorBanner(error: error)
            }

            ScrollView {
                VStack(spacing: 0) {
                    // Table header
                    tableHeaderRow

                    Divider()

                    // Table rows
                    ForEach(state.documentProgress) { progress in
                        tableRow(for: progress)
                        Divider()
                    }
                }
            }
        }
        .background(Color(.textBackgroundColor))
    }

    private func errorBanner(error: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(.white)
            Text(error)
                .font(.caption)
                .fontWeight(.medium)
                .foregroundColor(.white)
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color.red)
    }

    private var tableHeaderRow: some View {
        HStack(spacing: 0) {
            Text("Document")
                .font(.caption)
                .fontWeight(.semibold)
                .frame(width: 150, alignment: .leading)
                .padding(.horizontal, 8)

            ForEach(workflow.nodes) { node in
                Text(node.label ?? node.tool)
                    .font(.caption)
                    .fontWeight(.semibold)
                    .frame(width: 80, alignment: .center)
            }

            Spacer()
        }
        .padding(.vertical, 6)
        .background(Color(.controlBackgroundColor))
    }

    private func tableRow(for progress: DocumentProgress) -> some View {
        HStack(spacing: 0) {
            Text(progress.documentName)
                .font(.caption)
                .lineLimit(1)
                .frame(width: 150, alignment: .leading)
                .padding(.horizontal, 8)

            ForEach(workflow.nodes) { node in
                stepStatusCell(for: progress.stepStatuses[node.id])
                    .frame(width: 80)
            }

            Spacer()
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private var emptyStateView: some View {
        // Show error message if workflow failed
        if let state = executionState, state.status == .failed {
            errorStateView(error: state.error)
        } else if let state = executionState, state.status == .completed, state.documentProgress.isEmpty {
            // Completed but no documents processed - show warning
            warningStateView
        } else {
            // Normal empty state
            VStack(spacing: 8) {
                Image(systemName: "doc.text.magnifyingglass")
                    .font(.title2)
                    .foregroundColor(.secondary)

                Text("No output yet")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Text("Run the workflow to see processing results")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(.textBackgroundColor))
        }
    }

    private func errorStateView(error: String?) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.title)
                .foregroundColor(.red)

            Text("Workflow Failed")
                .font(.headline)
                .foregroundColor(.primary)

            if let error = error {
                Text(error)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 20)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(.textBackgroundColor))
    }

    private var warningStateView: some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.circle.fill")
                .font(.title)
                .foregroundColor(.orange)

            Text("No Documents Processed")
                .font(.headline)
                .foregroundColor(.primary)

            Text("""
                The workflow completed but didn't process any documents.
                Check that the source node has a valid collection selected.
                """)
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 20)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(.textBackgroundColor))
    }

    // MARK: - Status Views

    @ViewBuilder
    private func statusBadge(for status: WorkflowStatus) -> some View {
        HStack(spacing: 4) {
            statusIcon(for: status)
            statusText(for: status)
        }
        .font(.caption)
        .foregroundColor(.secondary)
    }

    @ViewBuilder
    private func statusIcon(for status: WorkflowStatus) -> some View {
        switch status {
        case .idle:
            Circle()
                .fill(Color.secondary)
                .frame(width: 6, height: 6)
        case .running:
            ProgressView()
                .scaleEffect(0.6)
        case .paused:
            Image(systemName: "pause.circle.fill")
                .foregroundColor(.orange)
        case .completed:
            Image(systemName: "checkmark.circle.fill")
                .foregroundColor(.green)
        case .failed:
            Image(systemName: "xmark.circle.fill")
                .foregroundColor(.red)
        }
    }

    private func statusText(for status: WorkflowStatus) -> Text {
        switch status {
        case .idle: return Text("Idle")
        case .running: return Text("Running")
        case .paused: return Text("Paused")
        case .completed: return Text("Completed")
        case .failed: return Text("Failed")
        }
    }

    @ViewBuilder
    private func stepStatusCell(for status: StepStatus?) -> some View {
        HStack(spacing: 4) {
            if let status = status {
                stepStatusView(status)
            } else {
                Text("-")
                    .foregroundColor(.secondary)
            }
        }
        .font(.caption)
    }

    @ViewBuilder
    private func stepStatusView(_ status: StepStatus) -> some View {
        switch status {
        case .pending:
            Circle()
                .stroke(Color.secondary, lineWidth: 1)
                .frame(width: 12, height: 12)
        case .running:
            ProgressView()
                .scaleEffect(0.5)
        case .completed(let duration):
            HStack(spacing: 2) {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(.green)
                    .font(.caption2)
                if let duration = duration {
                    Text(String(format: "%.1fs", duration))
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }
        case .failed(let error):
            ErrorStatusCell(error: error)
        }
    }

}

// MARK: - Error Status Cell

/// Clickable error cell that shows full error in a popover
private struct ErrorStatusCell: View {
    let error: String?
    @State private var showingPopover = false

    var body: some View {
        Button {
            showingPopover.toggle()
        } label: {
            HStack(spacing: 2) {
                Image(systemName: "xmark.circle.fill")
                    .foregroundColor(.red)
                    .font(.caption2)
                if let error = error {
                    Text(simplifyError(error))
                        .font(.caption2)
                        .foregroundColor(.red)
                        .lineLimit(1)
                }
            }
        }
        .buttonStyle(.plain)
        .popover(isPresented: $showingPopover, arrowEdge: .bottom) {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundColor(.red)
                    Text("Error Details")
                        .font(.headline)
                    Spacer()
                    Button {
                        showingPopover = false
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                }

                Divider()

                if let error = error {
                    Text(error)
                        .font(.system(.body, design: .monospaced))
                        .textSelection(.enabled)
                        .frame(maxWidth: 400, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                } else {
                    Text("Unknown error")
                        .foregroundColor(.secondary)
                }

                HStack {
                    Spacer()
                    Button("Copy") {
                        if let error = error {
                            NSPasteboard.general.clearContents()
                            NSPasteboard.general.setString(error, forType: .string)
                        }
                    }
                    .buttonStyle(.bordered)
                }
            }
            .padding()
            .frame(minWidth: 300, maxWidth: 450)
        }
        .help(error ?? "Unknown error")
    }

    /// Extract the key part of an error message for display
    private func simplifyError(_ error: String) -> String {
        // Handle common error patterns
        if error.contains("402") || error.lowercased().contains("insufficient credits") {
            return "No credits"
        }
        if error.contains("401") || error.lowercased().contains("unauthorized") {
            return "Auth error"
        }
        if error.contains("timeout") || error.contains("timed out") {
            return "Timeout"
        }
        if error.contains("429") || error.lowercased().contains("rate limit") {
            return "Rate limit"
        }
        if error.contains("500") || error.contains("internal server") {
            return "Server error"
        }
        // Truncate long errors
        if error.count > 15 {
            return String(error.prefix(12)) + "..."
        }
        return error
    }
}

// MARK: - Execution State Models

struct WorkflowExecutionState {
    var status: WorkflowStatus
    var documentProgress: [DocumentProgress]
    var error: String?
}

enum WorkflowStatus {
    case idle
    case running
    case paused
    case completed
    case failed
}

struct DocumentProgress: Identifiable {
    let id: String
    let documentName: String
    var stepStatuses: [String: StepStatus]
}

enum StepStatus {
    case pending
    case running
    case completed(duration: Double?)
    case failed(error: String?)
}

// MARK: - Mock Execution State

extension WorkflowExecutionState {
    static let sample = WorkflowExecutionState(
        status: .running,
        documentProgress: [
            DocumentProgress(
                id: "doc-1",
                documentName: "letter_001.jpg",
                stepStatuses: [
                    "step-1": .completed(duration: 2.3),
                    "step-2": .running,
                    "step-3": .pending
                ]
            ),
            DocumentProgress(
                id: "doc-2",
                documentName: "letter_002.jpg",
                stepStatuses: [
                    "step-1": .completed(duration: 1.8),
                    "step-2": .pending,
                    "step-3": .pending
                ]
            ),
            DocumentProgress(
                id: "doc-3",
                documentName: "letter_003.jpg",
                stepStatuses: [
                    "step-1": .pending,
                    "step-2": .pending,
                    "step-3": .pending
                ]
            )
        ]
    )
}

// MARK: - Preview

#Preview("Empty") {
    WorkflowOutputLog(
        workflow: Workflow(name: "Test", description: ""),
        executionStateOverride: nil
    )
    .environment(WorkflowExecutionObserver())
    .frame(width: 600, height: 200)
}
