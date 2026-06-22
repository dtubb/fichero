import Foundation
import OSLog

extension WorkflowExecutionObserver {

    // MARK: - Event Handling

    /// Apply one parsed SSE event to the execution tracked under `workflowId`.
    ///
    /// The per-event state reduction now lives on `WorkflowExecution.apply(_:)`
    /// (below) so it can be shared with the threadId-keyed `WorkflowExecutionStore`
    /// (#2546) — the Activity monitor reduces the SAME events into the SAME model
    /// without duplicating this logic. This method keeps the observer-specific
    /// concerns: the workflowId lookup, the missing-execution warning, the
    /// `fileCompletedCount` inspector signal, and the write-back.
    func handleEvent(_ event: WorkflowStreamEvent, for workflowId: String) {
        // Log every event for debugging
        let eventDesc = String(describing: event).prefix(80)
        workflowExecutionLogger.info("[EVENT] Received: \(eventDesc) for workflow: \(workflowId)")

        guard var execution = activeExecutions[workflowId] else {
            let activeKeys = self.activeExecutions.keys.joined(separator: ", ")
            workflowExecutionLogger.warning(
                "[EVENT] No execution found for workflow: \(workflowId). Active: \(activeKeys)"
            )
            return
        }

        execution.apply(event)

        // Inspector signal: a file finished — let DocumentInspector re-fetch
        // artifacts without polling. (Observer-only concern, not part of the
        // shared reducer.)
        if case .fileComplete = event {
            fileCompletedCount += 1
        }

        // Save updated execution
        activeExecutions[workflowId] = execution
    }
}

// MARK: - Shared Event Reducer

extension WorkflowExecution {

    // swiftlint:disable function_body_length cyclomatic_complexity
    /// Reduce one parsed SSE event into this execution's state.
    ///
    /// Pure, value-typed, side-effect-free: mutates only `self`. Shared by
    /// `WorkflowExecutionObserver` (keyed by workflowId, fed by the editor) and
    /// `WorkflowExecutionStore` (keyed by threadId, fed by Activity's
    /// subscribe-on-select) — one reducer, two homes (#2546).
    mutating func apply(_ event: WorkflowStreamEvent) {
        var execution = self
        defer { self = execution }

        switch event {
        case .start(_, let workflowName):
            workflowExecutionLogger.info("[EVENT] Workflow started: \(workflowName)")
            execution.status = .running

        case .nodeBegin(_, let nodeId, let nodeName):
            workflowExecutionLogger.info("[EVENT] Node started: \(nodeName) (\(nodeId))")
            // Skip LangGraph internal fan-out/fan-in nodes — not user-visible steps.
            guard !nodeId.hasSuffix("_aggregate"), !nodeId.hasPrefix("branch:to:") else { break }
            var state = execution.nodeStates[nodeId] ?? NodeExecutionState(nodeId: nodeId)
            state.status = .running
            state.progress = 0
            execution.nodeStates[nodeId] = state
            execution.currentNodeId = nodeId
            execution.currentNodeName = nodeName
            workflowExecutionLogger.info("[EVENT] nodeStates now has \(execution.nodeStates.count) entries")

        case .nodeEnd(_, let nodeId, let durationMs, _):
            workflowExecutionLogger.debug("Node completed: \(nodeId) in \(Int(durationMs))ms")
            var state = execution.nodeStates[nodeId] ?? NodeExecutionState(nodeId: nodeId)
            state.status = .completed
            state.progress = 1.0
            execution.nodeStates[nodeId] = state

            // Clear current node tracking when node completes
            if execution.currentNodeId == nodeId {
                execution.currentNodeId = nil
                execution.currentNodeName = nil
            }

        case .parallelStart(_, let nodeId, let fileTotal):
            workflowExecutionLogger.debug("Parallel start: \(nodeId) - \(fileTotal) files")
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
            workflowExecutionLogger.debug("File start: \(fileName) (\(fileIndex + 1)/\(fileTotal))")

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

        case .fileComplete(_, let nodeId, let filePath, let fileIndex, let fileTotal, let progress, let cached):
            let fileName = (filePath as NSString).lastPathComponent
            workflowExecutionLogger.debug("File complete: \(fileName) (\(fileIndex + 1)/\(fileTotal))")

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
            docProgress.stepStatuses[nodeId] = .completed(duration: nil, cached: cached)
            execution.documentProgress[filePath] = docProgress

            // Track overall progress
            execution.processedFiles += 1
            execution.currentFilePath = nil  // Clear current file
            // (The observer raises `fileCompletedCount` in `handleEvent` — it is
            // an observer-level inspector signal, not part of this reducer.)

        case .fileError(_, let nodeId, let filePath, let error, let progress):
            let fileName = (filePath as NSString).lastPathComponent
            workflowExecutionLogger.warning("File error: \(fileName) - \(error)")

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
            workflowExecutionLogger.info(
                "Parallel complete: \(nodeId) - \(successCount)/\(total) succeeded, \(errorCount) errors"
            )
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
                workflowExecutionLogger.warning("Workflow completed with errors: \(totalErrors) file(s) failed")
                execution.status = .failed
                if execution.workflowError == nil {
                    execution.workflowError = "\(totalErrors) file(s) failed to process"
                }
            } else {
                workflowExecutionLogger.info("Workflow completed successfully")
                execution.status = .completed
            }
            execution.isRunning = false

        case .pause:
            workflowExecutionLogger.info("Workflow paused")
            execution.status = .paused

        case .error(_, let error):
            workflowExecutionLogger.error("Workflow error: \(error)")
            execution.status = .failed
            execution.workflowError = error
            execution.isRunning = false

        case .systemicError(_, let error, let errorCount, let totalCount):
            workflowExecutionLogger.error("Systemic error: \(error) (\(errorCount)/\(totalCount) failures)")
            execution.status = .failed
            execution.workflowError = "Systemic error: \(error) (\(errorCount)/\(totalCount) failures)"
            execution.isRunning = false

        case .log(_, let line):
            execution.logLines.append(line)
        }
    }
    // swiftlint:enable function_body_length cyclomatic_complexity
}
