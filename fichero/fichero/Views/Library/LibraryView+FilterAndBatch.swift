import FicheroAPIClient
import SwiftUI

// MARK: - Filter, Collection State, and Empty State Extension

/// What the library content area shows when it holds no rows (#4235).
///
/// "This folder is empty" and "its contents have not arrived yet" are different
/// answers that used to render identically, which is why every folder click and
/// every drop flashed "No Documents" and then relaid out when the data landed.
enum LibraryEmptyPlaceholder: Equatable {
    /// A real, final answer: there is nothing here.
    case empty
    /// A children fetch is in flight for the selected folder.
    case loadingContents
    /// A drop registered and the import is being staged — often before the
    /// engine has a task to report progress for at all.
    case importing
}

extension LibraryView {

    // MARK: - Filter Bar Visibility

    /// React to the inline filter bar being revealed or dismissed.
    ///
    /// The bar can now be toggled from the shell toolbar (#4289) as well as from
    /// ⌘F, Escape, and "Clear Filter". Centralising the two rules here means
    /// every route obeys them:
    ///
    /// - Revealing puts the caret in the field, so the bar is immediately usable
    ///   (what ⌘F always did).
    /// - Dismissing clears the query, so rows are never left silently filtered
    ///   out with no visible field to explain why — the stuck-filter trap the
    ///   Escape and Clear Filter buttons already guard against.
    func filterBarVisibilityChanged(_ isShown: Bool) {
        if isShown {
            filterFieldFocused = true
        } else if !searchText.isEmpty {
            searchText = ""
        }
    }

    // MARK: - Filtered Documents

    // ponytail: recompute inputs — documents, entities, searchText, sortOrder, sortFieldRaw, sortAscending, folderId
    // filteredDocuments and filteredEntities are @State vars on LibraryView; recomputeFiltered()
    // is called from .onAppear and .onChange of every input so filter/sort never runs in body.
    //
    // `rebuildIndex` (#3865): the per-doc lowercased search keys only change when
    // the DOCUMENT SET changes, not when the query does. The debounced ⌘F
    // keystroke path passes `false` so typing filters against the cached keys
    // instead of re-lowercasing every doc's OCR text per keystroke; every other
    // caller (documents/entities/folder/sort changes) rebuilds with the default.
    func recomputeFiltered(rebuildIndex: Bool = true) {
        // The per-doc search keys are only read when filtering (searchText
        // non-empty, below). Skip the O(n) rebuild — name + a 4KB OCR excerpt,
        // lowercased per doc — on the empty-filter path, which is exactly what
        // runs at launch and on every live `revision` tick (#3195). The keys are
        // built lazily the first time a query actually needs them.
        if rebuildIndex && !searchText.isEmpty { rebuildDocumentSearchKeys() }

        // Documents — match against the precomputed lowercased key (name + a
        // bounded OCR excerpt + status), not a fresh full-pageContent scan (#3865).
        var docs = documents
        if !searchText.isEmpty {
            // Lazy build (#3195): if the doc set changed while the filter was
            // empty the cache is stale/empty — rebuild once here, not per
            // keystroke (preserving the #3865 cached-key guarantee for typing).
            if documentSearchKeys.count != documents.count { rebuildDocumentSearchKeys() }
            let query = searchText.localizedLowercase
            docs = docs.filter { doc in
                (documentSearchKeys[doc.id] ?? Self.documentSearchKey(for: doc)).contains(query)
            }
        }
        // NOT `docs.sorted(using: sortOrder)` (#3322). For `document_date` the
        // engine already ordered these rows, and re-sorting them here would
        // discard the precision tie-breaking and the undated fallback while
        // still producing a plausible-looking list. `orderedForDisplay` is the
        // one place that decides whether the client sorts at all.
        filteredDocuments = LibrarySortField.orderedForDisplay(
            docs,
            field: LibrarySortField(rawValue: sortFieldRaw) ?? .name,
            using: sortOrder
        )
        // Hash the ids (Int) instead of joining every id into one giant String
        // (#3870) — it only needs to CHANGE when the visible set changes.
        var hasher = Hasher()
        for doc in filteredDocuments { hasher.combine(doc.id) }
        thumbnailPrefetchKey = hasher.finalize()
        // id → index for O(1) prefetch scheduling (#3870); ids are unique, keep the
        // first on the off chance of a dup rather than trapping.
        documentIndexById = Dictionary(
            filteredDocuments.enumerated().map { ($1.id, $0) },
            uniquingKeysWith: { first, _ in first }
        )

        // Entities — strip OCR/extraction garbage names, then decorate each with
        // its lowercased sort key ONCE (#3865). The old comparator re-computed
        // `canonicalName.localizedLowercase` for both sides on every comparison —
        // O(n log n) allocations; now each key is built a single time.
        var rows = entities
            .filter { !OntologyBrowser.isOcrGarbage($0.canonicalName) }
            .map { entity in
                (
                    entity: entity,
                    nameKey: entity.canonicalName.localizedLowercase,
                    corroboration: entity.corroborationCount ?? 0,
                    selectionId: entitySelectionId(for: entity)
                )
            }
        if !searchText.isEmpty {
            let query = searchText.localizedLowercase
            rows = rows.filter { row in
                row.nameKey.contains(query)
                    || row.entity.entityType?.rawValue.localizedLowercase.contains(query) == true
                    || (row.entity.aliases ?? []).contains { $0.localizedLowercase.contains(query) }
            }
        }
        filteredEntities = rows.sorted { lhs, rhs in
            if lhs.nameKey != rhs.nameKey {
                return lhs.nameKey < rhs.nameKey
            }
            if lhs.corroboration != rhs.corroboration {
                return lhs.corroboration > rhs.corroboration
            }
            return lhs.selectionId < rhs.selectionId
        }.map { $0.entity }
    }

