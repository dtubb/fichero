import OSLog
import SwiftUI

let actionsLogger = Logger(subsystem: "app.fichero.fichero", category: "WorkflowEditor")

extension WorkflowEditor {

    func resetZoom() {
        withAnimation {
            scale = 1.0
        }
    }

    // swiftlint:disable:next function_body_length cyclomatic_complexity
    func runWorkflow() {
        isRunning = true

        // Register immediately so Activity tab shows "Starting…" before first SSE event
        var executionThreadId = "starting:\(UUID().uuidString)"
        executionObserver.startExecution(
            workflowId: editingWorkflow.id,
            name: editingWorkflow.name,
            threadId: executionThreadId
        )
        openWindow(id: "activity-monitor")

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

                // Resolve source IDs based on workflow-level input source.
                // - collection: run on selected collection/folder
                // - current_selection: run on current multi-selection
                // The Files node reads this from state["selected_doc_ids"].
                let selectedIds: [String]
                switch editingWorkflow.inputSource {
                case .collection:
                    if let collectionId = documentStore.selectedCollection?.id {
                        selectedIds = [collectionId]
                    } else if let docId = documentStore.selectedDocument?.id {
                        selectedIds = [docId]
                    } else {
                        selectedIds = []
                    }
                case .currentSelection:
                    if !selectedDocumentIds.isEmpty {
                        selectedIds = selectedDocumentIds
                    } else if let docId = documentStore.selectedDocument?.id {
                        selectedIds = [docId]
                    } else {
                        selectedIds = []
                    }
                }
                if selectedIds.isEmpty {
                    actionsLogger.warning(
                        "runWorkflow: no input resolved for source=\(editingWorkflow.inputSource.rawValue)"
                    )
                }

                // Track completion with a continuation
                var streamCompleted = false

                let response = try await workflowStreamService.execute(
                    workflowId: workflowId,
                    inputs: ["selected_doc_ids": selectedIds],
                    onAccepted: { acceptedResponse in
                        let threadId = acceptedResponse.threadId
                        executionObserver.promoteExecution(
                            from: executionThreadId,
                            to: threadId,
                            onCancel: { [weak workflowStreamService] in
                                Task { @MainActor in
                                    try? await workflowStreamService?.stopWorkflow(threadId: threadId)
                                }
                            }
                        )
                        executionThreadId = threadId
                    },
                    onEvent: { [weak documentStore] event in
                        // Debug: Log every event (using info level for visibility)
                        let eventDesc = String(String(describing: event).prefix(100))
                        actionsLogger.info("[SSE] Event: \(eventDesc)")

                        // Update global observer (single source of truth for all UI)
                        executionObserver.handleEvent(event, forThreadId: executionThreadId)

                        // Debug: Log document progress count
                        if let exec = executionObserver.activeExecutions[executionThreadId] {
                            let docCount = exec.documentProgress.count
                            let nodeStateCount = exec.nodeStates.count
                            actionsLogger.info(
                                "[SSE] Document count: \(docCount), nodeStates: \(nodeStateCount)"
                            )
                        }

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

                // Wait for stream to complete (poll observer state)
                while !streamCompleted {
                    try await Task.sleep(for: .milliseconds(100))
                    // Check if we're cancelled
                    if Task.isCancelled { break }
                    // Also check observer for completion
                    if let exec = executionObserver.activeExecutions[executionThreadId],
                       !exec.isRunning {
                        streamCompleted = true
                    }
                }

                // Determine final status from observer
                actionsLogger.info("[SSE] Stream ended, checking final state for workflowId: \(workflowId)")
                if let exec = executionObserver.activeExecutions[executionThreadId] {
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
                if let execution = executionObserver.activeExecutions[executionThreadId] {
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

                // End tracking in global observer
                executionObserver.endExecution(threadId: executionThreadId, status: finalStatus)

            } catch {
                actionsLogger.error("Failed to execute workflow: \(error.localizedDescription)")

                // End tracking with failed status
                executionObserver.endExecution(threadId: executionThreadId, status: .failed)
            }

            isRunning = false
        }
    }

    /// Update document processing status in library based on stream events
    func updateDocumentStatus(for event: WorkflowStreamEvent, documentStore: DocumentStore?) {
        guard let documentStore = documentStore else { return }

        switch event {
        case .fileStart:
            if let identity = event.fileProgressIdentity {
                documentStore.updateProcessingStatus(for: identity, status: .processing)
            }

        case .fileComplete:
            // Defer the green checkmark — reduce-phase nodes may still
            // be touching this page (#948).
            if let identity = event.fileProgressIdentity {
                documentStore.recordFanoutComplete(for: identity)
            }

        case .fileError:
            if let identity = event.fileProgressIdentity {
                documentStore.updateProcessingStatus(for: identity, status: .failed)
            }

        case .complete:
            documentStore.flushPendingFanoutCompletions(status: .completed)

        case .error, .systemicError:
            documentStore.flushPendingFanoutCompletions(status: .failed)

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

    func importWorkflow() {
        actionsLogger.info("Import workflow from editor")
        Task { @MainActor in
            do {
                _ = try await WorkflowExporter.importFromFile(using: workflowServiceGenerated)
                await workflowStore.loadWorkflows()
            } catch {
                actionsLogger.error("Failed to import workflow: \(error.localizedDescription)")
                saveError = error.localizedDescription
            }
        }
    }
}
