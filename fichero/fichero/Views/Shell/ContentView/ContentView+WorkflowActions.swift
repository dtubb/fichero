import OSLog
import SwiftUI

private let workflowLogger = Logger(subsystem: "app.fichero.fichero", category: "ContentView")

extension ContentView {

    // MARK: - Per-step model resolution

    /// The provider/model an UNPINNED chain step must send so the run does
    /// what the bar's sentence promised (Daniel, 2026-09-01). nil for the
    /// common case, where the engine resolves the same tier by itself — see
    /// `WorkflowBarPolicy.implicitRunOverride` for the one exception.
    @MainActor
    func workflowBarImplicitOverride(
        for step: StagedWorkflowStep
    ) -> WorkflowBarModelChoice? {
        WorkflowBarPolicy.implicitRunOverride(
            for: step,
            tools: Array(workflowStore.toolRegistry.values),
            textTier: workflowBarTextTierDefault,
            visionTier: workflowBarVisionTierDefault,
            selectionPrefersVision: selectionPrefersVisionModel
        )
    }

    /// The overrides one staged step rides into the run with: its pin, or the
    /// implicit tier correction, or nothing.
    @MainActor
    func workflowBarRunOverrides(
        for step: StagedWorkflowStep
    ) -> (provider: String?, model: String?) {
        if step.hasModelOverride {
            return (step.providerOverride, step.modelOverride)
        }
        guard let implicit = workflowBarImplicitOverride(for: step) else {
            return (step.providerOverride, step.modelOverride)
        }
        return (implicit.provider, implicit.model)
    }

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
        Task { @MainActor in
            await awaitWorkflowExecution(
                workflowId: workflowId,
                workflowName: workflowName,
                docIds: docIds,
                providerOverride: providerOverride,
                modelOverride: modelOverride
            )
        }
    }

    /// The awaitable form. The fire-and-forget entry point above wraps this in
    /// a Task; the workflow bar's chain awaits it directly, because step two of
    /// a chain must not start until step one has written what it reads
    /// (transcribe, then clean up, then catalogue) — 2026-08-28.
    @MainActor
    @discardableResult
    func awaitWorkflowExecution(
        workflowId: String,
        workflowName: String,
        docIds: [String],
        providerOverride: String? = nil,
        modelOverride: String? = nil,
        /// Set when the run was scoped to ONE artifact (Daniel, 2026-08-29):
        /// rides in the run inputs so an `artifacts_source` step whose config
        /// doesn't pin a type reads THAT artifact instead of its default.
        /// The engine ignores the hint everywhere else, so passing it is
        /// honest — it changes only the step built to consume it.
        artifactTypeHint: String? = nil,
        artifactStepNameHint: String? = nil,
        /// Set on each run of a "Compare models…" fan-out (Daniel,
        /// 2026-08-30): one fresh UUID per fan-out, shared by its runs, so
        /// the artifacts they produce can be lined up later. The engine
        /// ignores unknown inputs today; the compare-reader lane reads it.
        compareGroup: String? = nil,
        /// Called with the SERVER's thread id as soon as the run is accepted,
        /// so a caller can watch a run it is still awaiting — the chain rail
        /// uses it to make a running step clickable (2026-08-28).
        onThreadId: ((String) -> Void)? = nil
    ) async -> String {
        var executionThreadId = "pending:\(UUID().uuidString)"
        // Optimistic insert (#944): show the Activity row immediately, then replace
        // the placeholder thread ID once the POST returns.
        // If the POST fails, the row stays visible and is marked failed.
        executionObserver.startExecution(
            workflowId: workflowId,
            name: workflowName,
            threadId: executionThreadId
        )

        var streamCompleted = false
        // Assembled in one tested place so the framing line and the
        // compare-group stamp cannot drift between call sites.
        let inputs = WorkflowRunInputs.build(
            docIds: docIds,
            userContext: workflowUserContext,
            artifactTypeHint: artifactTypeHint,
            artifactStepNameHint: artifactStepNameHint,
            compareGroup: compareGroup
        )
        do {
                let response = try await workflowStreamService.execute(
                    workflowId: workflowId,
                    surface: "content-selection",
                    inputs: inputs,
                    providerOverride: providerOverride,
                    modelOverride: modelOverride,
                    // These ids came from the user's explicit selection, so
                    // they ARE the scope — nothing for the server to expand,
                    // and nothing left for this client to get wrong (#4414).
                    selection: WorkflowRunScope.documents(docIds),
                    onAccepted: { acceptedResponse in
                        promoteAcceptedRun(acceptedResponse, executionThreadId: &executionThreadId)
                        onThreadId?(executionThreadId)
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
        return executionThreadId
    }

    /// Swap the optimistic placeholder thread id for the server-assigned one
    /// and arm cancellation (#944). Extracted from `executeWorkflowViaSSE`'s
    /// `onAccepted` closure unchanged.
    private func promoteAcceptedRun(
        _ acceptedResponse: ExecuteAcceptedResponse,
        executionThreadId: inout String
    ) {
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
