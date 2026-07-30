import FicheroAPIClient
import Foundation
import OSLog

// MARK: - Helpers

extension DocumentStore {

    /// Update a document in all local caches.
    ///
    /// Handles the cross-folder move case: if the document's `parentId`
    /// no longer matches the currently-viewed `selectedCollection`, it
    /// must be REMOVED from `currentDocuments` — not just replaced in
    /// place — or the grid keeps showing a document that now lives
    /// somewhere else. Same logic for `childrenCache` buckets: the
    /// document only belongs in the bucket whose key equals its new
    /// `parentId`.
    func updateLocal(_ document: Document) {
        // Update in collections.
        if let index = collections.firstIndex(where: { $0.id == document.id }) {
            collections[index] = document
        }

        // Sync currentDocuments with the new parentId:
        //   - if it now belongs to the viewed folder, replace in place;
        //   - if not, remove it so the grid no longer shows it.
        let viewedFolderId = selectedCollection?.id
        if document.parentId == viewedFolderId {
            if let index = currentDocuments.firstIndex(where: { $0.id == document.id }) {
                currentDocuments[index] = document
            }
        } else {
            currentDocuments.removeAll { $0.id == document.id }
        }

        // Update / re-bucket the childrenCache. Remove from every bucket
        // that isn't the document's current parent; insert-or-replace in
        // the bucket that is.
        for parentId in childrenCache.keys {
            if parentId == document.parentId {
                if let index = childrenCache[parentId]?.firstIndex(where: { $0.id == document.id }) {
                    childrenCache[parentId]?[index] = document
                } else {
                    childrenCache[parentId]?.append(document)
                }
            } else {
                childrenCache[parentId]?.removeAll { $0.id == document.id }
            }
        }

        // Update selection if needed.
        if selectedCollection?.id == document.id {
            selectedCollection = document
        }
        if selectedDocument?.id == document.id {
            selectedDocument = document
        }
    }

    /// Replace a document in all caches without folder-membership checks.
    ///
    /// Use this for content-only updates (page_content, metadata) where the
    /// document's location hasn't changed. Unlike updateLocal(), this never
    /// removes the document from currentDocuments based on parentId — that
    /// removal logic exists only for cross-folder move operations.
    func refreshLocalContent(_ document: Document) {
        if let index = collections.firstIndex(where: { $0.id == document.id }) {
            collections[index] = document
        }
        if let index = currentDocuments.firstIndex(where: { $0.id == document.id }) {
            currentDocuments[index] = document
        }
        for parentId in childrenCache.keys {
            if let index = childrenCache[parentId]?.firstIndex(where: { $0.id == document.id }) {
                childrenCache[parentId]?[index] = document
            }
        }
        if selectedDocument?.id == document.id {
            selectedDocument = document
        }
        if selectedCollection?.id == document.id {
            selectedCollection = document
        }
    }

    /// Persist a document's `page_content` via a STORE-OWNED task that runs to
    /// completion regardless of view lifecycle.
    ///
    /// The Content-tab editor lives in a SwiftUI view (`ArtifactPanel`) whose
    /// debounced and on-blur saves run inside view-owned `Task`s. When that view
    /// re-renders, loses focus, or the document selection changes, SwiftUI
    /// cancels those tasks — and because the `updateDocument` PUT used to run
    /// *inside* them, the in-flight request was cancelled mid-flight
    /// (NSURLError -999, #2466; same family as the old page-content bug #175).
    ///
    /// By owning the `Task` here and awaiting its `.value` — which does NOT
    /// forward the caller's cancellation to an unstructured child task — a view
    /// re-render/blur can no longer abort the save. Saves for the same document
    /// are serialized so the most-recent edit lands last and concurrent PUTs
    /// never interleave. A genuine save failure is still surfaced (returned as a
    /// user-facing string); only the spurious cancellation is eliminated.
    ///
    /// - Parameters:
    ///   - documentId: The document whose `page_content` is being saved.
    ///   - save: The actual persistence work (the OpenAPI `updateDocument` PUT),
    ///           returning the updated `Document`. Injectable for testing.
    /// - Returns: `nil` on success, or a user-facing error string on failure.
    @discardableResult
    func savePageContent(
        documentId: String,
        perform save: @escaping @Sendable () async throws -> Document
    ) async -> String? {
        // Capture any earlier save of this document so we can wait for it first.
        let previous = pageContentSaveTasks[documentId]
        let task = Task { @MainActor [weak self] () -> String? in
            // Let the prior save of this document finish before issuing ours so
            // the last edit wins. We deliberately ignore its outcome and any
            // cancellation of it.
            _ = await previous?.value
            // Mark this as our own write BEFORE the PUT so the change-stream
            // echo — which the backend emits the moment it processes the PUT,
            // and which can race ahead of this task returning — is recognised
            // and dropped (#2478). Recorded even on failure; a stale marker just
            // expires via `ownWriteEchoWindow`.
            self?.markOwnWrite(documentId)
            do {
                let updated = try await save()
                self?.refreshLocalContent(updated)
                return nil
            } catch {
                return error.localizedDescription
            }
        }
        pageContentSaveTasks[documentId] = task
        let result = await task.value
        // Only clear if a newer save hasn't already replaced us.
        if pageContentSaveTasks[documentId] == task {
            pageContentSaveTasks[documentId] = nil
        }
        return result
    }

