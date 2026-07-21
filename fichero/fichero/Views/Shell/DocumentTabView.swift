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

    // @Observable objects injected by LibraryWindow — must be forwarded explicitly
    // when ContentView() is constructed below (SwiftUI does not re-propagate
    // @Environment(T.self) values across an explicit .environment() chain).
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
        if let apiClient = apiClient {
            ContentView()
                .environment(appState)
                .environment(viewSettings)
                .environment(apiClient)
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
