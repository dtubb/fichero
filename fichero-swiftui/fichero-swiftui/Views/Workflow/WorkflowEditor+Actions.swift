import SwiftUI
import OSLog

private let actionsLogger = Logger(subsystem: "ca.tubb.Fichero", category: "WorkflowEditor")

extension WorkflowEditor {

    func resetZoom() {
        withAnimation {
            scale = 1.0
        }
    }

    // swiftlint:disable:next function_body_length
    func runWorkflow() {
        isRunning = true
        showOutputLog = true

        // Initialize execution state (will be updated from observer)
        executionState = WorkflowExecutionState(
            status: .running,
            documentProgress: []
        )

        actionsLogger.info("Run workflow: \(editingWorkflow.name)")

        Task { @MainActor in
            do {
                // IMPORTANT: Save workflow before running to ensure backend has latest version
                actionsLogger.info("Auto-saving workflow before execution...")
                let definition = editingWorkflow.toAPIFormat()

                // Debug: Log what we're sending to backend
                actionsLogger.info("[DEBUG] Workflow: id=\(definition.id), nodes=\(definition.nodes.count)")
                for node in definition.nodes {
                    let configDesc = node.config?.keys.joined(separator: ", ") ?? "nil"
                    actionsLogger.info("[DEBUG] Node \(node.tool): config keys=[\(configDesc)]")
                }

                if selectedWorkflow != nil {
                    _ = try await workflowStore.updateWorkflow(definition)
                } else {
                    _ = try await workflowStore.saveWorkflow(definition)
                }
                actionsLogger.info("Workflow saved, now executing with SSE streaming...")

                // Execute workflow with NEW non-blocking API + SSE subscription
                // Single source of truth: all events go through executionObserver
                let workflowId = editingWorkflow.id  // Capture ID before closure

                // Track completion with a continuation
                var streamCompleted = false

                let response = try await workflowStreamService.execute(
                    workflowId: workflowId,
                    inputs: [:],
                    onEvent: { [weak documentStore] event in
                        // Debug: Log every event (using info level for visibility)
                        let eventDesc = String(String(describing: event).prefix(100))
                        actionsLogger.info("[SSE] Event: \(eventDesc)")

                        // Update global observer (single source of truth for all UI)
                        executionObserver.handleEvent(event, for: workflowId)

                        // Debug: Log document progress count
                        if let exec = executionObserver.activeExecutions[workflowId] {
                            let docCount = exec.documentProgress.count
                            let nodeStateCount = exec.nodeStates.count
                            actionsLogger.info(
                                "[SSE] Document count: \(docCount), nodeStates: \(nodeStateCount)"
                            )
                        }

                        // Update executionState from observer (for output log)
                        executionState = executionObserver.getExecutionState(for: workflowId)

                        // Update document processing status in library view
                        updateDocumentStatus(for: event, documentStore: documentStore)

                        // Track terminal events
                        switch event {
                        case .complete, .error, .systemicError:
                            streamCompleted = true
                        default:
                            break
                        }
                    }
                )

                actionsLogger.info("[SSE] Workflow started with thread: \(response.threadId)")

                // Register with global observer for app-wide visibility (with real thread ID)
                let threadId = response.threadId
                executionObserver.startExecution(
                    workflowId: workflowId,
                    name: editingWorkflow.name,
                    threadId: threadId,
                    onCancel: { [weak workflowStreamService] in
                        Task { @MainActor in
                            try? await workflowStreamService?.stopWorkflow(threadId: threadId)
                        }
                    }
                )

                // Wait for stream to complete (poll observer state)
                while !streamCompleted {
                    try await Task.sleep(for: .milliseconds(100))
                    // Check if we're cancelled
                    if Task.isCancelled { break }
                    // Also check observer for completion
                    if let exec = executionObserver.activeExecutions[workflowId],
                       !exec.isRunning {
                        streamCompleted = true
                    }
                }

                // Determine final status from observer
                actionsLogger.info("[SSE] Stream ended, checking final state for workflowId: \(workflowId)")
                if let exec = executionObserver.activeExecutions[workflowId] {
                    let docCount = exec.documentProgress.count
                    let workflowError = exec.workflowError ?? "none"
                    actionsLogger.info(
                        "[SSE] Final documentProgress: \(docCount), error: \(workflowError)"
                    )
                    for (_, progress) in exec.documentProgress {
                        let stepCount = progress.stepStatuses.count
                        actionsLogger.info(
                            "[SSE] Document: \(progress.documentName), statuses: \(stepCount)"
                        )
                    }
                } else {
                    actionsLogger.warning("[SSE] No execution found for workflowId: \(workflowId)")
                }

                let finalStatus: WorkflowStatus
                if let execution = executionObserver.activeExecutions[workflowId] {
                    if execution.workflowError != nil {
                        finalStatus = .failed
                        actionsLogger.error("Workflow failed: \(execution.workflowError ?? "Unknown error")")
                    } else {
                        finalStatus = execution.status == .failed ? .failed : .completed
                        if finalStatus == .completed {
                            actionsLogger.info("Workflow completed successfully")
                        }
                    }
                } else {
                    finalStatus = .completed
                }

                // Final update of execution state from observer (with document progress)
                if var finalState = executionObserver.getExecutionState(for: workflowId) {
                    finalState.status = finalStatus
                    let statusStr = String(describing: finalStatus)
                    let docCount = finalState.documentProgress.count
                    let finalError = finalState.error ?? "none"
                    actionsLogger.info(
                        "[SSE] Final state: \(docCount) docs, status: \(statusStr), error: \(finalError)"
                    )
                    executionState = finalState
                } else {
                    actionsLogger.warning("[SSE] No final state from observer, keeping current executionState")
                    executionState?.status = finalStatus
                }

                // End tracking in global observer
                executionObserver.endExecution(workflowId: workflowId, status: finalStatus)

            } catch {
                actionsLogger.error("Failed to execute workflow: \(error.localizedDescription)")
                executionState?.status = .failed
                executionState?.error = error.localizedDescription

                // End tracking with failed status
                executionObserver.endExecution(workflowId: editingWorkflow.id, status: .failed)
            }

            isRunning = false
        }
    }

