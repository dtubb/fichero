import Observation
import Foundation
import OSLog

let workflowExecutionLogger = Logger(subsystem: "app.fichero.fichero", category: "WorkflowExecutionObserver")

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

    /// Active executions keyed by thread ID (or a provisional key before the
    /// execute POST returns the real thread ID).
    var activeExecutions: [String: WorkflowExecution] = [:]

    /// Incremented each time any file completes — lets inspectors re-fetch
    /// artifacts without polling. Observed by DocumentInspector.
    var fileCompletedCount: Int = 0

    /// Incremented each time any workflow completes (success or failure).
    /// Drives final artifact refresh for reduce-phase nodes (Catalogue)
    /// that save artifacts after all parallel files are done.
    var workflowCompletedCount: Int = 0

    /// Completed/failed executions archived for the session so Activity tabs
    /// remain populated after a run finishes. Keyed by threadId.
    var completedExecutions: [String: WorkflowExecution] = [:]

    /// Cancel handlers for each execution key (not observable - internal use)
    private var cancelHandlers: [String: () -> Void] = [:]

    // MARK: - Computed Properties

    /// Is any workflow currently running?
    var isAnyWorkflowRunning: Bool {
        !activeExecutions.isEmpty
    }

    /// Get IDs of all running workflows
    var runningWorkflowIds: Set<String> {
        Set(activeExecutions.values.map(\.id))
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
    ///   - workflowId: Workflow definition ID
    ///   - name: Display name of the workflow
    ///   - threadId: Backend thread ID, or a provisional execution key
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

        activeExecutions[threadId] = execution

        if let onCancel {
            cancelHandlers[threadId] = onCancel
        }
    }

    /// Promote a provisional execution key to the real backend thread ID.
    /// This must happen before the stream task starts so early SSE events have
    /// a row to land in.
    func promoteExecution(from provisionalThreadId: String, to threadId: String, onCancel: (() -> Void)? = nil) {
        guard provisionalThreadId != threadId else {
            if let onCancel {
                cancelHandlers[threadId] = onCancel
            }
            return
        }

        if var execution = activeExecutions.removeValue(forKey: provisionalThreadId) {
            execution.threadId = threadId
            activeExecutions[threadId] = execution
        }

        if let cancelHandler = cancelHandlers.removeValue(forKey: provisionalThreadId) {
            cancelHandlers[threadId] = cancelHandler
        }
        if let onCancel {
            cancelHandlers[threadId] = onCancel
        }
    }

    /// Cancel a running workflow
    func cancelExecution(threadId: String) {
        workflowExecutionLogger.info("Cancelling workflow thread: \(threadId)")

        // Call the cancel handler
        if let cancelHandler = cancelHandlers[threadId] {
            cancelHandler()
            cancelHandlers.removeValue(forKey: threadId)
        }

        // Update status
        if var execution = activeExecutions[threadId] {
            execution.status = .failed
            execution.isRunning = false
            execution.workflowError = "Cancelled by user"
            activeExecutions[threadId] = execution

            // Archive after delay so Activity tabs remain readable post-cancel
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(30))
                if let finished = self.activeExecutions.removeValue(forKey: threadId) {
                    self.completedExecutions[threadId] = finished
                }
            }
        }
    }

    /// End tracking for a workflow (call when complete or failed)
    func endExecution(threadId: String, status: WorkflowStatus = .completed) {
        let statusDesc = String(describing: status)
        workflowExecutionLogger.info("Ending execution tracking: \(threadId) with status \(statusDesc)")

        if var execution = activeExecutions[threadId] {
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
            activeExecutions[threadId] = execution

            cancelHandlers.removeValue(forKey: threadId)

            // Signal inspectors that the workflow is done — important for
            // reduce-phase nodes (Catalogue) that save artifacts after all
            // parallel file completions.
            workflowCompletedCount += 1

            // Archive to completedExecutions so Activity tabs remain readable
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(1))
                if let finished = self.activeExecutions.removeValue(forKey: threadId) {
                    self.completedExecutions[threadId] = finished
                    workflowExecutionLogger.info("Archived completed execution: \(threadId)")
                } else {
                    workflowExecutionLogger.warning(
                        "endExecution archive: \(threadId) already removed — possible double-completion"
                    )
                }
            }
        }
    }

    // MARK: - Accessors

    /// Get the execution for a specific workflow
    func getExecution(for workflowId: String) -> WorkflowExecution? {
        latestExecution(for: workflowId, includeCompleted: true)
    }

    /// Get the node states for a specific workflow
    func getNodeStates(for workflowId: String) -> [String: NodeExecutionState]? {
        latestExecution(for: workflowId, includeCompleted: false)?.nodeStates
    }

    /// Get execution state for WorkflowOutputLog
    func getExecutionState(for workflowId: String) -> WorkflowExecutionState? {
        guard let execution = latestExecution(for: workflowId, includeCompleted: true) else { return nil }
        return WorkflowExecutionState(
            status: execution.status,
            documentProgress: execution.orderedDocumentProgress,
            error: execution.workflowError
        )
    }

    /// Check if a specific workflow is running
    func isRunning(workflowId: String) -> Bool {
        activeExecutions.values.contains { $0.id == workflowId && $0.isRunning }
    }

    /// Get progress for a specific workflow (for sidebar)
    func getProgress(for workflowId: String) -> Double? {
        latestExecution(for: workflowId, includeCompleted: false)?.overallProgress
    }

    /// Get the execution for a specific thread, active first then archived.
    func getExecution(threadId: String) -> WorkflowExecution? {
        activeExecutions[threadId] ?? completedExecutions[threadId]
    }

    private func latestExecution(for workflowId: String, includeCompleted: Bool) -> WorkflowExecution? {
        let executions = Array(activeExecutions.values)
            + (includeCompleted ? Array(completedExecutions.values) : [])
        return executions
            .filter { $0.id == workflowId }
            .max { $0.startTime < $1.startTime }
    }
}
