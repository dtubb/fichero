import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "DocumentTabView")

/// Per-window host for a library. **This view IS live** — `LibraryWorkspaceRoot`
/// mounts one per window; its load-bearing job is to (a) gate on
/// `appState.isBackendRunning` (showing `BackendConnectionView` until the engine
/// is up) and (b) forward the per-library `@Environment` services into
/// `ContentView()`, which is the actual app UI. Do not delete it.
///
/// **The `document.viewMode` switch below is LEGACY, though (#3583).** It dates
/// from a pre-WindowGroup design where "each tab was a viewMode" — a separate
/// `DocumentTabView` case (workflow / chat / search / batches / …) per tab. That
/// model was replaced: today the whole app lives in the `.library` case
/// (`ContentView`), where workflow/chat/search/KG are *sidebar modes*, and NEW
/// windows + native macOS tabs are opened through `WindowOpener` (#1685/#3582),
/// NOT by switching `viewMode`. `FicheroDocument.viewMode` never leaves its
/// `.library` default in the live tree, so every case except `.library` is an
/// unreachable `ContentUnavailableView`/placeholder.
///
/// Future devs: to add a new surface, extend `ContentView`'s sidebar modes or
/// open a window via `WindowOpener` — do NOT add cases to the switch below or
/// build on the `*PlaceholderView`s; that abstraction is retired.
struct DocumentTabView: View {
    let libraryId: UUID  // ID of the library this view is displaying
    @Binding var document: FicheroDocument
    let documentURL: URL?  // URL of the .fichero package file
    @Environment(AppState.self) var appState
    @Environment(LibraryManager.self) var libraryManager
    @Environment(ViewSettings.self) var viewSettings

    // All services come from the environment (shared per-library, not per-tab)
    @Environment(DocumentStore.self) var documentStore: DocumentStore
    @Environment(SavedSearchService.self) var savedSearchService
    @Environment(SearchService.self) var searchService
    @Environment(ConversationService.self) var conversationService
    @Environment(ChatService.self) var chatService
    @Environment(WorkflowStore.self) var workflowStore
    @Environment(ImportService.self) var importService
    @Environment(DocumentService.self) var documentService
    @Environment(StorageService.self) var storageService
    @Environment(WorkflowStreamService.self) var workflowStreamService
    @Environment(ResearchService.self) var researchService
    @Environment(WindowState.self) var windowState

    // @Observable objects injected by LibraryWindow and re-forwarded to
    // ContentView() below.
    //
    // This block used to claim "SwiftUI does not re-propagate
    // @Environment(T.self) values across an explicit .environment() chain".
    // **That is almost certainly false and the claim is withdrawn** (#4455).
    // `.environment(x)` ADDS a value; it does not clear the others, and values
    // inherit down a view tree. The evidence against it is direct: fourteen
    // library-scoped types were NOT forwarded here — AnnotationStore with 8
    // readers, ProviderAPIService and WorkflowService with 6 each — and none of
    // them was crashing. Under that claim they would trap routinely.
    //
    // What IS real is that some boundary exists, because #4448 was a genuine
    // crash. The two candidates, neither of which this chain addresses:
    // separate `Scene`s (which `ArtifactServiceInjectionTests` documents and
    // which explains #3350), and window-hosted toolbar content (which fits
    // #4448, whose backtrace trapped in `HostPreferencesCombiner` for types
    // read by `StatusIslandToolbarItem`/`ActivityStatusToolbarItem`).
    //
    // So this list is very likely a wrong generalisation of two narrower rules.
    // It is kept for now because removing it needs a runtime check nobody has
    // run — do NOT add to it on the strength of the old claim, and see #4455
    // before treating a missing entry here as the cause of anything.
    @Environment(ArtifactService.self) var artifactService
    @Environment(EntityService.self) var entityService
    @Environment(KGCurationService.self) var kgCurationService
    @Environment(ArtifactStore.self) var artifactStore
    @Environment(EntityStore.self) var entityStore
    @Environment(ClaimStore.self) var claimStore
    @Environment(ClaimFocusState.self) var claimFocusState
    @Environment(KGFocusState.self) var kgFocusState
    @Environment(WorkflowExecutionObserver.self) var executionObserver

    // Get the library reference
    private var library: LibraryManager.LibraryReference? {
        LibraryManager.shared.getLibrary(id: libraryId)
    }

    private var apiClient: APIClient? {
        library?.apiClient
    }

    init(libraryId: UUID, document: Binding<FicheroDocument>, documentURL: URL?) {
        self.libraryId = libraryId
        self._document = document
        self.documentURL = documentURL
    }

