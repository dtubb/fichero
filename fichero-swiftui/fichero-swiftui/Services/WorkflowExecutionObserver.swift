import Foundation
import OSLog

let workflowExecutionLogger = Logger(subsystem: "com.tubb.Fichero", category: "WorkflowExecutionObserver")

// MARK: - WorkflowExecutionObserver

/// Tracks all running workflow executions across the app.
/// Uses Swift Observation framework (@Observable) for efficient SwiftUI updates.
///
/// Usage:
/// - Create at app/window level with @State
/// - Inject via .environment(executionObserver)
/// - Access in views with @Environment(WorkflowExecutionObserver.self)
@MainActor
@Observable
class WorkflowExecutionObserver {

    // MARK: - Observable State

    /// Active executions by workflow ID (supports multiple concurrent)
    var activeExecutions: [String: WorkflowExecution] = [:]

    /// Incremented each time any file completes — lets inspectors re-fetch
    /// artifacts without polling. Observed by DocumentInspector.
    var fileCompletedCount: Int = 0

    /// Incremented each time any workflow completes (success or failure).
    /// Drives final artifact refresh for reduce-phase nodes (Catalogue)
    /// that save artifacts after all parallel files are done.
    var workflowCompletedCount: Int = 0

    /// Completed/failed executions archived for the session so Activity tabs
    /// remain populated after a run finishes. Keyed by workflowId.
    var completedExecutions: [String: WorkflowExecution] = [:]

    /// Cancel handlers for each workflow (not observable - internal use)
    private var cancelHandlers: [String: () -> Void] = [:]

    // MARK: - Computed Properties

    /// Is any workflow currently running?
    var isAnyWorkflowRunning: Bool {
        !activeExecutions.isEmpty
    }

    /// Get IDs of all running workflows
    var runningWorkflowIds: Set<String> {
        Set(activeExecutions.keys)
    }

    // MARK: - Initialization

    init() {
        // Note: SwiftUI may briefly create multiple @State instances during
        // scene setup / preview rendering. Each is scoped to its view's
        // lifetime. Suppress the init log to avoid confusion.
    }

    // MARK: - Execution Lifecycle

    /// Start tracking a workflow execution
    /// - Parameters:
    ///   - workflowId: Unique workflow ID
    ///   - name: Display name of the workflow
    ///   - threadId: Backend thread ID
    ///   - onCancel: Optional closure to call when user cancels
    func startExecution(workflowId: String, name: String, threadId: String, onCancel: (() -> Void)? = nil) {
        workflowExecutionLogger.info(
            "Starting execution tracking: \(name) (workflow: \(workflowId), thread: \(threadId))"
        )

        let execution = WorkflowExecution(
            id: workflowId,
            name: name,
            threadId: threadId,
            startTime: Date(),
            status: .running,
            nodeStates: [:],
            documentProgress: [:],
            currentFilePath: nil,
            currentNodeId: nil,
            currentNodeName: nil,
            isRunning: true,
            workflowError: nil,
            totalFiles: 0,
            processedFiles: 0
        )

        activeExecutions[workflowId] = execution

        if let onCancel = onCancel {
            cancelHandlers[workflowId] = onCancel
        }
    }

    /// Cancel a running workflow
    func cancelExecution(workflowId: String) {
        workflowExecutionLogger.info("Cancelling workflow: \(workflowId)")

        // Call the cancel handler
        if let cancelHandler = cancelHandlers[workflowId] {
            cancelHandler()
            cancelHandlers.removeValue(forKey: workflowId)
        }

        // Update status
        if var execution = activeExecutions[workflowId] {
            execution.status = .failed
            execution.isRunning = false
            execution.workflowError = "Cancelled by user"
            activeExecutions[workflowId] = execution

            // Archive after delay so Activity tabs remain readable post-cancel
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(30))
                if let finished = self.activeExecutions.removeValue(forKey: workflowId) {
                    self.completedExecutions[workflowId] = finished
                }
            }
        }
    }

    /// End tracking for a workflow (call when complete or failed)
    func endExecution(workflowId: String, status: WorkflowStatus = .completed) {
        let statusDesc = String(describing: status)
        workflowExecutionLogger.info("Ending execution tracking: \(workflowId) with status \(statusDesc)")

        if var execution = activeExecutions[workflowId] {
            execution.status = status
            execution.isRunning = false

            // Belt-and-braces: when the run finishes, any node still in a
            // non-terminal state (.running / .parallelRunning / .idle) never
            // received a matching node_end event — this happens when a
            // parallel fan-out's inner-node name doesn't match the outer
            // label the reducer tracks (#699). Force them to a terminal
            // state so the UI doesn't leave a spinner on a completed run.
            let finalStatus: NodeExecutionStatus = (status == .failed) ? .failed : .completed
            for (nodeId, nodeState) in execution.nodeStates {
                if nodeState.status != .completed && nodeState.status != .failed {
                    var fixed = nodeState
                    fixed.status = finalStatus
                    execution.nodeStates[nodeId] = fixed
                }
            }
            activeExecutions[workflowId] = execution

            cancelHandlers.removeValue(forKey: workflowId)

            // Signal inspectors that the workflow is done — important for
            // reduce-phase nodes (Catalogue) that save artifacts after all
            // parallel file completions.
            workflowCompletedCount += 1

            // Archive to completedExecutions so Activity tabs remain readable
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(1))
                if let finished = self.activeExecutions.removeValue(forKey: workflowId) {
                    self.completedExecutions[workflowId] = finished
                    workflowExecutionLogger.info("Archived completed execution: \(workflowId)")
                } else {
                    workflowExecutionLogger.warning("endExecution archive: \(workflowId) already removed — possible double-completion")
                }
            }
        }
    }

    // MARK: - Accessors

    /// Get the execution for a specific workflow
    func getExecution(for workflowId: String) -> WorkflowExecution? {
        activeExecutions[workflowId]
    }

    /// Get the node states for a specific workflow
    func getNodeStates(for workflowId: String) -> [String: NodeExecutionState]? {
        activeExecutions[workflowId]?.nodeStates
    }

    /// Get execution state for WorkflowOutputLog
    func getExecutionState(for workflowId: String) -> WorkflowExecutionState? {
        guard let execution = activeExecutions[workflowId] else { return nil }
        return WorkflowExecutionState(
            status: execution.status,
            documentProgress: execution.orderedDocumentProgress,
            error: execution.workflowError
        )
    }

    /// Check if a specific workflow is running
    func isRunning(workflowId: String) -> Bool {
        activeExecutions[workflowId] != nil
    }

    /// Get progress for a specific workflow (for sidebar)
    func getProgress(for workflowId: String) -> Double? {
        activeExecutions[workflowId]?.overallProgress
    }
}
