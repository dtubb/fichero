import Combine
import FicheroAPIClient
import SwiftUI

// MARK: - LibraryView body (file-length split, 2026-08-13)
//
// The processing-poll fallback, first-load state, and `body` itself.
// Members other split files reach were promoted private -> internal.

extension LibraryView {
    private static let processingPollTimer = Timer.publish(every: 15, on: .main, in: .common).autoconnect()
    private var processingPollTimer: Publishers.Autoconnect<Timer.TimerPublisher> { Self.processingPollTimer }

    private var shouldUseProcessingPollFallback: Bool {
        guard let ref = scopedLibraryReference else { return false }
        return ref.changeStream.liveUpdatesUnavailable || ref.activityStore.liveUpdatesPaused
    }

    /// The library has never loaded and nothing has failed — startup, not an
    /// outage (#3937).
    var isAwaitingFirstLoad: Bool {
        guard !isShowingEntitiesCollection else { return false }
        return Self.isAwaitingFirstLoad(hasLoadedSuccessfully: isConnected, error: documentStore.error)
    }

    /// A store that has never loaded is starting up, not offline (#3937).
    ///
    /// `DocumentStore.isConnected` only flips true once a load SUCCEEDS, so on its
    /// own it cannot tell "healthy but not asked for data yet" from "offline". The
    /// absence of an error is what separates the two — which is why this can never
    /// mask a real outage: the instant a load fails, `error` is set and the
    /// failure branches win.
    ///
    /// Pure so the invariant is testable without a live engine, the same reason
    /// `ConnectionPresentation.failureTitle` is pure (#3341).
    /// `nonisolated` is LOAD-BEARING: a static on a `View` inherits the type's
    /// MainActor isolation under the macOS 26 SDK, and the Swift Testing suite
    /// that calls this runs on a cooperative thread — the off-main call
    /// SIGTRAPs the whole test process, nondeterministically and misattributed
    /// to whichever test happened to be running (#4201).
    nonisolated static func isAwaitingFirstLoad(hasLoadedSuccessfully: Bool, error: Error?) -> Bool {
        !hasLoadedSuccessfully && error == nil
    }

    /// True only when a load failed because the engine could not be REACHED
    /// (#3937) — the one state that earns the outage pane. Every other failure
    /// keeps its own message via `errorState`, and no failure at all is not an
    /// outage. Reuses the one `AccessError` classifier instead of re-reading
    /// `URLError` codes here. An already-typed `AccessError` never arrives: the
    /// access-denied branch above claims it first.
    /// `nonisolated` for the same load-bearing reason as `isAwaitingFirstLoad`
    /// above — and it must stay that way transitively: everything this reads
    /// (`AccessError.classify`) has to be callable off-main too (#4201).
    nonisolated static func isEngineOutage(_ error: Error?) -> Bool {
        guard let error else { return false }
        return AccessError.classify(error) == .engineUnreachable
    }

    // Extracted from `body` to keep the body modifier chain within the Swift
    // type-checker's budget — adding the #2307 onChange handlers tipped the
    // single expression over "unable to type-check in reasonable time".
    // See memory: librarywindow-body-typecheck-timeout.

    var body: some View {
        withKeyboardShortcuts(eventWiredContent)
        // No toolbar .searchable here — ContentView owns the single GLOBAL
        // toolbar search (files), which already routes to runToolbarSearch. A
        // second .searchable in this window is a duplicate com.apple.SwiftUI.search
        // and can crash the macOS toolbar (#3163). The inline ⌘F filter stays.
    }

