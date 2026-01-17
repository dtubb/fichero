import Foundation
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "WorkflowExecutionObserver")

// MARK: - Workflow Execution

/// Represents an active workflow execution
struct WorkflowExecution: Identifiable {
    let id: String  // workflow ID
    let name: String
    let threadId: String
    let startTime: Date
    var status: WorkflowStatus
    var nodeStates: [String: NodeExecutionState]  // keyed by node ID
    var documentProgress: [String: DocumentProgress]  // keyed by file path
    var currentFilePath: String?
    var currentNodeId: String?
    var currentNodeName: String?
    var isRunning: Bool
    var workflowError: String?
    var totalFiles: Int = 0
    var processedFiles: Int = 0

    /// Ordered document progress for display
    var orderedDocumentProgress: [DocumentProgress] {
        Array(documentProgress.values).sorted { $0.documentName < $1.documentName }
    }

    /// Overall progress (0.0 to 1.0)
    var overallProgress: Double? {
        guard isRunning else { return nil }
        if totalFiles > 0 {
            return Double(processedFiles) / Double(totalFiles)
        }
        let states = nodeStates.values
        guard !states.isEmpty else { return 0 }
        let totalProgress = states.reduce(0.0) { $0 + $1.progress }
        return totalProgress / Double(states.count)
    }

    /// Current file name being processed
    var currentFileName: String? {
        guard let path = currentFilePath else { return nil }
        return (path as NSString).lastPathComponent
    }

    /// Running nodes
    var runningNodes: [NodeExecutionState] {
        nodeStates.values.filter { $0.status == .running || $0.status == .parallelRunning }
    }