    // MARK: - Self-echo suppression (#2478 / #2479)

    /// Record that this device just wrote `documentId`, so the change-stream
    /// echo of that write can be dropped instead of triggering a redundant
    /// re-fetch + re-splice (which resets the page editor — #2478).
    func markOwnWrite(_ documentId: String) {
        recentOwnWrites[documentId] = Date()
    }

    /// Returns true (and consumes the marker) if `documentId` is the echo of a
    /// write this device just made. A genuine update from another device has no
    /// fresh marker and returns false, so it still applies in place (#2479).
    /// Expired markers are treated as not-ours and pruned.
    func consumeOwnWriteEcho(_ documentId: String) -> Bool {
        guard let writtenAt = recentOwnWrites[documentId] else { return false }
        recentOwnWrites[documentId] = nil
        return Date().timeIntervalSince(writtenAt) <= ownWriteEchoWindow
    }

    // MARK: - Active page-edit flush (#2476)

    /// Register the focused page-content editor's flush so an external
    /// navigation can persist its in-flight edit before the document changes.
    func registerActivePageEdit(_ flush: @escaping @MainActor () async -> Void) {
        activePageEditFlush = flush
    }

    /// Clear the registered flush (editor blurred away / disappeared).
    func unregisterActivePageEdit() {
        activePageEditFlush = nil
    }

    /// Persist the focused page-content editor's in-flight edit, if any. Call
    /// this BEFORE switching the focused document (image prev/next) or the
    /// inspector tab so the edit isn't lost when the editor reseeds (#2476).
    func flushActivePageEdit() async {
        await activePageEditFlush?()
    }

    /// Clear all cached data.
    func clearCache() {
        childrenCache.removeAll()
    }

    // MARK: - Processing Status Updates