    /// Max OCR characters folded into a document's search key (#3865). ⌘F is a
    /// quick find-in-list, not full-text search — bounding the excerpt keeps the
    /// key cheap to build without scanning multi-MB OCR blobs. A match deeper
    /// than this in a long document won't surface here (use real search for that).
    static let searchExcerptLimit = 4000

    /// Lowercased `name + OCR excerpt + status` used by the ⌘F filter (#3865).
    /// Static + pure so it's unit-testable and reused as the lazy fallback when
    /// the cached index is missing a doc.
    static func documentSearchKey(for doc: Document) -> String {
        let excerpt = doc.pageContent.map { $0.prefix(searchExcerptLimit) } ?? ""
        return "\(doc.name) \(excerpt) \(doc.status.rawValue)".localizedLowercase
    }

    /// Rebuild the per-document search-key cache. Runs only when the document set
    /// changes (not per keystroke), so keystroke filtering stays a cheap
    /// dictionary lookup + `contains` (#3865).
    func rebuildDocumentSearchKeys() {
        var keys: [String: String] = [:]
        keys.reserveCapacity(documents.count)
        for doc in documents {
            keys[doc.id] = Self.documentSearchKey(for: doc)
        }
        documentSearchKeys = keys
    }

    var isShowingEntitiesCollection: Bool {
        contentCollection == .entities
    }

    var entityCollectionTaskKey: String {
        guard isShowingEntitiesCollection else { return "documents" }
        return "entities:\(windowState.libraryId.uuidString)"
    }

    var isCollectionLoading: Bool {
        isShowingEntitiesCollection ? isLoadingEntities : isLoading
    }

    var activeErrorMessage: String? {
        isShowingEntitiesCollection ? entityLoadErrorMessage : errorMessage
    }

    var isCollectionEmpty: Bool {
        isShowingEntitiesCollection ? filteredEntities.isEmpty : filteredDocuments.isEmpty
    }

    // MARK: - Filter Bar