    // The one body expression exceeded the type-checker's budget once it moved
    // into this extension (same failure class as the LibraryWindow.body
    // timeout): split at a structural seam — layout+insets+background below,
    // sheets+events chained on top in `eventWiredContent`.
    private var structuralContent: some View {
        VStack(spacing: 0) {
            libraryContent
        }
            // No-silent-fallback (F7): if this library's change stream drops, say
            // so with a pill above the content instead of quietly showing stale
            // rows. Reserving real space keeps the first row from peeking
            // through behind the pill.
            .safeAreaInset(edge: .top, spacing: 0) {
                liveUpdatesPausedInset
            }
            // The library's own mini toolbar (#4407 / #4374): search, sort and
            // filter live with the surface they act on. Top on the Mac, bottom
            // on touch — the same single platform decision the reader's find
            // bar makes, from the same place, so the two panes agree. Because
            // it is an inset on THIS view it resizes with the library pane and
            // disappears with it, which window chrome could never do.
            .safeAreaInset(edge: .top, spacing: 0) {
                if Self.miniToolbarPlacement == .top {
                    PaneFilterBar(placement: .top) { libraryMiniToolbar }
                }
            }
            // Closes the sidebar-click interval opened in `handleSelectionChange`
            // (#4228). See `InteractionProfile.Phase.selectionToContent` for what
            // this end point does and does not measure.
            .task(id: folderId) { InteractionProfile.end(.selectionToContent, detail: folderId ?? "nil") }
            // Xcode-navigator-style quick filter, pinned to the BOTTOM of the
            // library list pane. Narrows the rows currently shown client-side
            // (binds `searchText`, which drives `filteredDocuments`) — distinct
            // from the toolbar `.searchable`, which fires a *global* search.
            // Revealed on demand by ⌘F / the toolbar filter toggle, matching
            // Xcode's navigator filter field.
            .safeAreaInset(edge: .bottom, spacing: 0) {
                bottomInsetContent
            }
            .background(
                Group {
                    if featureManager.isLibraryFilterToolbarEnabled {
                        Button("") {
                            showFilterBar = true
                            filterFieldFocused = true
                        }
                        .keyboardShortcut("f", modifiers: .command)
                        .hidden()
                    }
                }
            )
    }

