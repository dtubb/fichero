import Foundation
import OSLog

extension WorkflowExecutionObserver {

    // MARK: - Event Handling

    /// Apply one parsed SSE event to the execution tracked under `threadId`.
    ///
    /// The per-event state reduction now lives on `WorkflowExecution.apply(_:)`
    /// (below) so it can be shared with the threadId-keyed `WorkflowExecutionStore`
    /// (#2546) — the Activity monitor reduces the SAME events into the SAME model
    /// without duplicating this logic. This method keeps the observer-specific
    /// concerns: the threadId lookup, the missing-execution warning, the
    /// `fileCompletedCount` inspector signal, and the write-back.
    func handleEvent(_ event: WorkflowStreamEvent, forThreadId threadId: String) {
        // Log every event for debugging
        let eventDesc = String(describing: event).prefix(80)
        workflowExecutionLogger.info("[EVENT] Received: \(eventDesc) for thread: \(threadId)")

        guard var execution = activeExecutions[threadId] else {
            let activeKeys = self.activeExecutions.keys.joined(separator: ", ")
            workflowExecutionLogger.warning(
                "[EVENT] No execution found for thread: \(threadId). Active: \(activeKeys)"
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
        activeExecutions[threadId] = execution
    }
}

// MARK: - Shared Event Reducer

extension WorkflowExecution {

    /// Reduce one parsed SSE event into this execution's state.
    ///
    /// Pure, value-typed, side-effect-free: mutates only `self`. Shared by
    /// `WorkflowExecutionObserver` (keyed by threadId, fed by the launchers) and
    /// `WorkflowExecutionStore` (keyed by threadId, fed by Activity's
    /// subscribe-on-select) — one reducer, two homes (#2546).
    ///
    /// Split into three per-category appliers (lifecycle / node / file) so each
    /// stays within its own bounded switch — cases are mutually exclusive, so
    /// exactly one applier ever mutates `execution` for a given event.
    mutating func apply(_ event: WorkflowStreamEvent) {
        var execution = self
        defer { self = execution }

        execution.applyLifecycleEvent(event)
        execution.applyNodeEvent(event)
        execution.applyFileEvent(event)
    }

    // MARK: - Lifecycle events (workflow-level)

    private mutating func applyLifecycleEvent(_ event: WorkflowStreamEvent) {
        switch event {
        case .start(_, let workflowName):
            applyStart(workflowName: workflowName)
        case .complete:
            applyComplete()
        case .pause:
            applyPause()
        case .cancelled:
            applyCancelled()
        case .error(_, let error):
            applyError(error)
        case .systemicError(_, let error, let errorCount, let totalCount):
            applySystemicError(error: error, errorCount: errorCount, totalCount: totalCount)
        case .log(_, let line):
            applyLog(line)
        default:
            break
        }
    }

    private mutating func applyStart(workflowName: String) {
        workflowExecutionLogger.info("[EVENT] Workflow started: \(workflowName)")
        status = .running
    }

    private mutating func applyComplete() {
        // Check if any node failed - if so, workflow failed
        let hasFailedNodes = nodeStates.values.contains { $0.status == .failed }
        let totalErrors = nodeStates.values.reduce(0) { $0 + $1.errorCount }

        if hasFailedNodes {
            workflowExecutionLogger.warning("Workflow completed with errors: \(totalErrors) file(s) failed")
            status = .failed
            if workflowError == nil {
                workflowError = "\(totalErrors) file(s) failed to process"
            }
        } else {
            workflowExecutionLogger.info("Workflow completed successfully")
            status = .completed
        }
        isRunning = false
    }

    private mutating func applyPause() {
        workflowExecutionLogger.info("Workflow paused")
        status = .paused
        isRunning = false
    }

    private mutating func applyCancelled() {
        workflowExecutionLogger.info("Workflow cancelled")
        status = .failed
        workflowError = "Cancelled by user"
        isRunning = false
    }

    private mutating func applyError(_ error: String) {
        workflowExecutionLogger.error("Workflow error: \(error)")
        status = .failed
        workflowError = error
        isRunning = false
    }

    private mutating func applySystemicError(error: String, errorCount: Int, totalCount: Int) {
        workflowExecutionLogger.error("Systemic error: \(error) (\(errorCount)/\(totalCount) failures)")
        status = .failed
        workflowError = "Systemic error: \(error) (\(errorCount)/\(totalCount) failures)"
        isRunning = false
    }

    private mutating func applyLog(_ line: String) {
        logLines.append(line)
    }

    // MARK: - Node-level events (per-node / per-batch)

    private mutating func applyNodeEvent(_ event: WorkflowStreamEvent) {
        switch event {
        case .nodeBegin(_, let nodeId, let nodeName):
            applyNodeBegin(nodeId: nodeId, nodeName: nodeName)
        case .nodeEnd(_, let nodeId, let durationMs, _):
            applyNodeEnd(nodeId: nodeId, durationMs: durationMs)
        case .parallelStart(_, let nodeId, let fileTotal):
            applyParallelStart(nodeId: nodeId, fileTotal: fileTotal)
        case .parallelComplete(_, let nodeId, let successCount, let errorCount, let total):
            applyParallelComplete(nodeId: nodeId, successCount: successCount, errorCount: errorCount, total: total)
        default:
            break
        }
    }

    private mutating func applyNodeBegin(nodeId: String, nodeName: String) {
        workflowExecutionLogger.info("[EVENT] Node started: \(nodeName) (\(nodeId))")
        // Skip LangGraph internal fan-out/fan-in nodes — not user-visible steps.
        guard !nodeId.hasSuffix("_aggregate"), !nodeId.hasPrefix("branch:to:") else { return }
        var state = nodeStates[nodeId] ?? NodeExecutionState(nodeId: nodeId)
        state.status = .running
        state.progress = 0
        nodeStates[nodeId] = state
        currentNodeId = nodeId
        currentNodeName = nodeName
        // Bind to a local first: Logger's message is an @escaping @autoclosure,
        // and reading nodeStates.count directly would capture mutating self.
        let nodeStateCount = nodeStates.count
        workflowExecutionLogger.info("[EVENT] nodeStates now has \(nodeStateCount) entries")
    }

    private mutating func applyNodeEnd(nodeId: String, durationMs: Double) {
        workflowExecutionLogger.debug("Node completed: \(nodeId) in \(Int(durationMs))ms")
        var state = nodeStates[nodeId] ?? NodeExecutionState(nodeId: nodeId)
        state.status = .completed
        state.progress = 1.0
        nodeStates[nodeId] = state

        // Clear current node tracking when node completes
        if currentNodeId == nodeId {
            currentNodeId = nil
            currentNodeName = nil
        }
    }

    private mutating func applyParallelStart(nodeId: String, fileTotal: Int) {
        workflowExecutionLogger.debug("Parallel start: \(nodeId) - \(fileTotal) files")
        var state = nodeStates[nodeId] ?? NodeExecutionState(nodeId: nodeId)
        state.status = .parallelRunning
        state.progress = 0
        state.fileTotal = fileTotal
        state.successCount = 0
        state.errorCount = 0
        nodeStates[nodeId] = state
        totalFiles = fileTotal
        processedFiles = 0
    }

    private mutating func applyParallelComplete(nodeId: String, successCount: Int, errorCount: Int, total: Int) {
        workflowExecutionLogger.info(
            "Parallel complete: \(nodeId) - \(successCount)/\(total) succeeded, \(errorCount) errors"
        )
        var state = nodeStates[nodeId] ?? NodeExecutionState(nodeId: nodeId)
        state.status = errorCount > 0 ? .failed : .completed
        state.progress = 1.0
        state.successCount = successCount
        state.errorCount = errorCount
        state.fileTotal = total
        nodeStates[nodeId] = state
    }

    // MARK: - File-level events (per-file progress within a parallel batch)

    private mutating func applyFileEvent(_ event: WorkflowStreamEvent) {
        switch event {
        case .fileStart(
            _, let nodeId, let filePath, let fileIndex, let fileTotal, let progress,
            let documentId, let pageId, let displayName, let sequence
        ):
            let identity = FileProgressIdentity(
                filePath: filePath, documentId: documentId, pageId: pageId,
                displayName: displayName, sequence: sequence
            )
            let counters = FileProgressCounters(fileIndex: fileIndex, fileTotal: fileTotal, progress: progress)
            applyFileStart(nodeId: nodeId, filePath: filePath, counters: counters, identity: identity)
        case .fileComplete(
            _, let nodeId, let filePath, let fileIndex, let fileTotal, let progress, let cached,
            let documentId, let pageId, let displayName, let sequence
        ):
            let identity = FileProgressIdentity(
                filePath: filePath, documentId: documentId, pageId: pageId,
                displayName: displayName, sequence: sequence
            )
            let counters = FileProgressCounters(fileIndex: fileIndex, fileTotal: fileTotal, progress: progress)
            applyFileComplete(nodeId: nodeId, counters: counters, cached: cached, identity: identity)
        case .fileError(
            _, let nodeId, let filePath, let error, let progress,
            let documentId, let pageId, let displayName, let sequence
        ):
            let identity = FileProgressIdentity(
                filePath: filePath, documentId: documentId, pageId: pageId,
                displayName: displayName, sequence: sequence
            )
            applyFileError(nodeId: nodeId, error: error, progress: progress, identity: identity)
        default:
            break
        }
    }

    /// Bundles the scalar per-file progress fields shared by `file_start` and
    /// `file_complete`, kept out of the parameter list to stay under the
    /// function-parameter-count limit.
    private struct FileProgressCounters {
        let fileIndex: Int
        let fileTotal: Int
        let progress: Double
    }

    private mutating func applyFileStart(
        nodeId: String, filePath: String, counters: FileProgressCounters, identity: FileProgressIdentity
    ) {
        let fileName = identity.resolvedDisplayName
        workflowExecutionLogger.debug("File start: \(fileName) (\(counters.fileIndex + 1)/\(counters.fileTotal))")

        // Drive `overallProgress` off the accurate processedFiles/totalFiles
        // path. The graph-parallel run path (enable_parallel=True, #2532/#2541)
        // never emits `parallel_start` — only file_start/complete/error — so
        // `totalFiles` would otherwise stay 0 and the Overall Progress bar sat
        // at 0% (#2546 follow-up). The file events carry the same `file_total`
        // `parallel_start` used to; seed it here (max, never shrink).
        if counters.fileTotal > 0 {
            totalFiles = max(totalFiles, counters.fileTotal)
        }

        // Update node state
        var state = nodeStates[nodeId] ?? NodeExecutionState(nodeId: nodeId)
        state.status = .running
        state.progress = counters.progress
        state.fileTotal = counters.fileTotal
        state.currentFile = filePath
        nodeStates[nodeId] = state

        // Update document progress
        var docProgress = documentProgress[identity.stableId] ?? DocumentProgress(
            id: identity.stableId,
            documentName: fileName,
            stepStatuses: [:]
        )
        docProgress.stepStatuses[nodeId] = .running
        documentProgress[identity.stableId] = docProgress
        currentFilePath = filePath
    }

    private mutating func applyFileComplete(
        nodeId: String, counters: FileProgressCounters, cached: Bool, identity: FileProgressIdentity
    ) {
        let fileName = identity.resolvedDisplayName
        workflowExecutionLogger.debug("File complete: \(fileName) (\(counters.fileIndex + 1)/\(counters.fileTotal))")

        // Seed totalFiles here too — a cached file_complete (#700) skips
        // file_start, and a late Activity subscriber may land mid-batch.
        if counters.fileTotal > 0 {
            totalFiles = max(totalFiles, counters.fileTotal)
        }

        // Update node state
        var state = nodeStates[nodeId] ?? NodeExecutionState(nodeId: nodeId)
        state.status = .parallelRunning
        state.progress = counters.progress
        state.fileTotal = counters.fileTotal
        state.successCount += 1
        nodeStates[nodeId] = state

        // Update document progress
        var docProgress = documentProgress[identity.stableId] ?? DocumentProgress(
            id: identity.stableId,
            documentName: fileName,
            stepStatuses: [:]
        )
        docProgress.stepStatuses[nodeId] = .completed(duration: nil, cached: cached)
        documentProgress[identity.stableId] = docProgress

        // Track overall progress
        processedFileIds.insert(identity.stableId)
        processedFiles = processedFileIds.count
        currentFilePath = nil  // Clear current file
        // (The observer raises `fileCompletedCount` in `handleEvent` — it is
        // an observer-level inspector signal, not part of this reducer.)
    }

    private mutating func applyFileError(
        nodeId: String, error: String, progress: Double, identity: FileProgressIdentity
    ) {
        let fileName = identity.resolvedDisplayName
        workflowExecutionLogger.warning("File error: \(fileName) - \(error)")

        // Update node state
        var state = nodeStates[nodeId] ?? NodeExecutionState(nodeId: nodeId)
        state.status = .parallelRunning
        state.progress = progress
        state.errorCount += 1
        state.errorMessage = error
        nodeStates[nodeId] = state

        // Update document progress
        var docProgress = documentProgress[identity.stableId] ?? DocumentProgress(
            id: identity.stableId,
            documentName: fileName,
            stepStatuses: [:]
        )
        docProgress.stepStatuses[nodeId] = .failed(error: error)
        documentProgress[identity.stableId] = docProgress

        // Track overall progress (errors also count as processed)
        processedFileIds.insert(identity.stableId)
        processedFiles = processedFileIds.count
        currentFilePath = nil
    }
}