    /// Xcode-navigator-style filter bar pinned to the BOTTOM of the library
    /// list pane (mounted via `.safeAreaInset(edge: .bottom)` in `LibraryView`).
    /// Thin, subtle `.bar` material with a top divider; binds `searchText`,
    /// which drives `filteredDocuments`, so it quick-narrows the visible rows
    /// client-side. The toolbar filter toggle / ⌘F controls visibility;
    /// Escape hides the bar (and clears the filter so no rows stay hidden).
    var filterBarView: some View {
        VStack(spacing: 0) {
            Divider()

            // Translucent Liquid Glass background, matching the sidebar mini-toolbars
            // and the library action bar for a consistent glass look (#2550).
            GlassEffectContainer {
                HStack(spacing: 6) {
                    Image(systemName: "line.3.horizontal.decrease.circle")
                        .foregroundStyle(.secondary)
                        .font(.body)
                        .imageScale(.small)

                    TextField("Filter", text: $searchText)
                        .textFieldStyle(.plain)
                        .font(.callout)
                        .focused($filterFieldFocused)

                    if !searchText.isEmpty {
                        Button {
                            searchText = ""
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundStyle(.secondary)
                        }
                        .buttonStyle(.plain)
                        .help("Clear filter")
                        .accessibilityLabel("Clear Filter")
                    }
                }
                .padding(.horizontal, 10)
                .frame(height: 30)
                .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 8))
            }
        }
        // Escape hides the bottom filter bar and clears the filter so no rows
        // are left silently hidden once the bar disappears.
        .background(
            Button("") {
                searchText = ""
                showFilterBar = false
            }
            .buttonStyle(.plain)
            .keyboardShortcut(.escape, modifiers: [])
            .hidden()
        )
    }

    // MARK: - Empty State

    /// What the content area shows when it currently has no rows (#4235).
    ///
    /// "No Documents" and "the contents haven't arrived yet" looked identical,
    /// so every folder click and every drop showed the empty state first and
    /// then relaid out when the data landed — the dead interval the issue is
    /// about. These are different states and must look different.
    var emptyCollectionPlaceholder: LibraryEmptyPlaceholder {
        Self.emptyCollectionPlaceholder(
            isFetchingContents: !isShowingEntitiesCollection && documentStore.isLoadingChildren,
            isPreparingImport: !isShowingEntitiesCollection
                && libraryManager.importingLibrary?.id == windowState.libraryId,
            hasFilterText: !searchText.isEmpty
        )
    }

    /// Pure so the precedence is testable without a rendered view or a live
    /// engine — the same reason `LibraryView.isAwaitingFirstLoad` is pure.
    /// `nonisolated` is LOAD-BEARING: a static on a `View` inherits the type's
    /// MainActor isolation under the macOS 26 SDK, and Swift Testing calls it
    /// off-main (#4201).
    nonisolated static func emptyCollectionPlaceholder(
        isFetchingContents: Bool,
        isPreparingImport: Bool,
        hasFilterText: Bool
    ) -> LibraryEmptyPlaceholder {
        // A filter that matches nothing is a real, final answer about rows the
        // app already has — never hide it behind a spinner.
        if hasFilterText { return .empty }
        // The import outranks the fetch: it is the thing the user just did, and
        // it is why the fetch will come back non-empty.
        if isPreparingImport { return .importing }
        if isFetchingContents { return .loadingContents }
        return .empty
    }

    /// The skeleton shown while work already in flight will fill this folder.
    /// Deliberately the same shape and metrics as `emptyState` so the swap to
    /// real content doesn't relayout the pane (#3614 "Every Frame Perfect").
    func contentPlaceholderState(_ placeholder: LibraryEmptyPlaceholder) -> some View {
        VStack(spacing: 12) {
            ProgressView()
                .controlSize(.large)

            // "Importing…", not "Preparing Import…". This placeholder is shown
            // for the WHOLE import — Daniel watched it read "Preparing Import…
            // / Reading the dropped items" while the engine had already ingested
            // the file and created 50 page children. The label described the
            // first instant and then asserted it for a minute.
            //
            // It does not claim a finer phase because the app cannot observe
            // one here: `importingLibrary` is a single boolean-ish state, and a
            // label that names a phase we cannot see would be the same lie in
            // nicer words. Say the true, coarse thing.
            Text(placeholder == .importing ? "Importing…" : "Loading…")
                .font(.headline)

            Text(placeholder == .importing
                 ? "Large documents can take a minute"
                 : "Fetching this folder’s contents")
                .font(.subheadline)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    /// ONE honest line, derived from the actual phase (#4372).
    ///
    /// This used to stack "Loading Documents…" over "Connecting to library
    /// data" — two different states asserted simultaneously, so at launch the
    /// pane claimed to be fetching a tree from an engine it had not connected
    /// to yet. Connecting and loading are different answers; the pane now gives
    /// whichever one is true.
    var loadingState: some View {
        VStack(spacing: 12) {
            ProgressView()
                .controlSize(.large)

            Text(loadingMessage)
                .font(.headline)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    /// The honest sentence for the current engine phase. Single source: the
    /// engine popover renders the very same string for the very same failure,
    /// so the two surfaces cannot describe one outage two ways (#4380).
    var engineStatusDetail: String {
        ConnectionPresentation.status(
            phase: appState.engine.phase,
            ownership: ConnectionPresentation.EngineOwnership.current(),
            accessError: appState.backendAccessError,
            authBroken: appState.authBroken
        ).detail
    }

    /// The current load phase for this collection, read from the single
    /// connection-state source plus this view's own fetch state.
    var libraryLoadPhase: LibraryLoadPhase {
        LibraryLoadPhase.resolve(
            enginePhase: appState.engine.phase,
            ownership: ConnectionPresentation.EngineOwnership.current(),
            hasLoadedSuccessfully: isConnected,
            isFetching: isCollectionLoading,
            isEmpty: isCollectionEmpty,
            engineDetail: engineStatusDetail,
            loadErrorMessage: activeErrorMessage
        )
    }

    /// Short enough to read at a glance (#4366); the detail, when there is any,
    /// belongs in the connection popover.
    var loadingMessage: String {
        let phase = libraryLoadPhase
        if phase == .loadingDocuments, isShowingEntitiesCollection {
            return "Loading entities…"
        }
        // `.empty`/`.loaded`/`.failed` have their own views and never reach the
        // spinner branch; "Loading…" is the honest last resort if one ever does.
        return phase.message ?? "Loading…"
    }

    func errorState(message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 40))
                .foregroundColor(.orange)

            Text(isShowingEntitiesCollection ? "Couldn’t Load Entities" : "Couldn’t Load Documents")
                .font(.headline)

            Text(message)
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 460)

            Button("Retry") {
                if isShowingEntitiesCollection {
                    Task {
                        await loadEntitiesIfNeeded()
                    }
                } else {
                    onRetry()
                }
            }
            .keyboardShortcut("r", modifiers: .command)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    /// Why this pane is empty, from the ONE mapping (#4403). Reading it here
    /// rather than re-deriving in the body is what stops the body contradicting
    /// the search header above it.
    var emptyReason: LibraryEmptyReason {
        LibraryEmptyReason.resolve(
            isShowingEntities: isShowingEntitiesCollection,
            filterText: searchText,
            activeSearchQuery: activeSearchQuery,
            hitCounts: searchHitCounts
        )
    }

    var emptyState: some View {
        let reason = emptyReason
        return VStack(spacing: 12) {
            Image(systemName: reason.systemImage)
                .font(.largeTitle)
                .foregroundColor(.secondary)

            Text(reason.title)
                .font(.headline)

            Text(reason.message)
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 420)

            if reason.offersClearFilter {
                // Escape route — clicking a tag in a row could trap the
                // user with a stuck filter and no visible filter bar
                // (the user hit this with "Image"). Always offer Clear.
                Button {
                    searchText = ""
                    showFilterBar = false
                } label: {
                    Label("Clear Filter", systemImage: "xmark.circle.fill")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .padding(.top, 4)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        // The empty-library right-click (#4449). `libraryRowsOrEmptyState`
        // branches HERE before the `displayMode` switch, so an empty library
        // never renders the icon grid whose gutter carried the only
        // empty-area Import menu — a new user's first right-click found
        // nothing. The `.frame(maxWidth/maxHeight: .infinity)` above is what
        // makes the whole blank pane the hit area, not just the text.
        //
        // Gated on `offersImport`, so a filtered/searched-out body or an
        // entity projection shows no menu rather than one that would import
        // into a container the user cannot currently see.
        .contextMenu {
            if reason.offersImport {
                libraryEmptyAreaImportMenu
            }
        }
    }

    func loadEntitiesIfNeeded() async {
        guard isShowingEntitiesCollection else { return }
        isLoadingEntities = true
        entityLoadErrorMessage = nil
        defer { isLoadingEntities = false }
        do {
            let fetched = try await entityService.listEntities(limit: 1000)
            guard !Task.isCancelled else { return }
            entities = fetched
            // Eagerly recompute so syncSelectionToLoadedEntities reads the fresh filteredEntities.
            recomputeFiltered()
            syncSelectionToLoadedEntities()
        } catch {
            guard !Task.isCancelled else { return }
            entities = []
            entityLoadErrorMessage = error.localizedDescription
        }
    }

    func entitySelectionId(for entity: Components.Schemas.KnowledgeEntity) -> String {
        entity.id ?? entity.stableInspectorId
    }

    func focusEntityIfPossible(_ entity: Components.Schemas.KnowledgeEntity) {
        guard let entityId = entity.id, !entityId.isEmpty else { return }
        kgFocusState.focusEntity(entityId: entityId)
    }

    func syncSelectionToLoadedEntities() {
        let validIds = Set(filteredEntities.map { entitySelectionId(for: $0) })
        selection = selection.intersection(validIds)
        if let selectionAnchor, !validIds.contains(selectionAnchor) {
            self.selectionAnchor = nil
        }
    }
}
