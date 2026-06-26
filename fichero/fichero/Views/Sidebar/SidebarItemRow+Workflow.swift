import SwiftUI

extension SidebarItemRow {
    // swiftlint:disable function_body_length
    /// Run a workflow on this sidebar document via the same SSE path that
    /// ContentView's toolbar/menubar/grid-context-menu use. Previously this
    /// went through BatchService.createBatch + executeBatch, which produced
    /// an executing run that the Activity view didn't register (BatchService
    /// path doesn't notify executionObserver), so users reported "context
    /// menu Run Workflow doesn't work" while the toolbar one did. Converging
    /// on the SSE path is #694's fix.
    func runWorkflowOnDocument(
        workflowId: String,
        docId: String,
        providerOverride: String? = nil,
        modelOverride: String? = nil
    ) {
        guard let library = library else {
            sidebarRowLogger.error("runWorkflowOnDocument: no library reference")
            return
        }
        let workflowName = workflowStore?.workflows
            .first(where: { $0.id == workflowId })?.name ?? workflowId
        let stream = library.workflowStreamService
        let observer = executionObserver
        Task { @MainActor in
            var executionThreadId = "pending:\(UUID().uuidString)"
            observer.startExecution(
                workflowId: workflowId,
                name: workflowName,
                threadId: executionThreadId
            )
            var streamCompleted = false
            do {
                let store = library.documentStore
                _ = try await stream.execute(
                    workflowId: workflowId,
                    inputs: ["selected_doc_ids": [docId]],
                    providerOverride: providerOverride,
                    modelOverride: modelOverride,
                    onAccepted: { acceptedResponse in
                        let threadId = acceptedResponse.threadId
                        observer.promoteExecution(
                            from: executionThreadId,
                            to: threadId,
                            onCancel: { [weak stream] in
                                Task { @MainActor in
                                    try? await stream?.stopWorkflow(threadId: threadId)
                                }
                            }
                        )
                        executionThreadId = threadId
                    },
                    onEvent: { event in
                        if handleSidebarWorkflowEvent(
                            event,
                            threadId: executionThreadId,
                            store: store,
                            observer: observer
                        ) {
                            streamCompleted = true
                        }
                    }
                )
                while !streamCompleted {
                    try await Task.sleep(for: .milliseconds(200))
                    if Task.isCancelled { break }
                    if let exec = observer.activeExecutions[executionThreadId], !exec.isRunning {
                        streamCompleted = true
                    }
                }
                let status = sidebarWorkflowFinalStatus(forThreadId: executionThreadId, observer: observer)
                observer.endExecution(threadId: executionThreadId, status: status)
            } catch {
                sidebarRowLogger.error("Sidebar Run Workflow failed: \(error)")
                observer.endExecution(threadId: executionThreadId, status: .failed)
            }
        }
    }
    // swiftlint:enable function_body_length

    private func handleSidebarWorkflowEvent(
        _ event: WorkflowStreamEvent,
        threadId: String,
        store: DocumentStore,
        observer: WorkflowExecutionObserver
    ) -> Bool {
        observer.handleEvent(event, forThreadId: threadId)
        // Per-doc spinner: mirror SSE file events to Document.status so
        // grid icons + sidebar folders show processing state.
        switch event {
        case .fileStart:
            if let identity = event.fileProgressIdentity {
                store.updateProcessingStatus(for: identity, status: .processing)
            }
        case .fileComplete:
            // Defer the green checkmark until workflow.complete so reduce-phase
            // nodes can keep processing the page.
            if let identity = event.fileProgressIdentity {
                store.recordFanoutComplete(for: identity)
            }
        case .fileError:
            if let identity = event.fileProgressIdentity {
                store.updateProcessingStatus(for: identity, status: .failed)
            }
        default:
            break
        }
        switch event {
        case .complete:
            store.flushPendingFanoutCompletions(status: .completed)
            return true
        case .error, .systemicError:
            store.flushPendingFanoutCompletions(status: .failed)
            return true
        default:
            return false
        }
    }

    private func sidebarWorkflowFinalStatus(
        forThreadId threadId: String,
        observer: WorkflowExecutionObserver
    ) -> WorkflowStatus {
        guard let exec = observer.activeExecutions[threadId] else { return .completed }
        return exec.workflowError != nil || exec.status == .failed ? .failed : .completed
    }
}