    /// Update the processing status of a document by its stable identity when
    /// available, falling back to the shared file path for older events.
    /// This is used during workflow execution to show visual feedback.
    /// The status is in-memory only and reverts on app restart.
    func updateProcessingStatus(for identity: FileProgressIdentity, status: Status) {
        // Track live processing identities so a terminal boundary can clear
        // residual spinners for documents whose completion event never
        // arrived (stopped run / dead SSE stream, #4346).
        if status == .processing {
            activeProcessingIdentities[identity.stableId] = identity
        } else {
            activeProcessingIdentities.removeValue(forKey: identity.stableId)
        }
        let filePath = identity.filePath
        let documentId = identity.leafDocumentId
        var matchCount = 0
        var matchedDocId: String?

        func matches(_ document: Document) -> Bool {
            if let documentId {
                return document.id == documentId
            }
            return document.path == filePath
        }

        // Update in collections
        if let index = collections.firstIndex(where: matches) {
            collections[index].status = status
            matchedDocId = collections[index].id
            matchCount += 1
        }

        // Update in current documents
        if let index = currentDocuments.firstIndex(where: matches) {
            currentDocuments[index].status = status
            matchedDocId = currentDocuments[index].id
            matchCount += 1
        }

        // Update in cache
        for (parentId, children) in childrenCache {
            if let index = children.firstIndex(where: matches) {
                childrenCache[parentId]?[index].status = status
                matchedDocId = children[index].id
                matchCount += 1
            }
        }

        // Update selection if needed
        if let selected = selectedDocument, matches(selected) {
            selectedDocument?.status = status
            matchedDocId = selected.id
            matchCount += 1
        }

        // Persist to overlay so the status survives currentDocuments / cache
        // reloads on navigation (#791). Pending = clear (don't shadow live
        // backend state); processing/completed/failed = remember.
        // Key the override on the RUN'S TARGET id even when no loaded container
        // holds that document (#4295/#4346): a run targets a document, and
        // whether the sidebar/grid happens to have hydrated it yet says nothing
        // about whether work is under way. Falling back to `documentId` is what
        // makes a page row's spinner correct before its children load.
        if let id = matchedDocId ?? documentId {
            if status == .pending {
                workflowStatusOverrides.removeValue(forKey: id)
            } else {
                workflowStatusOverrides[id] = status
            }
        }

        // Diagnostic for #767: if the SSE-supplied filePath never matches any
        // tracked Document.path, the spinner never updates. Log the miss so
        // future investigations can see whether the issue is "events don't
        // fire" or "events fire but paths don't match".
        if matchCount == 0 {
            let logger = Logger(subsystem: "app.fichero.fichero", category: "DocumentStore")
            if let documentId {
                logger.warning(
                    "updateProcessingStatus: no document matched id '\(documentId, privacy: .public)' path '\(filePath, privacy: .public)'"
                )
            } else {
                logger.warning(
                    "updateProcessingStatus: no document matched path '\(filePath, privacy: .public)' — spinner won't update (#767)"
                )
            }
        }
    }

    /// Compatibility wrapper for legacy path-only callers.
    func updateProcessingStatus(forPath filePath: String, status: Status) {
        updateProcessingStatus(
            for: FileProgressIdentity(
                filePath: filePath,
                documentId: nil,
                pageId: nil,
                displayName: nil,
                sequence: nil
            ),
            status: status
        )
    }

    /// Record that the per-file fanout slot for this identity has finished —
    /// but DO NOT flip the document's status to `.completed` yet. Reduce-phase
    /// nodes (extract_all, folder_cleanup) keep touching pages after the
    /// fanout's `fileComplete` event fires. The status stays `.processing`
    /// until the workflow's `complete` event fires and
    /// `flushPendingFanoutCompletions` promotes everything. (#948)
    func recordFanoutComplete(for identity: FileProgressIdentity) {
        pendingFanoutCompletions[identity.stableId] = identity
    }

    /// Compatibility wrapper for legacy path-only callers.
    func recordFanoutComplete(forPath filePath: String) {
        recordFanoutComplete(
            for: FileProgressIdentity(
                filePath: filePath,
                documentId: nil,
                pageId: nil,
                displayName: nil,
                sequence: nil
            )
        )
    }

    /// Promote every path recorded via `recordFanoutComplete` to `.completed`.
    /// Called by workflow-runner sites when the workflow's terminal event
    /// (`complete` / `error` / `systemicError`) arrives. (#948)
    func flushPendingFanoutCompletions(status: Status = .completed) {
        let completions = pendingFanoutCompletions.values
        pendingFanoutCompletions.removeAll()
        for identity in completions {
            updateProcessingStatus(for: identity, status: status)
        }
    }

    /// Clear every document still marked `.processing` by a live stream.
    ///
    /// Run-terminal boundaries call this AFTER `flushPendingFanoutCompletions`
    /// so documents whose `fileComplete`/`fileError` never arrived — a
    /// stopped run, or an SSE stream that died without a terminal frame
    /// (#4346/#4349) — revert to `.pending` instead of spinning forever.
    /// Callers must skip this while ANOTHER run is still active (the
    /// identities are not partitioned per thread); a concurrent run's next
    /// `fileStart` re-marks its documents anyway.
    func clearResidualProcessing(status: Status = .pending) {
        let residuals = activeProcessingIdentities.values
        activeProcessingIdentities.removeAll()
        for identity in residuals {
            updateProcessingStatus(for: identity, status: status)
        }
    }

