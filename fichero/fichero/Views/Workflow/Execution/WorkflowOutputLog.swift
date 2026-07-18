import OSLog
import SwiftUI

let workflowOutputLogger = Logger(subsystem: "app.fichero.fichero", category: "WorkflowOutputLog")

/// Output log showing workflow execution progress
struct WorkflowOutputLog: View {
    let workflow: Workflow

    /// Optional passed-in state (for when execution is in progress)
    var executionStateOverride: WorkflowExecutionState?

    /// Access the observer for persisted state
    @Environment(WorkflowExecutionObserver.self) var executionObserver

    /// Effective execution state - prefer observer state for persistence
    var executionState: WorkflowExecutionState? {
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

    /// Source tools gather input files but do not process them per-file, so they
    /// never emit fileStart/fileComplete events. Showing them as Output Log columns
    /// produces an all-"-" column that adds noise without value.
    private static let sourceTools: Set<String> = ["files", "collection", "folder", "search"]

    private var processingNodes: [WorkflowNode] {
        workflow.nodes.filter { !Self.sourceTools.contains($0.tool) }
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

    // MARK: - Progress Table

    private func progressTable(state: WorkflowExecutionState) -> some View {
        VStack(spacing: 0) {
            if state.status == .failed, let error = state.error {
                errorBanner(error: error)
            }

            ScrollView {
                Grid(alignment: .leading, horizontalSpacing: 0, verticalSpacing: 0) {
                    tableHeaderRow
                    Divider()
                    ForEach(state.documentProgress) { progress in
                        tableRow(for: progress)
                        Divider()
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
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
        GridRow {
            Text("Document")
                .font(.caption)
                .fontWeight(.semibold)
                .frame(width: 150, alignment: .leading)
                .padding(.horizontal, 8)
                .padding(.vertical, 6)
                .background(Color(.controlBackgroundColor))

            ForEach(processingNodes) { node in
                Text(node.label ?? node.tool)
                    .font(.caption)
                    .fontWeight(.semibold)
                    .frame(width: 80, alignment: .center)
                    .padding(.vertical, 6)
                    .background(Color(.controlBackgroundColor))
            }
        }
    }

    private func tableRow(for progress: DocumentProgress) -> some View {
        GridRow {
            Text(progress.documentName)
                .font(.caption)
                .lineLimit(1)
                .frame(width: 150, alignment: .leading)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)

            ForEach(processingNodes) { node in
                stepStatusCell(for: progress.stepStatuses[node.id])
                    .frame(width: 80)
                    .padding(.vertical, 4)
            }
        }
    }

    // MARK: - Empty States

    @ViewBuilder
    private var emptyStateView: some View {
        if let state = executionState, state.status == .failed {
            errorStateView(error: state.error)
        } else if let state = executionState, state.status == .completed, state.documentProgress.isEmpty {
            warningStateView
        } else {
            defaultEmptyStateView
        }
    }

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
