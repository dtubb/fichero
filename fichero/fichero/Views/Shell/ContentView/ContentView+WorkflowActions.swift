import OSLog
import SwiftUI

private let workflowLogger = Logger(subsystem: "app.fichero.fichero", category: "ContentView")

extension ContentView {

    // MARK: - Workflow Actions

    func addNodeFromTool(_ tool: ToolInfo, at position: CGPoint) {
        let newNode = WorkflowNode(from: tool, positionX: position.x, positionY: position.y)
        editingWorkflow.nodes.append(newNode)
        workflowLogger.info("Added node '\(tool.displayName)' at (\(position.x), \(position.y))")
    }

    @MainActor
    func autoSaveWorkflow(workflowId: String, workflow: Workflow) async {
        guard !workflow.nodes.isEmpty || !workflow.name.isEmpty else {
            workflowLogger.info("Auto-save skipped: empty workflow")
            return
        }

        // Locked system presets (Default Workflows) are read-only by design
        // (#4514): the server 403s any PUT, so firing the request only
        // produced "Auto-save failed: Unexpected response from server" ×N
        // while a locked preset was merely SELECTED. The editor knows the
        // flag — don't send the request at all. Check both the editor copy
        // and the canonical sidebar row so a stale editor snapshot can't
        // sneak one through.
        let canonical = workflowStore.workflows.first(where: { $0.id == workflowId })
        guard WorkflowSavePolicy.canAutoSave(
            editorIsSystem: workflow.isSystem,
            canonicalIsSystem: canonical?.isSystem
        ) else {
            workflowLogger.info("Auto-save skipped: '\(workflow.name)' is a read-only system workflow")
            return
        }

        workflowLogger.info("Auto-saving workflow: \(workflow.name) (id: \(workflowId))")
        for node in workflow.nodes {
            let provider = node.providerName ?? "nil"
            let model = node.modelName ?? "nil"
            print(
                "[DEBUG SAVE] Node \(node.id): providerName=\(provider), modelName=\(model)"
            )
        }
        do {
            var workflowForSave = workflow

            // If sidebar/workflow-store metadata has a newer name, prefer it to prevent
            // stale editor state from clobbering a just-renamed workflow.
            if let canonical = workflowStore.workflows.first(where: { $0.id == workflowId }),
               workflowForSave.name != canonical.name {
                workflowLogger.info(
                    "Auto-save name reconciliation: '\(workflowForSave.name)' -> '\(canonical.name)' for \(workflowId)"
                )
                workflowForSave.name = canonical.name
            }

            let definition = workflowForSave.toAPIFormat()
            _ = try await workflowStore.updateWorkflow(definition)
            workflowLogger.info("Auto-save completed for workflow: \(workflowId)")
        } catch {
            workflowLogger.error("Auto-save failed: \(error.localizedDescription)")
        }
    }

    // MARK: - Workflow Execution

    @MainActor
    func runWorkflowOnSelection(
        workflowId: String,
        preselectedIds: [String] = [],
        providerOverride: String? = nil,
        modelOverride: String? = nil
    ) {
        // #4523: read the WINDOW's effective selection (live, or preserved
        // across the navigation that cleared it) — one accessor, every launch
        // surface agrees on what "the selection" means.
        let effective = effectiveWorkflowRunSelection
        let selectedIds = !preselectedIds.isEmpty
            ? preselectedIds
            : (effective.isEmpty
                ? (detailDocument.map { [$0.id] } ?? [])
                : effective)
        guard !selectedIds.isEmpty else {
            workflowLogger.warning("runWorkflowOnSelection: no selection — nothing to run")
            importError = "Select one or more documents before running a workflow."
            return
        }

        let workflowName = workflowStore.workflows.first(where: { $0.id == workflowId })?.name ?? workflowId
        let noun = selectedIds.count == 1 ? "document" : "documents"
        importProgress = "Starting workflow on \(selectedIds.count) \(noun)…"

        executeWorkflowViaSSE(
            workflowId: workflowId,
            workflowName: workflowName,
            docIds: selectedIds,
            providerOverride: providerOverride,
            modelOverride: modelOverride
        )
    }

    // `runWorkflowOnCollection` is DELETED (#4396). It took every `.file` in
    // `documentStore.currentDocuments` and never consulted the selection, and
    // it had no callers — a scope-widening path with no trigger is a loaded
    // gun, not dead weight, and the next person to need "run on this folder"
    // would have reached for it. When that command is genuinely wanted it must
    // be a deliberately named one ("Run on all documents in this folder") that
    // states its scope and asks first, per `WorkflowRunScope`.