    /// A row is busy because a RUNNING execution targets it (#4295) — never
    /// because of what is selected. The old row derivation only consulted
    /// `currentDocuments` (the SELECTED collection's children) and roots, so a
    /// page row's spinner appeared while its parent was selected and vanished
    /// on deselect. This checks the run's own target record
    /// (`workflowStatusOverrides` — written per target id by
    /// `updateProcessingStatus`, independent of any container) plus every
    /// live container including `childrenCache`, where sidebar child rows
    /// actually live.
    func isDocumentBusy(_ documentId: String) -> Bool {
        if workflowStatusOverrides[documentId] == .processing { return true }
        if currentDocuments.first(where: { $0.id == documentId })?.status == .processing { return true }
        if collections.first(where: { $0.id == documentId })?.status == .processing { return true }
        for kids in childrenCache.values
        where kids.contains(where: { $0.id == documentId && $0.status == .processing }) {
            return true
        }
        return false
    }

    /// Aggregate busy state for a folder row (#4295): any direct child busy —
    /// by live status in the grid or the sidebar cache, or by being a running
    /// execution's target (override) even when its container copy is stale.
    func folderHasBusyChild(_ folderId: String) -> Bool {
        childActivityCounts(of: folderId).busy > 0
    }

    /// How many direct children are busy, and how many there are (#4417).
    ///
    /// The counting half of `folderHasBusyChild`, which threw the numbers away
    /// and returned a Bool — so the parent could only borrow the child's
    /// spinner instead of summarising them. Same sources, same staleness
    /// tolerance; it just keeps what it counted.
    ///
    /// Children are unioned by id across the grid and the sidebar cache: the
    /// same child can appear in both, and counting it twice would report more
    /// work in flight than exists.
    func childActivityCounts(of parentId: String) -> (busy: Int, total: Int) {
        var statusById: [String: Bool] = [:]

        for doc in currentDocuments where doc.parentId == parentId {
            statusById[doc.id] = doc.status == .processing
                || workflowStatusOverrides[doc.id] == .processing
        }
        for kid in childrenCache[parentId] ?? [] {
            let busy = kid.status == .processing || workflowStatusOverrides[kid.id] == .processing
            // A cached copy can be staler than the grid's; either saying busy
            // is enough, which matches the tolerance #4295 established.
            statusById[kid.id] = (statusById[kid.id] ?? false) || busy
        }

        return (busy: statusById.values.filter { $0 }.count, total: statusById.count)
    }

    /// Apply workflowStatusOverrides to a freshly-loaded array so the UI sees
    /// the in-flight / failed state survive reloads. Called by every load
    /// path that populates currentDocuments / collections / childrenCache.
    /// (#791)
    func applyStatusOverrides(_ docs: [Document]) -> [Document] {
        guard !workflowStatusOverrides.isEmpty else { return docs }
        return docs.map { doc in
            if let override = workflowStatusOverrides[doc.id] {
                var copy = doc
                copy.status = override
                return copy
            }
            return doc
        }
    }

    /// Re-fetch the given documents by ID from the backend and merge each fresh
    /// record into the in-memory caches via `refreshLocalContent`. Called after a
    /// workflow completes so backend-written content (e.g. a Transcribe
    /// transcript) replaces the stale in-memory `pageContent` without forcing a
    /// full folder reload. (#1445)
    func refreshDocumentsByIds(_ ids: [String]) async {
        for id in ids {
            do {
                let fresh = try await documentService.getDocument(id)
                refreshLocalContent(fresh)
            } catch {
                if error.isCancellationError { return }   // superseded — not a failure
                let logger = Logger(subsystem: "app.fichero.fichero", category: "DocumentStore")
                logger.warning(
                    "refreshDocumentsByIds: failed to refresh \(id, privacy: .public): \(error.localizedDescription, privacy: .public)"
                )
            }
        }
    }
}
