import OSLog
import SwiftUI

extension ContentView {

    /// Handles `.onChange(of: browserSelection)`.
    /// Persists browser selection to @SceneStorage.
    /// What a selected browse row asks of the shell, decided from its OWN id (#4850): classified
    /// BEFORE the ambient "which collection is showing" flag, because a composite outline id
    /// ("<doc>:entity:<id>") must never reach code built for a bare id.
    enum BrowserRowAction: Equatable {
        /// An entity row: focus this BARE entity id (nil for the group row, which focuses nothing).
        case focusEntity(String?)
        /// A page row: promote this page's own (bare) document id.
        case promotePage(String?)
        /// Claim, artifact and note rows: handled elsewhere; do nothing here.
        case ignore
        /// A document row or an unrecognised id: fall through to the document path.
        case notClassified
    }

    static func browserRowAction(forNodeId nodeId: String) -> BrowserRowAction {
        let parsed = LibraryOutlineNode.parse(nodeId: nodeId)
        switch parsed.childType {
        case .entities: return .focusEntity(parsed.itemId)
        case .pages: return .promotePage(parsed.itemId)
        case .claims, .artifacts, .notes: return .ignore
        case nil: return .notClassified
        }
    }

    func handleBrowserSelectionChange(_ newSelection: Set<String>) {
        // #4834: a real browser/table selection always outranks a
        // knowledge-surface reveal.
        sourceRevealDocument = nil
        // Persist browser selection to @SceneStorage
        if let encoded = try? JSONEncoder().encode(newSelection) {
            browserSelectionData = encoded
        }
        rememberRunSelection(newSelection)
        let primaryId = shellPrimarySelectionId(
            in: newSelection, orderedBy: selectedDocuments
        )
        // #4850: classify the row FIRST, from its OWN id — not from the
        // ambient "which collection is the sidebar showing" flag below,
        // which says nothing about what THIS particular selected row is and
        // let an entity/claim row's COMPOSITE outline id
        // ("<doc>:entity:<id>"/"<doc>:claim:<id>") leak into code built for
        // a bare id. Also fixes a case the old ambient flag never covered:
        // an entity/claim row disclosed under a document while browsing
        // the DOCUMENTS collection (not the Entities/Claims collection)
        // used to fall straight into the document-promotion path below
        // with a composite id.
        if let primaryId {
            switch Self.browserRowAction(forNodeId: primaryId) {
            case .focusEntity(let entityId):
                // The table's own `.onChange` (`EntitiesTableView.swift:169-181`
                // → `openEntityFromLibrary`, `LibraryView+Selection.swift:321`)
                // already focuses this row with the bare `entity.id` — this
                // is now the SAME value, not a second writer: whichever of
                // the two fires last writes the identical id, so the stale-
                // composite race is gone. The table is the PRIMARY writer;
                // this branch exists so any future entity surface that is
                // not the table still resolves correctly.
                if let entityId { kgFocusState.focusEntity(entityId: entityId) }
                NavTrace.log("selChange.entityFocus", "nil")
                detailDocument = nil
                return
            case .promotePage(let pageId):
                // #4862: a page row promotes ITS OWN page (a real Document nested under its
                // parent PDF only for disclosure). `LibraryView+TableView.swift`'s own
                // `.onChange(of: selection)` resolves this via its live outline; this branch is the
                // same safety net for any OTHER browse mode reaching here with the composite id.
                if let pageId {
                    Task { @MainActor in
                        if let page = try? await documentStore.documentService.getDocument(pageId) {
                            detailDocument = page
                        }
                    }
                }
                return
            case .ignore:
                // Claim, artifact and note rows have a correct, richer handler of their own (the
                // claims table's `onOpenSource`, the Table view's artifact focus). Their composite
                // ids must never reach the generic document-promotion path below, and nothing
                // beyond that is invented here (#4850, #4862).
                return
            case .notClassified:
                break
            }
        }
        if isEntityLibrarySelection {
            guard let firstId = primaryId else {
                kgFocusState.clear()
                detailDocument = nil
                return
            }
            kgFocusState.focusEntity(entityId: firstId)
            // #4850: this branch FOCUSES an entity — the old label
            // "selChange.entityClear" described the opposite of what runs here.
            NavTrace.log("selChange.entityFocus", "nil")
            detailDocument = nil
            return
        }
        if kgFocusState.focusedEntityId != nil {
            kgFocusState.clear()
        }
        guard let firstId = primaryId,
              BrowserSelectionPreviewPolicy.shouldPromoteSelectionToDetail(
                layoutMode: currentLayoutMode,
                selectedDocumentId: firstId,
                currentDetailDocumentId: detailDocument?.id
              ) else {
            if newSelection.isEmpty {
                NavTrace.log("selChange.emptyClear", "nil")
                detailDocument = nil
            }
            return
        }
        if let doc = selectedDocuments.first(where: { $0.id == firstId }) {
            NavTrace.log("selChange.promote", "\(firstId) (rewrite; had \(detailDocument?.id ?? "nil"))")
            detailDocument = doc
            return
        }
        // Selection promotion must not silently fall through when the selected
        // row isn't in currentDocuments yet (restore-before-load, columns-mode
        // child columns, tree-rebuild reload in flight — #4297's family). The
        // sidebar path already fetches; mirror it here so a selected image
        // always reaches the preview pane instead of an empty state (#4299).
        Task { @MainActor in
            let fetched = try? await documentStore.documentService.getDocument(firstId)
            if let fetched,
               shellPrimarySelectionId(
                   in: browserSelection, orderedBy: selectedDocuments
               ) == firstId {
                NavTrace.log("selChange.asyncFetch", "\(firstId)")
                detailDocument = fetched
            }
        }
    }

