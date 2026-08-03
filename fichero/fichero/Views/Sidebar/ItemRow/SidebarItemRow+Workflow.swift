import SwiftUI

private struct SidebarWorkflowRequest {
    let workflowId: String
    let docIds: [String]
    let workflowName: String
    let providerOverride: String?
    let modelOverride: String?
}

extension SidebarItemRow {
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
        runWorkflowOnDocuments(
            workflowId: workflowId,
            docIds: [docId],
            providerOverride: providerOverride,
            modelOverride: modelOverride
        )
    }

    /// Runs one sidebar workflow request over the exact resolved file IDs.
    func runWorkflowOnDocuments(
        workflowId: String,
        docIds: [String],
        providerOverride: String? = nil,
        modelOverride: String? = nil
    ) {
        guard !docIds.isEmpty, let library else {
            sidebarRowLogger.error("runWorkflowOnDocuments: no documents or library reference")
            return
        }
        let workflowName = workflowStore?.workflows
            .first(where: { $0.id == workflowId })?.name ?? workflowId
        let stream = library.workflowStreamService
        let observer = executionObserver
        let store = library.documentStore
        let request = SidebarWorkflowRequest(
            workflowId: workflowId,
            docIds: docIds,
            workflowName: workflowName,
            providerOverride: providerOverride,
            modelOverride: modelOverride
        )
        Task { @MainActor in
            await executeSidebarWorkflow(
                request,
                stream: stream,
                store: store,
                observer: observer
            )
        }
    }

    // Extracted from `runWorkflowOnDocument`'s `Task` body: starts the SSE
    // execution, pumps events until completion, and reports the final
    // status. Same order/side effects as before — pure extraction.
    private func executeSidebarWorkflow(
        _ request: SidebarWorkflowRequest,
        stream: WorkflowStreamService,
        store: DocumentStore,
        observer: WorkflowExecutionObserver
    ) async {
        var executionThreadId = "pending:\(UUID().uuidString)"
        observer.startExecution(
            workflowId: request.workflowId,
            name: request.workflowName,
            threadId: executionThreadId
        )
        var streamCompleted = false
        do {
            _ = try await stream.execute(
                workflowId: request.workflowId,
                inputs: ["selected_doc_ids": request.docIds],
                providerOverride: request.providerOverride,
                modelOverride: request.modelOverride,
                // `WorkflowRunTargetResolver` already expanded any folder into
                // its descendants before we got here, so `documents` is the
                // only honest claim — `kind=folder` with N ids is refused at
                // the boundary, and rightly (#4414).
                selection: WorkflowRunScope.documents(request.docIds),
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
            if !streamCompleted {
                // Reconciles against the persisted run record when the SSE
                // stream dies without a terminal frame (#4346/#4349).
                _ = await observer.waitForTerminal(
                    stream: stream,
                    threadId: { executionThreadId },
                    streamCompleted: { streamCompleted }
                )
            }
            let status = sidebarWorkflowFinalStatus(forThreadId: executionThreadId, observer: observer)
            observer.endExecution(threadId: executionThreadId, status: status)
            finishSidebarBusyState(status: status, store: store, observer: observer)
        } catch {
            sidebarRowLogger.error("Sidebar Run Workflow failed: \(error)")
            observer.endExecution(threadId: executionThreadId, status: .failed)
            finishSidebarBusyState(status: .failed, store: store, observer: observer)
        }
    }

    /// Terminal busy-state cleanup (#4346): a run settled by reconciliation
    /// (dead stream) never got its terminal SSE frame, so the event-driven
    /// flush never ran — settle fanout slots, then clear any document still
    /// spinning unless another run is live (its own boundary will clear).
    private func finishSidebarBusyState(
        status: WorkflowStatus,
        store: DocumentStore,
        observer: WorkflowExecutionObserver
    ) {
        store.flushPendingFanoutCompletions(status: status == .completed ? .completed : .failed)
        if !observer.hasRunningExecution {
            store.clearResidualProcessing()
        }
    }

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
        case .cancelled, .error, .systemicError:
            // `.cancelled` is terminal too (#4321/#4346): omitting it left the
            // stream un-completed and every mid-flight document spinning
            // forever after a Stop.
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
        // Deliberate Stop stays `.cancelled`, never rendered as failed (#4321).
        if exec.status == .cancelled { return .cancelled }
        return exec.workflowError != nil || exec.status == .failed ? .failed : .completed
    }
}
