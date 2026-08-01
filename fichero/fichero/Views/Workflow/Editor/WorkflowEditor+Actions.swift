import OSLog
import SwiftUI

let actionsLogger = Logger(subsystem: "app.fichero.fichero", category: "WorkflowEditor")

@MainActor
private final class WorkflowRunCompletion {
    private var continuation: CheckedContinuation<Void, Never>?
    /// Readable from the run body so the stream-end reconciliation can skip
    /// the network round-trip when a terminal frame already settled the run
    /// (#4457) — `onStreamEnd` fires on EVERY stream end, healthy or not.
    private(set) var isFinished = false

    /// Status read back from the PERSISTED run record when the stream died
    /// without a terminal frame (#4457). Carried here rather than in a captured
    /// local `var`, because this object is a reference the callbacks already
    /// hold — mutating a captured variable from the stream-end callback would
    /// be a concurrent mutation.
    ///
    /// It exists because `computeFinalStatus` reads the OBSERVER, and on a dead
    /// stream the observer never saw a terminal event: it would report the run
    /// `.completed` on the "no error seen" branch, claiming a success that
    /// never happened. When set, this is the authoritative answer.
    private(set) var reconciledStatus: WorkflowStatus?

    func finish(reconciled: WorkflowStatus? = nil) {
        guard !isFinished else { return }
        if let reconciled { reconciledStatus = reconciled }
        isFinished = true
        continuation?.resume()
        continuation = nil
    }

    func wait() async {
        guard !isFinished else { return }
        await withCheckedContinuation { continuation in
            self.continuation = continuation
        }
    }
}

extension WorkflowEditor {

    func resetZoom() {
        withAnimation {
            scale = 1.0
        }
    }

    func runWorkflow() {
        isRunning = true
        let executionThreadId = beginWorkflowExecutionTracking()

        Task { @MainActor in
            await performWorkflowRun(executionThreadId: executionThreadId)
            isRunning = false
        }
    }

    /// Registers the run with the execution observer and surfaces the Activity
    /// monitor window, returning the temporary thread id used until the
    /// backend hands back its own.
    private func beginWorkflowExecutionTracking() -> String {
        // Register immediately so Activity tab shows "Starting…" before first SSE event
        let executionThreadId = "starting:\(UUID().uuidString)"
        executionObserver.startExecution(
            workflowId: editingWorkflow.id,
            name: editingWorkflow.name,
            threadId: executionThreadId
        )
        // The workflow still runs; only skip popping the monitor window on
        // single-window platforms (iPhone), where it's a silent no-op (#2805).
        if supportsMultipleWindows {
            openWindow(id: "activity-monitor")
        }

        actionsLogger.info("Run workflow: \(editingWorkflow.name)")
        return executionThreadId
    }

    private func performWorkflowRun(executionThreadId initialThreadId: String) async {
        var executionThreadId = initialThreadId
        do {
            try await autoSaveWorkflowBeforeRun()

            // Execute workflow with NEW non-blocking API + SSE subscription
            // Single source of truth: all events go through executionObserver
            let workflowId = editingWorkflow.id  // Capture ID before closure

            let scope = resolveRunScope()
            let selectedIds = scope.docIds
            warnIfNoInputResolved(selectedIds)
            // State the scope in the run record so a widened run is
            // recognisable afterwards, not only by its effects (#4396).
            actionsLogger.info(
                "Workflow run scope: \(scope.describedScope, privacy: .public)"
            )

            let completion = WorkflowRunCompletion()

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
                    // (#3191) Dropped the per-event info logs ("[SSE] Event",
                    // "[SSE] Document count") — they fired for every token /
                    // progress frame, flooding the log for the whole run.

                    // Update global observer (single source of truth for all UI)
                    executionObserver.handleEvent(event, forThreadId: executionThreadId)

                    // Update document processing status in library view
                    updateDocumentStatus(for: event, documentStore: documentStore)

                    // Track terminal events
                    if event.isTerminal {
                        completion.finish()
                    }
                },
                // #4457: the run used to settle ONLY on a terminal frame, so a
                // transport death mid-run left `completion.wait()` suspended
                // forever. See `reconcileStreamEnd`.
                onStreamEnd: {
                    reconcileStreamEnd(completion: completion, threadId: executionThreadId)
                }
            )

            actionsLogger.info("[SSE] Workflow started with thread: \(response.threadId)")

            await completion.wait()

