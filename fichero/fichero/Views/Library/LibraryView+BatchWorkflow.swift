import FicheroAPIClient
import OSLog
import SwiftUI

// MARK: - Batch Workflow Execution

extension LibraryView {

    private var logger: Logger {
        Logger(subsystem: "app.fichero.fichero", category: "LibraryView")
    }

    /// A workflow id can only be run in the library it will execute against.
    /// Pure so the guard in `runBatchWorkflow` is unit-testable (#3820).
    static func workflowIsRunnable(workflowId: String, in workflows: [WorkflowSidebarItem]) -> Bool {
        workflows.contains { $0.id == workflowId }
    }

    // MARK: - Workflow Execution (replaces batch path)
    /// Execute a workflow via SSE, mirroring the toolbar path in ContentView+Actions.
    /// Passes ALL selected document IDs at once so aggregation workflows (Catalogue)
    /// receive the complete set, and SSE events drive UI refresh.
    @MainActor
    // swiftlint:disable:next function_body_length
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
        guard let library = activeLibraryReference else {
            logger.error("runBatchWorkflow: no library reference — cannot run \(workflowId)")
            return
        }
        let workflows = library.workflowStore.workflows
        // Defensive: only send an id the execution library can resolve. With the
        // coherent context above this holds by construction; the guard stops a
        // stale menu from ever firing a doomed 400 request.
        guard Self.workflowIsRunnable(workflowId: workflowId, in: workflows) else {
            logger.error("runBatchWorkflow: \(workflowId) not in execution library — refusing to send")
            return
        }
        let stream = library.workflowStreamService
        let workflowName = workflows.first(where: { $0.id == workflowId })?.name ?? workflowId

        logger.info("Starting SSE workflow \(workflowId) on \(docIds.count) documents via context menu")

        var executionThreadId = "pending:\(UUID().uuidString)"
        executionObserver.startExecution(
            workflowId: workflowId,
            name: workflowName,
            threadId: executionThreadId
        )
        var streamCompleted = false
        do {
                let response = try await stream.execute(
                    workflowId: workflowId,
                    inputs: ["selected_doc_ids": docIds],
                    providerOverride: providerOverride,
                    modelOverride: modelOverride,
                    onAccepted: { acceptedResponse in
                        let threadId = acceptedResponse.threadId
                        executionObserver.promoteExecution(
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
                    onEvent: { [weak documentStore = library.documentStore] event in
                    if handleBatchWorkflowEvent(
                        event,
                        threadId: executionThreadId,
                        documentStore: documentStore
                    ) {
                        streamCompleted = true
                    }
                }
            )

            let threadId = response.threadId
            logger.info("Started SSE workflow \(workflowId) thread \(threadId) for \(docIds.count) docs")

            while !streamCompleted {
                try await Task.sleep(for: .milliseconds(200))
                if Task.isCancelled { break }
                if let exec = executionObserver.activeExecutions[executionThreadId], !exec.isRunning {
                    streamCompleted = true
                }
            }

            let finalStatus = batchWorkflowFinalStatus(forThreadId: executionThreadId)
            executionObserver.endExecution(threadId: executionThreadId, status: finalStatus)
            logger.info("Workflow \(workflowId) finished with status: \(String(describing: finalStatus))")

        } catch {
            logger.error("executeWorkflowViaSSE failed: \(error.localizedDescription)")
            ErrorService.shared.reportError(error)
            executionObserver.endExecution(threadId: executionThreadId, status: .failed)
        }
    }

    // swiftlint:disable:next cyclomatic_complexity
    private func handleBatchWorkflowEvent(
        _ event: WorkflowStreamEvent,
        threadId: String,
        documentStore: DocumentStore?
    ) -> Bool {
        executionObserver.handleEvent(event, forThreadId: threadId)
        if let store = documentStore {
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
        switch event {
        case .complete:
            documentStore?.flushPendingFanoutCompletions(status: .completed)
            if let documentStore {
                Task { @MainActor in
                    await documentStore.refreshDocumentsByIds(selectedDocumentIdsForBatch)
                }
            }
            return true
        case .error, .systemicError:
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
        return exec.workflowError != nil || exec.status == .failed ? .failed : .completed
    }
}