    private var eventWiredContent: some View {
        structuralContent
            // Sheets are a HOSTING BOUNDARY (2026-08-08 night review B3, the
            // crash class that killed the app four times that day): content
            // must be re-injected with every non-optional @Environment object
            // it reads. WorkflowEditor's sheet (its own file) is the house
            // convention; these three under-injected. The full library list
            // is the safe form — a hand-picked subset crashes on the next
            // service a sheet grows.
            .sheet(isPresented: $showWorkflowPicker) {
                WorkflowPickerSheet(
                    selectedDocumentIds: selectedDocumentIdsForBatch,
                    onSelect: { workflowId in
                        Task { @MainActor in
                            await runBatchWorkflow(workflowId: workflowId)
                        }
                    }
                )
                .environment(libraryManager)
                .environment(executionObserver)
                .environment(windowState)
                .modifier(SheetLibraryEnvironment(library: scopedLibraryReference))
            }
            .sheet(item: $workspacePickerDocument) { document in
                WorkspaceItemPicker(document: document)
                    .environment(executionObserver)
                    .modifier(SheetLibraryEnvironment(library: scopedLibraryReference))
            }
            .sheet(item: $bookmarkPickerDocument) { document in
                BookmarksView(document: document, onOpen: { openDocument($0) })
                    .modifier(SheetLibraryEnvironment(library: scopedLibraryReference))
            }
            // A failed drop onto a folder cell must SAY so (#4474). It used to
            // be logged only, so a refused move looked exactly like one that
            // worked. Extracted as a modifier rather than an inline `.alert`
            // because this body is already near the type-checker's limit.
            .modifier(LibraryDropAlertModifier(windowState: windowState))
            .focusedSceneValue(\.runWorkflowOnSelection, runWorkflowOnSelectionAction)
            // Data-menu Import… while the LIBRARY pane (not the sidebar) has
            // focus (#4452). Deliberately the narrow `libraryImportAction`
            // key, not `sidebarActions` — see that key's doc comment for why
            // stubbing the other 10 SidebarActions closures would be a new
            // silent no-op bug of the exact shape #4449 just closed.
            .focusedValue(\.libraryImportAction) { mode in
                fileImportMode = mode
                fileImportTargetFolderId = folderId
                showingFileImporter = true
            }
            .onAppear {
                if outlineModel == nil {
                    outlineModel = LibraryOutlineModel(
                        service: entityService,
                        artifactService: artifactService
                    )
                }
                // Mode-specific caches only when their view is the one shown on
                // appear (#3867/#3870); switching in later re-syncs via
                // onChange(displayMode). refreshLibraryProjection self-gates.
                if displayMode == .table { syncPagesByParentId() }
                loadSortSettings(for: folderId)
                syncSortOrder()
                recomputeFiltered()
                refreshLibraryProjection()
                consumePendingOpen()
            }
            // Merged the two former documentStore.revision observers into one
            // (#3870) — SwiftUI would run both every revision.
            .onChange(of: documentStore.revision) { _, _ in
                // Pending-open hand-off retry once rows arrive (#1685).
                recomputeFiltered()
                refreshLibraryProjection()               // no-op unless canvas/space (#3867)
                if displayMode == .table { syncPagesByParentId() }  // outline-only (#3870)
                consumePendingOpen()
            }
            // Recompute mode-specific caches lazily on switch-in, since the
            // per-revision paths now skip them off-mode (#3867 / #3870).
            .onChange(of: displayMode) { _, _ in
                refreshLibraryProjection()
                if displayMode == .table { syncPagesByParentId() }
            }
            .onChange(of: entities) { _, _ in
                recomputeFiltered()
                refreshLibraryProjection()
            }
            .onChange(of: scopedLibraryReference?.activityStore.refreshToken ?? 0) { _, _ in
                refreshPendingStatusesFromLiveUpdate()
            }
            .onChange(of: scopedLibraryReference?.activityStore.backendWork) { _, _ in
                refreshPendingStatusesFromLiveUpdate()
            }
            // Debounce ⌘F keystrokes (#3865): `.task(id:)` cancels the pending
            // task per keystroke → filter runs once after a ~200ms pause, not per
            // key. Empty query (clear) applies instantly; reuses the current index.
            .task(id: searchText) {
                if !searchText.isEmpty {
                    try? await Task.sleep(for: .milliseconds(200))
                    if Task.isCancelled { return }
                }
                recomputeFiltered(rebuildIndex: false)
            }
            .onChange(of: folderId) { _, newId in
                loadSortSettings(for: newId)
                syncSortOrder()
                // A folder remembers its own sort, so navigating can change the
                // server request without the sort menu being touched (#3322).
                syncServerListingSort()
                recomputeFiltered()
            }
            .onChange(of: sortFieldRaw) { _, _ in
                // O1: skip when a sortOrder/table-header write already owns
                // the sync — this handler exists for EXTERNAL field writes.
                guard !isApplyingSortChange else { return }
                syncSortOrder()
                saveSortSettings(for: folderId)
                syncServerListingSort()
                recomputeFiltered()
            }
            .onChange(of: sortAscending) { _, _ in
                guard !isApplyingSortChange else { return }
                syncSortOrder()
                saveSortSettings(for: folderId)
                // Direction is the engine's business for a server-ordered sort:
                // reversing the array here would flip rows without re-deciding
                // the precision ties (#3322).
                syncServerListingSort()
                recomputeFiltered()
            }
            .onChange(of: sortOrder) { _, newOrder in
                isApplyingSortChange = true
                handleSortOrderChange(newOrder)
                isApplyingSortChange = false
                syncServerListingSort()
                recomputeFiltered()
            }
            .onChange(of: showFilterBar) { _, shown in filterBarVisibilityChanged(shown) }
            .onReceive(processingPollTimer) { _ in
                guard shouldUseProcessingPollFallback else { return }
                refreshPendingStatusesFromLiveUpdate()
            }
            .task(id: entityCollectionTaskKey) {
                await loadEntitiesIfNeeded()
            }
            // Suppress implicit animations on folder change — icons should appear
            // instantly, not slide in cascading from the top.
            .transaction(value: folderId) { $0.animation = nil }
    }
}