            logFinalExecutionState(executionThreadId: executionThreadId, workflowId: workflowId)
            // #4457: the persisted record wins when the stream died without a
            // terminal frame. `computeFinalStatus` reads the observer, which in
            // that case never saw a terminal event and falls through to
            // `.completed` — reporting a success the run never had.
            let finalStatus = completion.reconciledStatus
                ?? computeFinalStatus(executionThreadId: executionThreadId)

            // End tracking in global observer
            executionObserver.endExecution(threadId: executionThreadId, status: finalStatus)

        } catch {
            actionsLogger.error("Failed to execute workflow: \(error.localizedDescription)")

            // End tracking with failed status
            executionObserver.endExecution(threadId: executionThreadId, status: .failed)
        }
    }

    /// Saves the in-progress workflow before running it, so the backend has
    /// the latest version.
    private func autoSaveWorkflowBeforeRun() async throws {
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
    }

    /// Resolves source IDs based on workflow-level input source.
    /// - collection: run on selected collection/folder
    /// - current_selection: run on current multi-selection
    /// The Files node reads this from state["selected_doc_ids"].
    /// #4396: the run's scope, decided by `WorkflowRunScope` — one place, and
    /// a SELECTION ALWAYS WINS.
    ///
    /// This used to switch on `editingWorkflow.inputSource` and, for
    /// `.collection`, return the folder id without ever consulting the
    /// selection. Since `.collection` is the default everywhere (model init,
    /// definition init, and the decoder's `?? .collection`), running a
    /// collection-authored workflow — Catalogue — with one PDF selected sent
    /// the folder and the engine expanded it.
    private func resolveRunScope() -> WorkflowRunScope.Resolution {
        WorkflowRunScope.resolve(
            inputSource: editingWorkflow.inputSource,
            selection: selectedDocumentIds,
            collectionId: documentStore.selectedCollection?.id,
            fallbackDocumentId: documentStore.selectedDocument?.id
        )
    }

    private func warnIfNoInputResolved(_ selectedIds: [String]) {
        guard selectedIds.isEmpty else { return }
        actionsLogger.warning(
            "runWorkflow: no input resolved for source=\(editingWorkflow.inputSource.rawValue)"
        )
    }

    /// Determine final status from observer
    private func logFinalExecutionState(executionThreadId: String, workflowId: String) {
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
    }

    /// Settle a run whose SSE stream ended (#4457).
    ///
    /// Fires on EVERY stream end, healthy or not, so the already-finished case
    /// returns immediately and the happy path costs nothing. When the stream
    /// died without a terminal frame, no `complete`/`error`/`cancelled` event
    /// can ever arrive — the run used to wait for one forever, leaking a
    /// continuation and spinning the editor's run UI indefinitely while the
    /// Activity surface reconciled the same run correctly (#4380/#4403 class).
    ///
    /// A `nil` settle means the bounded poll ran out, NOT that the run is still
    /// going. Finish regardless: the whole point is that nothing else is
    /// coming, so waiting longer only strands the UI.
    private func reconcileStreamEnd(completion: WorkflowRunCompletion, threadId: String) {
        guard !completion.isFinished else { return }
        Task { @MainActor in
            let settled = await workflowStreamService.settleAfterStreamEnd(threadId: threadId)
            completion.finish(
                reconciled: settled.map { WorkflowExecution.workflowStatus(from: $0.status) }
            )
        }
    }

    private func computeFinalStatus(executionThreadId: String) -> WorkflowStatus {
        guard let execution = executionObserver.activeExecutions[executionThreadId] else {
            return .completed
        }
        if execution.workflowError != nil {
            actionsLogger.error("Workflow failed: \(execution.workflowError ?? "Unknown error")")
            return .failed
        }
        let finalStatus: WorkflowStatus = execution.status == .failed ? .failed : .completed
        if finalStatus == .completed {
            actionsLogger.info("Workflow completed successfully")
        }
        return finalStatus
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

        case .cancelled, .error, .systemicError:
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
                using: workflowService
            )
        }
    }

    func importWorkflow() {
        actionsLogger.info("Import workflow from editor")
        Task { @MainActor in
            do {
                _ = try await WorkflowExporter.importFromFile(using: workflowService)
                await workflowStore.loadWorkflows()
            } catch {
                actionsLogger.error("Failed to import workflow: \(error.localizedDescription)")
                saveError = error.localizedDescription
            }
        }
    }
}