    /// Shared SSE execution path used by both selection and collection runs.
    /// Registers with executionObserver so Activity view shows live progress.
    @MainActor
    private func executeWorkflowViaSSE(
        workflowId: String,
        workflowName: String,
        docIds: [String],
        providerOverride: String? = nil,
        modelOverride: String? = nil
    ) {
        var executionThreadId = "pending:\(UUID().uuidString)"
        // Optimistic insert (#944): show the Activity row immediately, then replace
        // the placeholder thread ID once the POST returns.
        // If the POST fails, the row stays visible and is marked failed.
        executionObserver.startExecution(
            workflowId: workflowId,
            name: workflowName,
            threadId: executionThreadId
        )

        Task { @MainActor in
            var streamCompleted = false
            do {
                let response = try await workflowStreamService.execute(
                    workflowId: workflowId,
                    inputs: ["selected_doc_ids": docIds],
                    providerOverride: providerOverride,
                    modelOverride: modelOverride,
                    // These ids came from the user's explicit selection, so
                    // they ARE the scope — nothing for the server to expand,
                    // and nothing left for this client to get wrong (#4414).
                    selection: WorkflowRunScope.documents(docIds),
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
                        if handleWorkflowStreamEvent(
                            event,
                            threadId: executionThreadId,
                            documentStore: documentStore
                        ) {
                            streamCompleted = true
                        }
                    }
                )

                importProgress = nil
                workflowLogger.info("Started SSE workflow \(workflowId) thread \(response.threadId) for \(docIds.count) docs")

                await settleWorkflowRun(
                    threadId: { executionThreadId },
                    workflowId: workflowId,
                    docIds: docIds,
                    streamCompleted: { streamCompleted }
                )
            } catch {
                failWorkflowStart(threadId: executionThreadId, error: error)
            }
        }
    }

    /// Wait out a stream that ended without a terminal frame, then run the
    /// post-completion bookkeeping. Reconciles against the persisted run
    /// record when the SSE stream dies mid-run (#4346/#4349) — the old poll
    /// loop hung forever in that case.
    @MainActor
    private func settleWorkflowRun(
        threadId: @escaping () -> String,
        workflowId: String,
        docIds: [String],
        streamCompleted: @escaping () -> Bool
    ) async {
        var completed = streamCompleted()
        if !completed {
            completed = await executionObserver.waitForTerminal(
                stream: workflowStreamService,
                threadId: threadId,
                streamCompleted: streamCompleted
            )
        }
        await finishWorkflowExecution(
            threadId: threadId(),
            workflowId: workflowId,
            docIds: docIds,
            streamCompleted: completed
        )
    }

    /// A run that never started: mark the optimistic Activity row failed and
    /// clear any processing state it would have owned.
    @MainActor
    private func failWorkflowStart(threadId: String, error: Error) {
        importProgress = nil
        importError = "Workflow failed to start: \(error.localizedDescription)"
        workflowLogger.error("executeWorkflowViaSSE failed: \(error.localizedDescription)")
        executionObserver.endExecution(threadId: threadId, status: .failed)
        documentStore.flushPendingFanoutCompletions(status: .failed)
        if !executionObserver.hasRunningExecution {
            documentStore.clearResidualProcessing()
        }
    }

    /// Post-completion bookkeeping for a workflow run. A completed workflow
    /// (e.g. Transcribe) may have written new per-page content backend-side, so
    /// re-fetch the affected documents before ending execution — the Content/
    /// transcript pane then shows fresh text instead of stale in-memory content,
    /// and the inspector's `workflowCompletedCount` observers see the refreshed
    /// data. (#1445)
    @MainActor
    private func finishWorkflowExecution(
        threadId: String,
        workflowId: String,
        docIds: [String],
        streamCompleted: Bool
    ) async {
        if streamCompleted {
            await documentStore.refreshDocumentsByIds(docIds)
        }
        let finalStatus = workflowFinalStatus(forThreadId: threadId)
        executionObserver.endExecution(threadId: threadId, status: finalStatus)
        // A run settled by reconciliation (dead stream, #4346/#4349) never got
        // its terminal SSE frame, so the event-driven flush never ran: settle
        // fanout slots, then clear any document still spinning — unless
        // another run is live (its own terminal boundary will clear).
        documentStore.flushPendingFanoutCompletions(
            status: finalStatus == .completed ? .completed : .failed
        )
        if !executionObserver.hasRunningExecution {
            documentStore.clearResidualProcessing()
        }
        workflowLogger.info(
            "Workflow \(workflowId) finished with status: \(String(describing: finalStatus))"
        )
    }

    private func handleWorkflowStreamEvent(
        _ event: WorkflowStreamEvent,
        threadId: String,
        documentStore: DocumentStore?
    ) -> Bool {
        executionObserver.handleEvent(event, forThreadId: threadId)
        updateDocumentStatusFromEvent(event, documentStore: documentStore)
        return event.isTerminal
    }

    private func workflowFinalStatus(forThreadId threadId: String) -> WorkflowStatus {
        guard let exec = executionObserver.activeExecutions[threadId] else {
            return .completed
        }
        // A deliberate Stop (or server-side cancellation surfaced by
        // reconciliation) stays `.cancelled` — never rendered as failed (#4321).
        if exec.status == .cancelled { return .cancelled }
        return exec.workflowError != nil || exec.status == .failed ? .failed : .completed
    }

    private func updateDocumentStatusFromEvent(
        _ event: WorkflowStreamEvent,
        documentStore: DocumentStore?
    ) {
        guard let documentStore else { return }
        switch event {
        case .fileStart:
            if let identity = event.fileProgressIdentity {
                documentStore.updateProcessingStatus(for: identity, status: .processing)
            }
        case .fileComplete:
            // Per-file fanout slot finished, but reduce-phase nodes
            // (extract_all etc.) may still be touching this page. Defer
            // the green checkmark until the workflow's terminal event.
            // See DocumentStore.recordFanoutComplete + flushPendingFanoutCompletions (#948).
            if let identity = event.fileProgressIdentity {
                documentStore.recordFanoutComplete(for: identity)
            }
        case .fileError:
            if let identity = event.fileProgressIdentity {
                documentStore.updateProcessingStatus(for: identity, status: .failed)
            }
        case .complete:
            documentStore.flushPendingFanoutCompletions(status: .completed)
        case .cancelled, .error, .systemicError:
            documentStore.flushPendingFanoutCompletions(status: .failed)
        default:
            break
        }
    }
}
