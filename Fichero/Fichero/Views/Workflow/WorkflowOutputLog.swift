import SwiftUI

/// Output log showing workflow execution progress
struct WorkflowOutputLog: View {
    let workflow: Workflow
    let executionState: WorkflowExecutionState?

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
        .background(Color(.textBackgroundColor))
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

    private var emptyStateView: some View {
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
            Image(systemName: "xmark.circle.fill")
                .foregroundColor(.red)
                .font(.caption2)
                .help(error ?? "Unknown error")
        }
    }
}

// MARK: - Execution State Models

struct WorkflowExecutionState {
    var status: WorkflowStatus
    var documentProgress: [DocumentProgress]
}

enum WorkflowStatus {
    case idle
    case running
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
            ),
        ]
    )
}

// MARK: - Preview

#Preview("Empty") {
    WorkflowOutputLog(
        workflow: Workflow(name: "Test", description: ""),
        executionState: nil
    )
    .frame(width: 600, height: 200)
}
