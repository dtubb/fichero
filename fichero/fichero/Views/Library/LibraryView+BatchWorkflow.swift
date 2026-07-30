import FicheroAPIClient
import OSLog
import SwiftUI

// MARK: - Batch Workflow Execution

/// Mutable box carrying the in-flight execution's thread id, promoted from a
/// pending placeholder to the server-assigned id once the SSE request is accepted.
/// A reference type so escaping closures and the awaiting caller observe the same value.
private final class BatchWorkflowThreadId {
    var value: String
    init(_ value: String) { self.value = value }
}

/// Parameters for one SSE batch-workflow run — bundled so
/// `executeBatchWorkflowStream` stays under the parameter-count limit.
private struct BatchWorkflowRequest {
    let workflowId: String
    let docIds: [String]
    let providerOverride: String?
    let modelOverride: String?
}

extension LibraryView {

    private var logger: Logger {
        Logger(subsystem: "app.fichero.fichero", category: "LibraryView")
    }

    /// A workflow id can only be run in the library it will execute against.
    /// Pure so the guard in `runBatchWorkflow` is unit-testable (#3820).
    static func workflowIsRunnable(workflowId: String, in workflows: [WorkflowSidebarItem]) -> Bool {
        workflows.contains { $0.id == workflowId && $0.canRunDirectly }
    }

    // MARK: - Workflow Execution (replaces batch path)
    /// Execute a workflow via SSE, mirroring the toolbar path in ContentView+Actions.
    /// Passes ALL selected document IDs at once so aggregation workflows (Catalogue)
    /// receive the complete set, and SSE events drive UI refresh.
    @MainActor
    func runBatchWorkflow(
        workflowId: String,
        providerOverride: String? = nil,
        modelOverride: String? = nil
    ) async {
        guard !selectedDocumentIdsForBatch.isEmpty else { return }

        let docIds = selectedDocumentIdsForBatch
        // #3820 — run through the SAME library reference that sourced the
        // Run-Workflow menu (`libraryWorkflows` → `activeLibraryReference`), NOT
        // the environment's shared WorkflowStreamService. When those diverged
        // (the window's library vs. the global fallback), the menu offered a
        // workflow_id unresolvable in the execution's library → engine 400 on
        // single items. The sidebar path already binds list + execution to one
        // library (which is why folders worked); mirror that here.
        guard let context = resolveBatchWorkflowContext(workflowId: workflowId) else { return }

        logger.info("Starting SSE workflow \(workflowId) on \(docIds.count) documents via context menu")

        let threadId = BatchWorkflowThreadId("pending:\(UUID().uuidString)")
        executionObserver.startExecution(
            workflowId: workflowId,
            name: context.workflowName,
            threadId: threadId.value
        )

        do {
            let request = BatchWorkflowRequest(
                workflowId: workflowId,
                docIds: docIds,
                providerOverride: providerOverride,
                modelOverride: modelOverride
            )
            try await executeBatchWorkflowStream(request, library: context.library, threadId: threadId)
            let finalStatus = batchWorkflowFinalStatus(forThreadId: threadId.value)
            executionObserver.endExecution(threadId: threadId.value, status: finalStatus)
            finishBatchBusyState(status: finalStatus, store: context.library.documentStore)
            logger.info("Workflow \(workflowId) finished with status: \(String(describing: finalStatus))")
        } catch {
            logger.error("executeWorkflowViaSSE failed: \(error.localizedDescription)")
            ErrorService.shared.reportError(error)
            executionObserver.endExecution(threadId: threadId.value, status: .failed)
            finishBatchBusyState(status: .failed, store: context.library.documentStore)
        }
    }

    /// Terminal busy-state cleanup (#4346): a run settled by reconciliation
    /// (dead stream) never got its terminal SSE frame, so the event-driven
    /// flush never ran — settle fanout slots, then clear any document still
    /// spinning unless another run is live (its own boundary will clear).
    private func finishBatchBusyState(status: WorkflowStatus, store: DocumentStore) {
        store.flushPendingFanoutCompletions(status: status == .completed ? .completed : .failed)
        if !executionObserver.hasRunningExecution {
            store.clearResidualProcessing()
        }
    }