    /// Handles `.onChange(of: detailDocument)`.
    /// Keeps documentStore.selectedDocument in sync and records navigation.
    func handleDetailDocumentChange(from oldDoc: Document?, to newDoc: Document?) {
        // Keep documentStore.selectedDocument in sync so WorkflowEditor
        // toolbar button sees the current document at run time.
        documentStore.selectedDocument = newDoc
        // Clear page focus so the inspector starts fresh on a DIFFERENT
        // document — never on a refresh of the same one (#1463, corrected
        // 2026-08-09): this cleared UNCONDITIONALLY, so any background
        // refresh that merely replaced the detailDocument snapshot (a status
        // poll, a change-stream splice) dropped the reader to page 1 with no
        // user action ('snaps back to page 1', #4558). Same id = same
        // document; the reader keeps its place.
        if oldDoc?.id != newDoc?.id {
            // While a library search is active, the reader must show the
            // ACTUAL SOURCE page the hit matched — not the parent paginated to
            // page 1 (Daniel, 2026-09-07: "reader should show the actual
            // source, not page 1, page 2, etc."). So make the hit's page the
            // authoritative page cursor, and keep that cursor when detail later
            // RE-ROOTS onto the hit's parent container (page-child → its folder
            // / PDF): clearing it there is exactly what dropped the reader back
            // to the container's first page. Outside search, behavior is
            // unchanged — clear on a real document change (#1463/#4558).
            if activeSearchQuery != nil, let newDoc {
                if newDoc.docType == .page {
                    pageFocusDocument = newDoc
                } else if let focus = pageFocusDocument,
                          focus.parentId == newDoc.id
                            || pdfParentDocumentId(of: focus) == newDoc.id {
                    // Re-root to the hit's parent: keep the source-page cursor.
                } else {
                    pageFocusDocument = nil
                }
            } else {
                pageFocusDocument = nil
            }
        }
        guard !isRestoringNavigationHistory else { return }
        recordNavigationEntry()
        postSearchPassageAnchor(for: newDoc)
    }

