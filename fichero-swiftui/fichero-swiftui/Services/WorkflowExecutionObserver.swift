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

            // Remove after delay to let the user see the cancelled state
            Task { [weak self] in
                try? await Task.sleep(for: .seconds(30))
                guard !Task.isCancelled else { return }
                self?.activeExecutions.removeValue(forKey: workflowId)
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
            activeExecutions[workflowId] = execution

            cancelHandlers.removeValue(forKey: workflowId)

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