    /// Issue the SSE workflow request and drive it to completion, mutating `threadId`
    /// in place as the observer promotes it from a pending placeholder to the real
    /// server-assigned id. A reference type so the mutation is visible both inside
    /// the escaping `onAccepted`/`onEvent` closures and after `await` resumes.
    private func executeBatchWorkflowStream(
        _ request: BatchWorkflowRequest,
        library: LibraryManager.LibraryReference,
        threadId: BatchWorkflowThreadId
    ) async throws {
        let stream = library.workflowStreamService
        var streamCompleted = false
        let response = try await stream.execute(
            workflowId: request.workflowId,
            inputs: ["selected_doc_ids": request.docIds],
            providerOverride: request.providerOverride,
            modelOverride: request.modelOverride,
            onAccepted: { acceptedResponse in
                let acceptedThreadId = acceptedResponse.threadId
                executionObserver.promoteExecution(
                    from: threadId.value,
                    to: acceptedThreadId,
                    onCancel: { [weak stream] in
                        Task { @MainActor in
                            try? await stream?.stopWorkflow(threadId: acceptedThreadId)
                        }
                    }
                )
                threadId.value = acceptedThreadId
            },
            onEvent: { [weak documentStore = library.documentStore] event in
                if handleBatchWorkflowEvent(
                    event,
                    threadId: threadId.value,
                    documentStore: documentStore
                ) {
                    streamCompleted = true
                }
            }
        )

        logger.info(
            "Started SSE workflow \(request.workflowId) thread \(response.threadId) for \(request.docIds.count) docs"
        )

        if !streamCompleted {
            // Reconciles against the persisted run record when the SSE stream
            // dies without a terminal frame (#4346/#4349).
            _ = await executionObserver.waitForTerminal(
                stream: stream,
                threadId: { threadId.value },
                streamCompleted: { streamCompleted }
            )
        }
    }

    /// Resolve and validate the library + workflow name a batch run should execute
    /// against. Defensive: only returns an id the execution library can resolve, so a
    /// stale menu never fires a doomed 400 request.
    private func resolveBatchWorkflowContext(
        workflowId: String
    ) -> (library: LibraryManager.LibraryReference, workflowName: String)? {
        guard let library = activeLibraryReference else {
            logger.error("runBatchWorkflow: no library reference — cannot run \(workflowId)")
            return nil
        }
        let workflows = library.workflowStore.workflows
        guard Self.workflowIsRunnable(workflowId: workflowId, in: workflows) else {
            logger.error("runBatchWorkflow: \(workflowId) not in execution library — refusing to send")
            return nil
        }
        let workflowName = workflows.first(where: { $0.id == workflowId })?.name ?? workflowId
        return (library, workflowName)
    }

    private func handleBatchWorkflowEvent(
        _ event: WorkflowStreamEvent,
        threadId: String,
        documentStore: DocumentStore?
    ) -> Bool {
        executionObserver.handleEvent(event, forThreadId: threadId)
        updateFanoutProgress(for: event, store: documentStore)
        return handleBatchWorkflowCompletion(event, documentStore: documentStore)
    }

    private func updateFanoutProgress(for event: WorkflowStreamEvent, store: DocumentStore?) {
        guard let store else { return }
        switch event {
        case .fileStart:
            if let identity = event.fileProgressIdentity {
                store.updateProcessingStatus(for: identity, status: .processing)
            }
        case .fileComplete:
            if let identity = event.fileProgressIdentity {
                store.recordFanoutComplete(for: identity)
                if let documentId = identity.leafDocumentId {
                    Task { @MainActor in
                        await store.refreshDocumentsByIds([documentId])
                    }
                }
            }
        case .fileError:
            if let identity = event.fileProgressIdentity {
                store.updateProcessingStatus(for: identity, status: .failed)
            }
        default:
            break
        }
    }

    private func handleBatchWorkflowCompletion(_ event: WorkflowStreamEvent, documentStore: DocumentStore?) -> Bool {
        switch event {
        case .complete:
            documentStore?.flushPendingFanoutCompletions(status: .completed)
            if let documentStore {
                Task { @MainActor in
                    await documentStore.refreshDocumentsByIds(selectedDocumentIdsForBatch)
                }
            }
            return true
        case .cancelled, .error, .systemicError:
            documentStore?.flushPendingFanoutCompletions(status: .failed)
            return true
        default:
            return false
        }
    }

    private func batchWorkflowFinalStatus(forThreadId threadId: String) -> WorkflowStatus {
        guard let exec = executionObserver.activeExecutions[threadId] else {
            return .completed
        }
        // Deliberate Stop stays `.cancelled`, never rendered as failed (#4321).
        if exec.status == .cancelled { return .cancelled }
        return exec.workflowError != nil || exec.status == .failed ? .failed : .completed
    }
}