    /// Pure: a search result's hits on one page, as PAGE-relative spans
    /// (#5466). Each excerpt's anchor names its page and its matched range;
    /// excerpts anchored to another page are not this page's hits.
    static func searchHitSpans(of result: SearchResult, onPage pageId: String) -> [ReaderHitSpan] {
        result.transcriptExcerpts
            .filter { $0.anchor.documentId == pageId }
            .map { ReaderHitSpan(start: Int($0.anchor.charStart), end: Int($0.anchor.charEnd)) }
    }

    /// While search results show, selecting a hit LIGHTS the matched passage
    /// (Daniel, 2026-09-02: the row/reader/preview should show "why on each
    /// page"). The hit's excerpt anchor — which the engine now places at the
    /// matched PASSAGE, not char 0 — rides the same `.readerTextSelection`
    /// seam the reader's own selection uses, so the preview's word boxes
    /// light the passage and the reader's source highlight follows, with
    /// zero new plumbing.
    func postSearchPassageAnchor(for doc: Document?) {
        guard activeSearchQuery != nil, let doc,
              let result = transientSearchStore?.results
                  .first(where: { $0.documentId == doc.id }),
              let excerpt = result.transcriptExcerpts.first else {
            // No hit to light (search ended, or this selection is not a
            // resolvable result) — clear the transcript's search mark.
            NavTrace.log(
                "searchAnchor.clear",
                "doc=\(doc?.id ?? "nil") search=\(activeSearchQuery != nil) "
                    + "hasResult=\(transientSearchStore?.results.contains(where: { $0.documentId == doc?.id }) ?? false)"
            )
            ReaderSearchMatchState.shared.clear()
            return
        }
        let anchor = ReaderPassageAnchor(
            documentId: excerpt.anchor.documentId,
            text: excerpt.text,
            charStart: Int(excerpt.anchor.charStart),
            charEnd: Int(excerpt.anchor.charEnd)
        )
        // Light the RELEVANT passage in the transcript from the backend anchor
        // (page id + PAGE-relative char range), not by re-scanning the query as
        // a substring (Daniel, 2026-09-07: "highlight … by the html backend,
        // not the swiftui interface with a filter"). The coordinator reads this
        // in syncSelection and runs DocumentKGPaneRoute.pageHitsScript.
        // EVERY hit the engine found on that page is lit, the first current
        // (#5466) — not the first alone.
        let spans = Self.searchHitSpans(of: result, onPage: anchor.documentId)
        ReaderSearchMatchState.shared.set(pageId: anchor.documentId, spans: spans, current: 0)
        NavTrace.log(
            "searchAnchor.set",
            "page=\(anchor.documentId) hits=\(spans.count) start=\(anchor.charStart ?? -1) end=\(anchor.charEnd ?? -1)"
        )
        // LATCH, then post (Daniel, 2026-09-03). This fires from the
        // `detailDocument` change, so the reader for that document is
        // frequently built in the same turn — after this post. A notification
        // reaches only the surfaces that already exist; the latch is what a
        // reader mounting one frame later reads on appear. The post stays for
        // the surfaces already up (the preview's word boxes, the annotation
        // bar) — one anchor, two ways of arriving, no second source of truth.
        ReaderPassageFocus.record(anchor)
        NotificationCenter.default.post(
            name: .readerTextSelection,
            object: nil,
            userInfo: [
                "documentId": anchor.documentId,
                "text": anchor.text,
                // Non-nil by construction here; unwrapped rather than bridged
                // through `as Any`, which would put an Optional in the
                // userInfo for every reader to fail to cast.
                "charStart": anchor.charStart ?? 0,
                "charEnd": anchor.charEnd ?? 0,
                // "Land here", not "here is a selection" — the reader is a
                // publisher on this seam too, and must not answer itself.
                ReaderPassageAnchor.kindKey: ReaderPassageAnchor.searchPassageKind
            ]
        )
    }
}