    var body: some View {
        ZStack {
            // Get right to the app: render the real content in EVERY engine phase,
            // even not-yet-connected / failed. The connection state is surfaced
            // NON-MODALLY by `EngineStatusToolbarItem` in the toolbar (with Retry),
            // never as a full-tab `BackendConnectionView` takeover. The old
            // `if isBackendRunning { content } else { connectionView }` swap
            // re-introduced exactly the full-window error splash the root gate
            // (`BackendRootGate`) removed (startup-transport-ux S1). ContentView
            // handles a down backend with inline empty/error states.
            contentView
        }
        // ★ EVERY FRAME PERFECT (#3615): surface color as the base layer so a
        // not-yet-painted ContentView first frame never exposes a bare white frame.
        .background(Color(platformColor: .windowBackgroundColor))
        .task {
            guard !Task.isCancelled else { return }
            // Library path is already set in LibraryManager when library was opened
            if let apiClient = apiClient {
                let clientIdString = String(describing: ObjectIdentifier(apiClient))
                let pathString = apiClient.currentLibraryPath ?? "none"
                let libraryIdString = String(describing: libraryId)
                logger.info("Using library \(libraryIdString) with APIClient-\(clientIdString), path: \(pathString)")
            }

            // Load data for this tab's context
            await loadContext()
        }
        .onChange(of: document.viewMode) { _, _ in
            // Update last modified when view mode changes
            document.lastModified = Date()
        }
    }

    @ViewBuilder
    private var contentView: some View {
        // Bind the LIBRARY, not just its apiClient. Every value forwarded below
        // that is library-scoped is then read off one resolved reference, so a
        // new forward cannot be added from a stale second lookup — and the two
        // activity stores below have a source without DocumentTabView having to
        // declare more non-optional @Environment reads of its own.
        if let library {
            ContentView()
                .environment(appState)
                .environment(viewSettings)
                .environment(library.apiClient)
                .environment(documentStore)
                .environment(savedSearchService)
                .environment(searchService)
                .environment(conversationService)
                .environment(chatService)
                .environment(workflowStore)
                .environment(importService)
                .environment(documentService)
                .environment(storageService)
                .environment(workflowStreamService)
                .environment(researchService)
                .environment(windowState)
                // App-wide singletons injected at the ContentView host so
                // ContentView reads them via environment injection rather
                // than grabbing `.shared` — the DI seam for #3033. Shared
                // instances, no new objects created here.
                .environment(ErrorService.shared)
                .environment(FeatureManager.shared)
                // Forward the @Observable artifact service so the library
                // subtree built after `selectCollection` (LibraryView →
                // inspector / artifact cells) can read it via
                // @Environment(ArtifactService.self). Without this,
                // opening a library or selecting a collection traps with
                // "No Observable object of type ArtifactService
                // found." (#3350)
                .environment(artifactService)
                // The inspector reads the entity / KG services + stores
                // from ContentView, not directly from DocumentTabView's
                // parent environment. Forward them here too so the
                // inspector still resolves its dependencies during the
                // first render before windowState.library is available.
                .environment(entityService)
                .environment(kgCurationService)
                .environment(artifactStore)
                .environment(entityStore)
                .environment(claimStore)
                // SPARQL console store (#3298/#1863): the console reads it
                // from the environment instead of scraping a client off
                // LibraryManager.shared.
                .environment(appState.kgQueryStore)
                // These app-/library-scoped @Observable focus + substrate
                // services are also read directly by ContentView. Forward
                // them here so switching into Research / KG / claim-focused
                // surfaces never depends on accidental inheritance past the
                // explicit ContentView() host.
                .environment(claimFocusState)
                .environment(kgFocusState)
                // Forward the @Observable observer so ContentView and its subtree
                // (DocumentInspector → ArtifactEntityViews) can read it via
                // @Environment(WorkflowExecutionObserver.self). Without this the
                // environment chain breaks at the ContentView() host and crashes
                // with "No Observable object of type WorkflowExecutionObserver found."
                // (#1561). Single shared instance — no new object created here.
                .environment(executionObserver)
                // #4448: the two activity stores were the last library-scoped
                // values a view under this host read non-optionally without
                // being forwarded here. `StatusIslandToolbarItem` and
                // `ActivityStatusToolbarItem` read ActivityStore, and
                // `ActivityBrowserView` reads WorkflowExecutionStore; all three
                // mount inside ContentView. They resolved only by inheritance
                // past this explicit host — the same accident that produced
                // #3350 and #1561 — and a toolbar item is the worst place to
                // rely on it, because toolbar content is laid out by the window
                // and can be updated after the content subtree has changed.
                .environment(library.activityStore)
                .environment(library.workflowExecutionStore)
                // #4455: the remaining library-scoped values a view under this
                // host reads NON-OPTIONALLY. They resolved only by inheritance
                // past this explicit host — the accident behind #1561, #3298,
                // #3350 and #4448 — and each was one click away from the same
                // "No Observable object of type X found" trap. Baselined as debt
                // by scripts/check_environment_forwarding.py when #4448 shipped;
                // paid off here, which empties that baseline.
                .environment(library.bookmarkService)
                .environment(library.workspaceStore)
                .environment(library.batchStore)
                .environment(library.workflowService)
                .environment(library.providerService)
                .environment(library.modelService)
                .environment(library.noteStore)
                .environment(library.annotationStore)
                .environment(library.actionStore)
                .environment(library.chainStore)
                .environment(library.researchStore)
                .environment(library.citationStore)
                .environment(library.referenceStore)
                .environment(library.interpretationStore)
        } else {
            Text("Library not found")
                .font(.headline)
                .foregroundColor(.secondary)
        }
    }

    private func loadContext() async {
        // Context loading is handled by individual views via their own .task modifiers
        // This method exists for future cross-view state restoration if needed
    }
}