    /// Completed nodes count
    var completedNodesCount: Int {
        nodeStates.values.filter { $0.status == .completed }.count
    }
}

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
        logger.info("WorkflowExecutionObserver initialized")
    }

    // MARK: - Execution Lifecycle

    /// Start tracking a workflow execution
    /// - Parameters:
    ///   - workflowId: Unique workflow ID
    ///   - name: Display name of the workflow
    ///   - threadId: Backend thread ID
    ///   - onCancel: Optional closure to call when user cancels
    func startExecution(workflowId: String, name: String, threadId: String, onCancel: (() -> Void)? = nil) {
        logger.info("Starting execution tracking: \(name) (workflow: \(workflowId), thread: \(threadId))")

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
        logger.info("Cancelling workflow: \(workflowId)")

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
        logger.info("Ending execution tracking: \(workflowId) with status \(String(describing: status))")

        if var execution = activeExecutions[workflowId] {
            execution.status = status
            execution.isRunning = false
            // Keep in activeExecutions so UI can show final state
            activeExecutions[workflowId] = execution

            // Remove after a longer delay to allow animations to complete
            // and let the user see the final state
            Task { [weak self] in
                try? await Task.sleep(for: .seconds(30))
                guard !Task.isCancelled else { return }
                self?.activeExecutions.removeValue(forKey: workflowId)
            }
        }
    }

    // MARK: - Event Handling

    /// Handle SSE event and update all relevant state
    func handleEvent(_ event: WorkflowStreamEvent, for workflowId: String) {
        // Log every event for debugging
        logger.info("[EVENT] Received: \(String(describing: event).prefix(80)) for workflow: \(workflowId)")

        guard var execution = activeExecutions[workflowId] else {
            let activeKeys = self.activeExecutions.keys.joined(separator: ", ")
            logger.warning("[EVENT] No execution found for workflow: \(workflowId). Active: \(activeKeys)")
            return
        }

        switch event {
        case .start(_, let workflowName):
            logger.info("[EVENT] Workflow started: \(workflowName)")
            execution.status = .running

        case .nodeBegin(_, let nodeId, let nodeName):
            logger.info("[EVENT] Node started: \(nodeName) (\(nodeId))")
            var state = execution.nodeStates[nodeId] ?? NodeExecutionState(nodeId: nodeId)
            state.status = .running
            state.progress = 0
            execution.nodeStates[nodeId] = state
            execution.currentNodeId = nodeId
            execution.currentNodeName = nodeName
            logger.info("[EVENT] nodeStates now has \(execution.nodeStates.count) entries")

        case .nodeEnd(_, let nodeId, let durationMs, _):
            logger.debug("Node completed: \(nodeId) in \(Int(durationMs))ms")
            var state = execution.nodeStates[nodeId] ?? NodeExecutionState(nodeId: nodeId)
            state.status = .completed
            state.progress = 1.0
            execution.nodeStates[nodeId] = state

        case .parallelStart(_, let nodeId, let fileTotal):
            logger.debug("Parallel start: \(nodeId) - \(fileTotal) files")
            var state = execution.nodeStates[nodeId] ?? NodeExecutionState(nodeId: nodeId)
            state.status = .parallelRunning
            state.progress = 0
            state.fileTotal = fileTotal
            state.successCount = 0
            state.errorCount = 0
            execution.nodeStates[nodeId] = state
            execution.totalFiles = fileTotal
            execution.processedFiles = 0

        case .fileStart(_, let nodeId, let filePath, let fileIndex, let fileTotal, let progress):
            let fileName = (filePath as NSString).lastPathComponent
            logger.debug("File start: \(fileName) (\(fileIndex + 1)/\(fileTotal))")

            // Update node state
            var state = execution.nodeStates[nodeId] ?? NodeExecutionState(nodeId: nodeId)
            state.status = .running
            state.progress = progress
            state.fileTotal = fileTotal
            state.currentFile = filePath
            execution.nodeStates[nodeId] = state

            // Update document progress
            var docProgress = execution.documentProgress[filePath] ?? DocumentProgress(
                id: filePath,
                documentName: fileName,
                stepStatuses: [:]
            )
            docProgress.stepStatuses[nodeId] = .running
            execution.documentProgress[filePath] = docProgress
            execution.currentFilePath = filePath

        case .fileComplete(_, let nodeId, let filePath, let fileIndex, let fileTotal, let progress):
            let fileName = (filePath as NSString).lastPathComponent
            logger.debug("File complete: \(fileName) (\(fileIndex + 1)/\(fileTotal))")

            // Update node state
            var state = execution.nodeStates[nodeId] ?? NodeExecutionState(nodeId: nodeId)
            state.status = .parallelRunning
            state.progress = progress
            state.fileTotal = fileTotal
            state.successCount += 1
            execution.nodeStates[nodeId] = state

            // Update document progress
            var docProgress = execution.documentProgress[filePath] ?? DocumentProgress(
                id: filePath,
                documentName: fileName,
                stepStatuses: [:]
            )
            docProgress.stepStatuses[nodeId] = .completed(duration: nil)
            execution.documentProgress[filePath] = docProgress

            // Track overall progress
            execution.processedFiles += 1
            execution.currentFilePath = nil  // Clear current file

        case .fileError(_, let nodeId, let filePath, let error, let progress):
            let fileName = (filePath as NSString).lastPathComponent
            logger.warning("File error: \(fileName) - \(error)")

            // Update node state
            var state = execution.nodeStates[nodeId] ?? NodeExecutionState(nodeId: nodeId)
            state.status = .parallelRunning
            state.progress = progress
            state.errorCount += 1
            state.errorMessage = error
            execution.nodeStates[nodeId] = state

            // Update document progress
            var docProgress = execution.documentProgress[filePath] ?? DocumentProgress(
                id: filePath,
                documentName: fileName,
                stepStatuses: [:]
            )
            docProgress.stepStatuses[nodeId] = .failed(error: error)
            execution.documentProgress[filePath] = docProgress

            // Track overall progress (errors also count as processed)
            execution.processedFiles += 1
            execution.currentFilePath = nil

        case .parallelComplete(_, let nodeId, let successCount, let errorCount, let total):
            logger.info("Parallel complete: \(nodeId) - \(successCount)/\(total) succeeded, \(errorCount) errors")
            var state = execution.nodeStates[nodeId] ?? NodeExecutionState(nodeId: nodeId)
            state.status = errorCount > 0 ? .failed : .completed
            state.progress = 1.0
            state.successCount = successCount
            state.errorCount = errorCount
            state.fileTotal = total
            execution.nodeStates[nodeId] = state

        case .complete:
            // Check if any node failed - if so, workflow failed
            let hasFailedNodes = execution.nodeStates.values.contains { $0.status == .failed }
            let totalErrors = execution.nodeStates.values.reduce(0) { $0 + $1.errorCount }

            if hasFailedNodes {
                logger.warning("Workflow completed with errors: \(totalErrors) file(s) failed")
                execution.status = .failed
                if execution.workflowError == nil {
                    execution.workflowError = "\(totalErrors) file(s) failed to process"
                }
            } else {
                logger.info("Workflow completed successfully")
                execution.status = .completed
            }
            execution.isRunning = false

        case .pause:
            logger.info("Workflow paused")
            execution.status = .paused

        case .error(_, let error):
            logger.error("Workflow error: \(error)")
            execution.status = .failed
            execution.workflowError = error

        case .systemicError(_, let error, let errorCount, let totalCount):
            logger.error("Systemic error: \(error) (\(errorCount)/\(totalCount) failures)")
            execution.status = .failed
            execution.workflowError = "Systemic error: \(error) (\(errorCount)/\(totalCount) failures)"
        }

        // Save updated execution
        activeExecutions[workflowId] = execution
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