    /// Update document processing status in library based on stream events
    func updateDocumentStatus(for event: WorkflowStreamEvent, documentStore: DocumentStore?) {
        guard let documentStore = documentStore else { return }

        switch event {
        case .fileStart(_, _, let filePath, _, _, _):
            documentStore.updateProcessingStatus(forPath: filePath, status: .processing)

        case .fileComplete(_, _, let filePath, _, _, _):
            documentStore.updateProcessingStatus(forPath: filePath, status: .completed)

        case .fileError(_, _, let filePath, _, _):
            documentStore.updateProcessingStatus(forPath: filePath, status: .failed)

        default:
            break
        }
    }

    @MainActor
    func saveWorkflow() async {
        actionsLogger.info("Save workflow: \(editingWorkflow.name)")
        isSaving = true
        saveError = nil

        do {
            let definition = editingWorkflow.toAPIFormat()
            if selectedWorkflow != nil {
                _ = try await workflowStore.updateWorkflow(definition)
            } else {
                _ = try await workflowStore.saveWorkflow(definition)
            }
            actionsLogger.info("Successfully saved workflow")
            showSaveSuccess = true

            // Hide success message after 2 seconds
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(2))
                guard !Task.isCancelled else { return }
                showSaveSuccess = false
            }
        } catch {
            actionsLogger.error("Failed to save workflow: \(error.localizedDescription)")
            saveError = error.localizedDescription
        }

        isSaving = false
    }

    func exportWorkflow() {
        actionsLogger.info("Export workflow: \(editingWorkflow.name)")
        Task { @MainActor in
            await WorkflowExporter.exportToFile(
                editingWorkflow.id,
                name: editingWorkflow.name,
                using: workflowServiceGenerated
            )
        }
    }
}
