import Foundation
import OSLog

// MARK: - Processing-status refresh (split from DocumentStore+Helpers for
// file_length, 2026-08-20 — same members, only the file moved)

extension DocumentStore {
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

        if matchCount == 0 {
            Self.logStatusMatchMiss(documentId: documentId, filePath: filePath)
        }
    }

    /// Diagnostic for #767: if the SSE-supplied filePath never matches any
    /// tracked Document.path, the spinner never updates. Log the miss so
    /// future investigations can see whether the issue is "events don't
    /// fire" or "events fire but paths don't match".
    private static func logStatusMatchMiss(documentId: String?, filePath: String) {
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
    /// Resolve a document id against everything loaded — the grid, the
    /// collections, and the sidebar children cache (2026-08-09, the sidebar
    /// multi-scope's lookup). Nil = not loaded anywhere; the caller fetches.
    func resolveDocument(_ documentId: String) -> Document? {
        if let doc = currentDocuments.first(where: { $0.id == documentId }) { return doc }
        if let doc = collections.first(where: { $0.id == documentId }) { return doc }
        for kids in childrenCache.values {
            if let doc = kids.first(where: { $0.id == documentId }) { return doc }
        }
        return nil
    }

    func isDocumentBusy(_ documentId: String) -> Bool {
        // One set-membership test against the dirty-flagged processing index
        // (2026-08-09): the previous linear scans over currentDocuments +
        // collections + every childrenCache array ran per row per render, and
        // the stall sampler attributed 165-188ms main-thread stalls to
        // exactly this function. Same sources, same union semantics — the
        // index is rebuilt once per mutation in DocumentStore.
        processingDocumentIds.contains(documentId)
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
    /// Every document the sidebar knows — roots plus all cached children,
    /// deduplicated by id.
    ///
    /// MEMOIZED (2026-08-09 stall log): rebuilding this union copied every
    /// Document on EVERY access and hit 1747ms on the main thread resolving
    /// one context menu. Keyed on (revision, cache shape) like the
    /// childActivityCounts memo below. ponytail: a same-count in-place child
    /// swap that skips the revision bump serves one stale read — splices and
    /// loads bump revision, so in practice the key always moves; a structure
    /// token on every childrenCache write is the upgrade if that ever bites.
    var sidebarDocuments: [Document] {
        let key = SidebarDocumentsMemoKey(
            revision: revision,
            roots: collections.count,
            parents: childrenCache.count,
            children: childrenCache.reduce(into: 0) { $0 += $1.value.count }
        )
        if let memo = sidebarDocumentsMemo, memo.key == key { return memo.docs }
        var seen = Set<String>()
        let docs = (collections + childrenCache.values.flatMap { $0 })
            .filter { seen.insert($0.id).inserted }
        sidebarDocumentsMemo = (key, docs)
        return docs
    }

    func childActivityCounts(of parentId: String) -> (busy: Int, total: Int) {
        // Memoized per (revision, overrides-token) — this ran O(all documents)
        // per FOLDER ROW per render and stalled the main thread for 231ms in
        // Daniel's 2026-08-09 log. Same sources, same answers; just cached
        // until either input actually changes.
        if childActivityMemoKey != (revision, childActivityMemoToken) {
            childActivityMemo.removeAll(keepingCapacity: true)
            childActivityMemoKey = (revision, childActivityMemoToken)
        }
        if let cached = childActivityMemo[parentId] { return cached }
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

        let counts = (busy: statusById.values.filter { $0 }.count, total: statusById.count)
        childActivityMemo[parentId] = counts
        return counts
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
        guard !ids.isEmpty else { return }
        // ONE batched round-trip (perf audit 2026-08-19) — this was a
        // sequential per-id fetch loop after every workflow completion.
        do {
            for fresh in try await documentService.getDocuments(ids: ids) {
                refreshLocalContent(fresh)
            }
        } catch {
            if error.isCancellationError { return }   // superseded — not a failure
            let logger = Logger(subsystem: "app.fichero.fichero", category: "DocumentStore")
            logger.warning(
                "refreshDocumentsByIds: failed to refresh \(ids.count) id(s): \(error.localizedDescription, privacy: .public)"
            )
        }
    }
}
