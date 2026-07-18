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

    // MARK: - Navigation

    func navigateToDocument(_ doc: Document) {
        viewMode = .library(doc)
        sidebarSelectionState.selectedItemId = "doc:\(doc.id)"
    }

    /// Open the source page behind a KG entity click. The source claim
    /// points at a page-level document (path=nil, parent = the real file
    /// per #701). Resolution:
    ///   1. Fetch the source doc by id.
    ///   2. If it's a page child (no path), walk up to the parent file —
    ///      that's the thing the user actually wants to look at.
    ///   3. Navigate to the parent FOLDER (so the file appears in the
    ///      grid) and select the file via browserSelection so the
    ///      preview pane opens it.
    /// Falls through silently if the source can't be resolved — a click
    /// shouldn't crash and we don't have a UI surface for "couldn't
    /// resolve source" yet. (#833)
    @MainActor
    func navigateToSourcePage(_ sourceDocId: String) async {
        let source: Document
        do {
            source = try await documentStore.documentService.getDocument(sourceDocId)
        } catch {
            workflowLogger.warning("navigateToSourcePage: couldn't fetch \(sourceDocId): \(error.localizedDescription)")
            return
        }

        // Resolve "the file the user wants" — page children (path == nil)
        // bubble up to their parent file; everything else is its own target.
        let target: Document
        let sourceIsPageChild = source.path?.isEmpty ?? true
        if sourceIsPageChild {
            // First try: use the parentId field if available
            if let parentId = source.parentId, !parentId.isEmpty {
                do {
                    target = try await documentStore.documentService.getDocument(parentId)
                } catch {
                    // Fallback: use the new /documents/{id}/parent endpoint
                    do {
                        target = try await documentStore.documentService.getParent(sourceDocId)
                    } catch {
                        workflowLogger.warning(
                            "navigateToSourcePage: couldn't resolve parent for \(sourceDocId): \(error.localizedDescription)"
                        )
                        return
                    }
                }
            } else {
                // No parentId available, use the new endpoint directly
                do {
                    target = try await documentStore.documentService.getParent(sourceDocId)
                } catch {
                    workflowLogger.warning(
                        "navigateToSourcePage: couldn't fetch parent for \(sourceDocId): \(error.localizedDescription)"
                    )
                    return
                }
            }
        } else {
            target = source
        }

        await navigateToResolvedSource(target)
    }

    /// Open the containing folder so `target` shows up in the grid and select
    /// it; if `target` is top-level, just point the sidebar at it. Shared by the
    /// engine-resolved reveal (#3577) and the legacy client-side resolver above.
    @MainActor
    func navigateToResolvedSource(_ target: Document) async {
        if let folderId = target.parentId, !folderId.isEmpty {
            do {
                let folder = try await documentStore.documentService.getDocument(folderId)
                navigateToDocument(folder)
                browserSelection = [target.id]
                detailDocument = target
            } catch {
                navigateToDocument(target)
            }
        } else {
            navigateToDocument(target)
        }
    }

    /// Resolve a source anchor to its parent document + page through the ONE
    /// engine route (#3577) — page-child → parent resolution no longer lives in
    /// the app — then select it. Falls back to the legacy client-side walk if
    /// the engine resolve fails so a reveal never breaks (no regression).
    @MainActor
    func revealResolvedSource(_ request: ClaimSourceNavigationRequest) async {
        do {
            let resolved = try await documentStore.locationService.resolve(request.asLocation)
            let target = try await documentStore.documentService.getDocument(resolved.resolvedDocumentId)
            await navigateToResolvedSource(target)
        } catch {
            workflowLogger.warning(
                "revealResolvedSource: engine resolve failed (\(error.localizedDescription)); falling back to client-side navigateToSourcePage"
            )
            await navigateToSourcePage(request.documentId)
        }
    }

    /// Focus the preview pane on a KG source without changing sidebar or
    /// library-tree selection. Used by KGFocusState for ordinary row/graph
    /// focus; explicit open-source buttons still use navigateToSourcePage.
    @MainActor
    func focusKGSourcePreview(_ sourceDocId: String) async {
        let source: Document
        do {
            source = try await documentStore.documentService.getDocument(sourceDocId)
        } catch {
            workflowLogger.warning("focusKGSourcePreview: couldn't fetch \(sourceDocId): \(error.localizedDescription)")
            return
        }

        let sourceIsPageChild = source.path?.isEmpty ?? true
        if sourceIsPageChild, let parentId = source.parentId, !parentId.isEmpty {
            do {
                detailDocument = try await documentStore.documentService.getDocument(parentId)
            } catch {
                workflowLogger.warning(
                    "focusKGSourcePreview: couldn't fetch parent for \(sourceDocId): \(error.localizedDescription)"
                )
            }
        } else {
            detailDocument = source
        }
    }

    /// Walk up to the current folder's parent. If the current folder is at
    /// the library root (no parent_id), navigate to the library root view
    /// (no selection). Bound to Cmd+` so users can ascend the hierarchy when
    /// the sidebar is hidden. (#786)
    @MainActor
    func navigateToParent() {
        guard let prefixedId = sidebarSelectionState.selectedItemId,
              prefixedId.hasPrefix("doc:") else {
            return
        }
        let docId = String(prefixedId.dropFirst("doc:".count))
        let current = documentStore.currentDocuments.first(where: { $0.id == docId })
            ?? detailDocument
        guard let current else { return }
        if let parentId = current.parentId, !parentId.isEmpty {
            sidebarSelectionState.selectedItemId = "doc:\(parentId)"
        } else {
            sidebarSelectionState.selectedItemId = nil
            detailDocument = nil
            viewMode = .library(nil)
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
        let selectedIds = !preselectedIds.isEmpty
            ? preselectedIds
            : (!browserSelection.isEmpty
                ? Array(browserSelection)
                : (detailDocument.map { [$0.id] } ?? []))
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

    @MainActor
    func runWorkflowOnCollection(
        workflowId: String,
        providerOverride: String? = nil,
        modelOverride: String? = nil
    ) {
        let collectionIds = documentStore.currentDocuments
            .filter { $0.docType == .file }
            .map { $0.id }
        guard !collectionIds.isEmpty else { return }

        let workflowName = workflowStore.workflows.first(where: { $0.id == workflowId })?.name ?? workflowId
        importProgress = "Starting workflow on \(collectionIds.count) documents in collection…"

        executeWorkflowViaSSE(
            workflowId: workflowId,
            workflowName: workflowName,
            docIds: collectionIds,
            providerOverride: providerOverride,
            modelOverride: modelOverride
        )
    }

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

                let threadId = response.threadId
                importProgress = nil
                workflowLogger.info("Started SSE workflow \(workflowId) thread \(threadId) for \(docIds.count) docs")

                streamCompleted = await waitForWorkflowCompletion(
                    threadId: executionThreadId,
                    streamCompleted: streamCompleted
                )
                await finishWorkflowExecution(
                    threadId: executionThreadId,
                    workflowId: workflowId,
                    docIds: docIds,
                    streamCompleted: streamCompleted
                )
            } catch {
                importProgress = nil
                importError = "Workflow failed to start: \(error.localizedDescription)"
                workflowLogger.error("executeWorkflowViaSSE failed: \(error.localizedDescription)")
                executionObserver.endExecution(threadId: executionThreadId, status: .failed)
            }
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
        switch event {
        case .complete, .error, .systemicError:
            return true
        default:
            return false
        }
    }

    private func workflowFinalStatus(forThreadId threadId: String) -> WorkflowStatus {
        guard let exec = executionObserver.activeExecutions[threadId] else {
            return .completed
        }
        return exec.workflowError != nil || exec.status == .failed ? .failed : .completed
    }

    @MainActor
    private func waitForWorkflowCompletion(
        threadId: String,
        streamCompleted: Bool
    ) async -> Bool {
        var completed = streamCompleted
        while !completed {
            try? await Task.sleep(for: .milliseconds(200))
            if Task.isCancelled { break }
            if let exec = executionObserver.activeExecutions[threadId], !exec.isRunning {
                completed = true
            }
        }
        return completed
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
        case .error, .systemicError:
            documentStore.flushPendingFanoutCompletions(status: .failed)
        default:
            break
        }
    }
}
