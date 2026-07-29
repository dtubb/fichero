import FicheroAPIClient
import Observation
import os
import OSLog
import SwiftUI

let libraryManagerLogger = Logger(subsystem: "app.fichero.fichero", category: "LibraryManager")

/// Manages multiple open .fichero libraries
/// Allows multiple windows and tabs to reference the same library instance
@MainActor
@Observable
class LibraryManager {
    static let shared = LibraryManager()

    /// Fixed UUID for the Global library (cross-library searches, chats, workflows)
    static let globalLibraryId = UUID(uuidString: "00000000-0000-0000-0000-000000000001")!

    /// All currently open libraries (Global is always last)
    var openLibraries: [LibraryReference] = []

    /// The currently active library (used for new tabs/windows)
    var currentLibraryId: UUID?

    /// Cross-window "Open in New Tab / New Window" intent (#1685). Set just
    /// before `openWindow(id: "main")`; the destination LibraryView consumes
    /// and clears it once its documents load, so the freshly opened window
    /// focuses the requested document. Reuses the Safari new-window path —
    /// no parallel tab system.
    var pendingOpenDocumentId: String?

    /// Cross-window library handoff queue for open-in-new-window flows. The
    /// caller appends one library id per `openWindow(id: "main")`; each new
    /// destination scene consumes the oldest pending id during initialization
    /// so batched opens don't clobber one another.
    var pendingWindowLibraryIds: [UUID] = []

    /// Counter for unsaved library numbering (Untitled, Untitled 2, Untitled 3, etc.)
    var untitledCounter: Int = 1

    /// Library data loads are deferred until the backend is confirmed running.
    /// FicheroApp restores libraries before EmbeddedBackendService finishes its
    /// startup probe; firing document/workflow/search requests during that
    /// window creates noisy Network.framework path-check errors on launch (#1163).
    var backendIsReady = false
    var loadedLibraryIds: Set<UUID> = []
    var loadingLibraryIds: Set<UUID> = []

    /// Security-scoped libraries whose sandbox grant is still in flight (#3986-A).
    /// A user-picked package on the MAS/sandbox build must NOT be loaded until its
    /// grant's network round-trip completes — otherwise the restore / backend-ready
    /// path races the grant and the engine reads the package before it has access
    /// (#3773). `loadAndRegister` adds the id when it issues the grant and the
    /// grant's own engineWork removes it, so only that path fires the first load.
    /// Non-sandbox builds and temporary/remote/global libraries never enter this
    /// set (their grant is a no-op) and so are never deferred.
    var libraryIdsAwaitingGrant: Set<UUID> = []

    /// Bumped each time a library's data finishes loading. SidebarView observes
    /// this via @State to trigger rebuildCaches() — ensures the sidebar
    /// populates on iPhone even when its .task fires before loadCollections() (#2472).
    var librariesLoadVersion: Int = 0

    /// Represents an open library with its associated resources
    /// Each library has one instance of each service, shared across all windows/tabs viewing this library
    @MainActor
    @Observable
    class LibraryReference: Identifiable {
        let id: UUID
        let url: URL
        /// Which backend this library talks to (#2866). Defaults to the local
        /// embedded engine; a remote library carries its own host so the app can
        /// hold several backends at once. Drives the clients' baseURL, the TLS
        /// pin, and the sidebar location badge.
        let host: BackendHost
        var displayName: String  // Display name for window title (e.g., "Untitled 2", "MyResearch")
        var document: FicheroDocument

        // Core services - one instance per library, shared across all tabs/windows
        let apiClient: APIClient
        let ficheroClient: FicheroClient  // Generated API client
        let documentStore: DocumentStore
        let savedSearchService: SavedSearchService  // Generated saved search service
        let bookmarkService: BookmarkService  // Generated bookmark service (#2755)
        let searchService: SearchService
        let conversationService: ConversationService  // Generated conversation service
        let chatService: ChatService  // Generated chat service
        let workflowStore: WorkflowStore
        let workflowService: WorkflowService  // Generated workflow service
        let workflowStreamService: WorkflowStreamService  // SSE streaming for workflow execution
        let importService: ImportService
        let documentService: DocumentService
        let storageService: StorageService
        let providerService: ProviderAPIService
        let modelService: ModelService
        let artifactService: ArtifactService
        let entityService: EntityService  // /api/entities + /api/claims (#728)
        let kgCurationService: KGCurationService
        let activityService: ActivityService
        let batchService: BatchService
        let automationService: AutomationAPIService
        let chainService: ChainService
        let researchService: ResearchService
        let noteService: NoteService
        let annotationService: AnnotationService
        let actionsService: ActionsService

        // Observable domain stores (#1851 / #1885) — wrap the transport wrappers
        // above. One per library, shared across that library's windows, so a
        // mutation in one window reaches every window's views through the shared
        // store. Lazy: built on first use. See
        // docs/contributor/architecture/fichero/observable_data_layer.md.
        @ObservationIgnored lazy var entityStore: EntityStore = EntityStore(
            entityService: entityService,
            kgCurationService: kgCurationService,
            libraryPath: url.path
        )

        /// Per-library claim store (#1862) — wraps the same transport wrappers,
        /// owns the claim list for the current document/entity scope, and reacts
        /// to `claim.*` change events. Retires the `.ficheroClaim*`
        /// NotificationCenter bus.
        @ObservationIgnored lazy var claimStore: ClaimStore = ClaimStore(
            entityService: entityService,
            kgCurationService: kgCurationService,
            libraryPath: url.path
        )

        /// Per-library note store (#1882). Wraps `noteService`, owns the note
        /// list for the current scope, and reacts to `note.*` change events.
        @ObservationIgnored lazy var noteStore: NoteStore = NoteStore(noteService: noteService)

        /// Per-library annotation store (#1883). Wraps `annotationService`,
        /// owns the annotation list for the current scope, and reacts to
        /// `annotation.*` change events.
        @ObservationIgnored lazy var annotationStore: AnnotationStore = AnnotationStore(annotationService: annotationService)

        /// Per-library action store (#1905). Wraps `actionsService`, owns the
        /// action list + categories, and reacts to `action.*` change events.
        @ObservationIgnored lazy var actionStore: ActionStore = ActionStore(service: actionsService)

        /// Per-library activity store (#2448). Wraps `activityService`, owns the
        /// run-browser list, and signals `ActivityBrowserView` to refresh on
        /// `workflow.*` SSE events (best-effort until the backend emits dedicated
        /// `activity.*` events).
        @ObservationIgnored lazy var activityStore: ActivityStore = ActivityStore(service: activityService)

        /// Per-library chain store (#3191). Wraps `chainService` so chain views
        /// observe store state instead of instantiating transports directly.
        @ObservationIgnored lazy var chainStore: ChainStore = ChainStore(chainService: chainService)

        /// Per-library live workflow-execution store (#2546). Keyed by `threadId`,
        /// it is the shared home for live execution state feeding the Activity
        /// monitor: it subscribes-on-select to a running thread's SSE stream
        /// (reusing `WorkflowStreamService`) and reduces events via the shared
        /// `WorkflowExecution.apply(_:)`, so Activity shows live progress for ANY
        /// running workflow regardless of where it was started.
        @ObservationIgnored lazy var workflowExecutionStore: WorkflowExecutionStore = WorkflowExecutionStore(
            ficheroClient: ficheroClient,
            activityService: activityService
        )

        /// Per-library audit store (#2085). Reads the global "who changed what"
        /// action-registry log (`GET /api/actions/audit`) and undoes rows
        /// (`POST /api/actions/audit/{id}/undo`) through the generated client.
        @ObservationIgnored lazy var auditStore: AuditStore = AuditStore(client: ficheroClient)

        /// Per-library backup store (#2087). Lists / creates / restores / deletes
        /// point-in-time snapshots (`/api/storage/snapshots`) through the
        /// generated client.
        @ObservationIgnored lazy var backupStore: BackupStore = BackupStore(client: ficheroClient)

        /// Per-library research store (#1904). Wraps `researchService`, owns the
        /// per-project data (plans, tasks, checklists, sources, notes), and
        /// reacts to `research.*` change events.
        @ObservationIgnored lazy var researchStore: ResearchStore = ResearchStore(researchService: researchService)

        /// Per-library saved agent workspaces (#3533 / #3547). Owns the workspace
        /// list; save/list/delete route through `chatService`.
        @ObservationIgnored lazy var workspaceStore: WorkspaceStore = WorkspaceStore(chatService: chatService)

        /// Per-library workflow batch runs (#3536). Owns the batch list + the
        /// folder-fan-out create; routes through `batchService`.
        @ObservationIgnored lazy var batchStore: BatchStore = BatchStore(batchService: batchService)

        /// Per-library search store (#1903). Wraps `searchService`, owns the
        /// current result set and index stats, and invalidates stale results on
        /// `document.*` change events.
        @ObservationIgnored lazy var searchStore: SearchStore = SearchStore(searchService: searchService)

        /// Per-document artifact store (#1997). Wraps `artifactService`, owns the
        /// selected document's artifacts, and reacts to `artifact.*` change
        /// events. Built on the generic `ObservableDomainStore` substrate.
        @ObservationIgnored lazy var artifactStore: ArtifactStore = ArtifactStore(artifactService: artifactService)

        /// Per-document citation store (#1998). Wraps `entityService`, owns the
        /// selected document's inbound/outbound citations + usage rows, and
        /// reacts to `citation.*` change events.
        @ObservationIgnored lazy var citationStore: CitationStore = CitationStore(entityService: entityService)

        /// Per-document reference store (#1999). Wraps `entityService`, owns the
        /// selected document's extracted bibliography, and reacts to
        /// `reference.*` change events.
        @ObservationIgnored lazy var referenceStore: ReferenceStore = ReferenceStore(entityService: entityService)

        /// Per-document interpretation store (#2009). Wraps `entityService`, owns
        /// the selected document's hermeneutic interpretations, and reacts to
        /// `interpretation.*` change events (#2008).
        @ObservationIgnored lazy var interpretationStore: InterpretationStore = InterpretationStore(entityService: entityService)

        /// Per-library canvas layout store (#2293 / #3082) — ONE instance shared
        /// across this library's windows and both the 2D and future 3D renderers,
        /// so moving an item in one window moves it in the others. Scope-keyed by
        /// folder id; reacts to `canvas.*` change events for cross-device sync.
        @ObservationIgnored lazy var canvasLayoutStore: CanvasLayoutStore = CanvasLayoutStore(client: ficheroClient)

        /// Per-library canvas item store (#2294 / #3082) — sibling to
        /// `canvasLayoutStore` owning the standalone item CONTENT. Shared instance,
        /// scope-keyed, on the `canvas` change domain.
        @ObservationIgnored lazy var canvasItemStore: CanvasItemStore = CanvasItemStore(client: ficheroClient)

        /// One SSE change-stream per library (#1863), fanning events to the
        /// stores above. `start()` is idempotent — each window kicks it from
        /// its `.task`; only the first connects.
        @ObservationIgnored lazy var changeStream: LibraryChangeStream = {
            let stream = LibraryChangeStream(
                baseURLProvider: { self.apiClient.baseURL },
                libraryPath: self.url.path,
                transport: FicheroClientChangeStreamTransport(client: self.ficheroClient)
            )
            stream.register(self.documentStore)
            stream.register(self.entityStore)
            stream.register(self.claimStore)
            stream.register(self.noteStore)
            stream.register(self.annotationStore)
            stream.register(self.actionStore)
            stream.register(self.activityStore)
            stream.register(self.researchStore)
            stream.register(self.searchStore)
            stream.register(self.workflowStore)
            stream.register(self.artifactStore)
            stream.register(self.citationStore)
            stream.register(self.referenceStore)
            stream.register(self.interpretationStore)
            stream.register(self.canvasLayoutStore)
            stream.register(self.canvasItemStore)
            // Remote hosts: the dedicated /changes/stream can drop over the
            // tailnet (#2479), so mutations also ride the ACL-scoped activity
            // stream (#3159). Bridge those folded change frames into the same
            // fan-out. Local hosts keep the dedicated stream as the sole source,
            // so leave the router nil there to avoid double-applying (#3159 emits
            // the folded frames unconditionally, on local as well as remote).
            if !self.host.isLocal {
                self.activityStore.changeRouter = { [weak stream] event in
                    stream?.ingest(event)
                }
            }
            return stream
        }()

        /// Whether this library currently holds its security-scoped resource.
        ///
        /// Guarded by a lock rather than `nonisolated(unsafe)`, which the
        /// compiler reports as having NO EFFECT here: it documented intent and
        /// enforced nothing, while two `nonisolated` methods read-modify-wrote
        /// it. A lost update there doesn't crash — it silently loses file
        /// access, or holds a scope forever (#4216).
        ///
        /// `deinit` genuinely runs off the main actor at an unpredictable time:
        /// SwiftUI holds strong references outside `openLibraries` —
        /// `SidebarView.libraryToShare` is `@State`, and `ShareLibrarySheet`,
        /// `SidebarSectionHeader`, `LibraryWorkspaceRoot` and
        /// `LibrarySharingBadge` each take `let library: LibraryReference` — so
        /// a reference can outlive `closeLibrary` and be released by whichever
        /// thread drops it last.
        ///
        /// The methods therefore stay `nonisolated`. `@MainActor` is NOT the
        /// alternative: a `deinit` on a `@MainActor` class cannot call an
        /// isolated method and cannot await, so it fails to compile — and the
        /// workaround that invites, `Task { @MainActor in … }` inside `deinit`,
        /// CAPTURES `self` DURING DEALLOCATION, which is a use-after-free and
        /// far worse than the race it would be fixing. Don't.
        ///
        /// Retiring `deinit`'s stop entirely would close the hole instead of
        /// guarding it (#4219) — blocked today because at least one path
        /// (#4218) drops a library without stopping its scope, so `deinit` is
        /// currently load-bearing.
        private let securityScopeState = OSAllocatedUnfairLock(initialState: false)

        /// Test seam: the flag's value, read through the lock (#4216).
        nonisolated var isAccessingSecurityScope: Bool {
            securityScopeState.withLock { $0 }
        }

        /// Where this library's engine lives — local embedded engine vs a named
        /// remote device/host. Drives the sidebar local-vs-remote badge (#2574).
        /// Reflects the live app-global host today; once libraries are pinned to
        /// a SPECIFIC remote host (#2866 follow-up) this reads `host` instead —
        /// the seam is `host.isLocal`.
        var locationDescriptor: LibraryLocationDescriptor {
            LibraryLocationDescriptor.forHost(host)
        }

        @MainActor
        init(
            url: URL,
            document: FicheroDocument,
            displayName: String,
            id: UUID? = nil,
            host: BackendHost = .appDefault,
            apiClient: APIClient? = nil,
            documentStore: DocumentStore? = nil,
            searchService: SearchService? = nil,
            workflowStore: WorkflowStore? = nil,
            importService: ImportService? = nil,
            storageService: StorageService? = nil,
            providerService: ProviderAPIService? = nil,
            modelService: ModelService? = nil,
            startAccessing: Bool = false
        ) {
            self.id = id ?? UUID()
            self.url = url
            self.host = host
            self.displayName = displayName
            self.document = document

            // Persist this backend's SPKI pin so the pinned session validates
            // its cert (#2866). No-op for the local engine (no pin) and for
            // hosts already pinned.
            host.persistPinIfNeeded()

            // Reuse existing instances or create new ones. A new client targets
            // THIS library's backend host, not the global one.
            if let existingClient = apiClient {
                self.apiClient = existingClient
            } else {
                self.apiClient = APIClient(baseURL: host.url)
            }

            // Set the library path on the API client immediately
            // This ensures all services created below have access to the path
            self.apiClient.currentLibraryPath = url.path

            // Create the generated API client (shares same library path), bound
            // to this library's backend host. Pass `transportMode` so an EMBEDDED
            // engine is dialed over its UDS socket, not TCP https://127.0.0.1:8765
            // (which nothing binds when embedded → errno 61). Mirrors APIClient's
            // inner client and AppState.ficheroClient; without it every generated
            // service on this client (WorkflowStore's list_workflows was the
            // reported symptom) fails "Could not connect to the server".
            self.ficheroClient = FicheroClient(
                baseURL: host.url,
                libraryPath: url.path,
                transportMode: EngineConfig.transportMode
            )

            // Initialize all services with the library's APIClient
            self.documentStore = documentStore ?? DocumentStore(apiClient: self.apiClient)
            self.savedSearchService = SavedSearchService(ficheroClient: self.ficheroClient)
            self.bookmarkService = BookmarkService(ficheroClient: self.ficheroClient)
            self.searchService = searchService ?? SearchService(ficheroClient: self.ficheroClient)
            self.conversationService = ConversationService(ficheroClient: self.ficheroClient)
            self.chatService = ChatService(ficheroClient: self.ficheroClient)
            self.workflowStore = workflowStore ?? WorkflowStore(ficheroClient: self.ficheroClient)
            self.workflowService = WorkflowService(ficheroClient: self.ficheroClient)
            self.workflowStreamService = WorkflowStreamService(ficheroClient: self.ficheroClient)
            self.importService = importService ?? ImportService(ficheroClient: self.ficheroClient)

            #if os(macOS)
            // iOS uses document-picker grants; only the macOS sandbox needs to
            // hand a newly minted bookmark to an already-running embedded engine.
            FolderAccessManager.shared.engineAccessService =
                SandboxAccessService(ficheroClient: self.ficheroClient)
            #endif
            self.documentService = DocumentService(ficheroClient: self.ficheroClient)
            self.storageService = storageService ?? StorageService(ficheroClient: self.ficheroClient)
            self.providerService = providerService ?? ProviderAPIService(ficheroClient: self.ficheroClient)
            self.modelService = modelService ?? ModelService(ficheroClient: self.ficheroClient)
            self.artifactService = ArtifactService(ficheroClient: self.ficheroClient)
            self.entityService = EntityService(ficheroClient: self.ficheroClient)
            self.kgCurationService = KGCurationService(ficheroClient: self.ficheroClient)
            self.activityService = ActivityService(ficheroClient: self.ficheroClient)
            self.batchService = BatchService(ficheroClient: self.ficheroClient)
            self.automationService = AutomationAPIService(ficheroClient: self.ficheroClient)
            self.chainService = ChainService(apiClient: self.apiClient)
            self.researchService = ResearchService(ficheroClient: self.ficheroClient)
            self.noteService = NoteService(ficheroClient: self.ficheroClient)
            self.annotationService = AnnotationService(ficheroClient: self.ficheroClient)
            self.actionsService = ActionsService(client: self.ficheroClient)

            // Start accessing security-scoped resource if requested
            if startAccessing {
                self.startAccessingSecurityScope()
            }
        }

        /// Start accessing the security-scoped resource.
        ///
        /// Check-and-set happen inside ONE `withLock`: as two separate steps a
        /// concurrent start could double-acquire, and macOS reference-counts
        /// these — the extra acquire is never released (#4216).
        nonisolated func startAccessingSecurityScope() {
            securityScopeState.withLock { isAccessing in
                guard !isAccessing else { return }
                if url.startAccessingSecurityScopedResource() {
                    isAccessing = true
                }
            }
        }

        /// Stop accessing the security-scoped resource. Same atomicity argument
        /// inverted: two racing stops could each pass the guard and release a
        /// scope held once, dropping file access the app still needs.
        nonisolated func stopAccessingSecurityScope() {
            securityScopeState.withLock { isAccessing in
                guard isAccessing else { return }
                url.stopAccessingSecurityScopedResource()
                isAccessing = false
            }
        }

        deinit {
            stopAccessingSecurityScope()
        }

        func reconfigureBackendHost() {
            // Every library is currently created on the app-default host, so it
            // follows the Settings engine-host switch (unchanged behavior). When
            // a library is pinned to a SPECIFIC remote host (#2866 follow-up),
            // this will branch on that; today there are no such libraries.
            ficheroClient.reconfigure(baseURL: EngineConfig.host)
            // Also rebind the legacy APIClient's separate FicheroClient (#2349):
            // DocumentStore + ChainService are built on `apiClient`, not the shared
            // `ficheroClient`, so without this they kept the old (localhost) host
            // after pairing while every generated service had already rebound.
            apiClient.reconfigure(baseURL: EngineConfig.host)
            storageService.clearAll()
        }
    }

    private init() {
        // Always load Global library on startup
        LaunchProfile.milestone("LibraryManager.shared init start")
        loadGlobalLibrary()
        LaunchProfile.milestone("LibraryManager.shared init done")
    }

    /// Load or create the Global library
    /// Global library is stored at ~/Library/Application Support/Fichero/global.fichero
    /// (the single canonical data dir, matching the engine's paths.server_state_dir;
    /// the legacy app.fichero.fichero/ location is migrated by the engine — #1526).
    private func loadGlobalLibrary() {
        // Under XCUITest the harness redirects Application Support to a
        // disposable temp dir (#1230) so smoke tests never touch the real
        // global.fichero. Outside UI tests this is the standard location.
        let appSupport = uiTestSupportDirectory()
            ?? hostAccessibleApplicationSupportDirectory()
        let globalURL = appSupport
            .appendingPathComponent("Fichero")
            .appendingPathComponent("global.fichero")

        // Check if Global library already exists
        if openLibraries.contains(where: { $0.id == Self.globalLibraryId }) {
            libraryManagerLogger.info("Global library already loaded")
            return
        }

        // Package structure (mkdir + Info.plist) is created lazily in
        // loadLibraryDataIfNeeded once the backend is ready — NOT here. This runs
        // inside LibraryManager.shared's init during App construction, before the
        // first frame, and synchronous disk I/O on that path delays launch (#3974).

        // Load or create Global library document
        let document = FicheroDocument()

        // Create Local library reference with fixed ID
        // Note: apiClient.currentLibraryPath is set in LibraryReference.init()
        let library = LibraryReference(
            url: globalURL,
            document: document,
            displayName: "Local",
            id: Self.globalLibraryId,
            startAccessing: false  // No security-scoped access needed for app support folder
        )

        // Always insert Global at the beginning
        openLibraries.insert(library, at: 0)

        libraryManagerLogger.info("Loaded Global library at: \(globalURL.path)")

        scheduleLoadWhenBackendReady(for: library)
    }

    private func hostAccessibleApplicationSupportDirectory() -> URL {
        #if targetEnvironment(simulator) && !os(macOS)
        if EngineConfig.engineIsLocal {
            if let hostHome = ProcessInfo.processInfo.environment["SIMULATOR_HOST_HOME"],
               !hostHome.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return URL(fileURLWithPath: hostHome)
                    .appendingPathComponent("Library/Application Support")
            }
        }
        #endif
        return FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
    }

    /// Get the Global library (always available)
    var globalLibrary: LibraryReference? {
        return openLibraries.first(where: { $0.id == Self.globalLibraryId })
    }

    /// The open library currently running a folder import, if any (#4203).
    ///
    /// Deliberately not "the selected library": the Activity window and the
    /// toolbar island are global, and an import running in a library the user
    /// has since navigated away from is exactly the one they need to see. One
    /// accessor so both surfaces resolve the same import.
    var importingLibrary: LibraryReference? {
        openLibraries.first { $0.importService.activeIngest != nil }
            // #4235: a task-less import is still an import. Staging the drop,
            // minting the folder grant and the create call all happen BEFORE
            // the engine has a task to report progress for, so keying only on
            // `activeIngest` left the island blank for that whole window — the
            // user drops a folder and the app looks like it did not notice.
            // `isImporting` is set at the top of the drop path, so it covers
            // exactly the gap `activeIngest` cannot.
            ?? openLibraries.first { $0.importService.isImporting }
    }
}

enum LibraryError: Error {
    case libraryNotFound
    case saveFailed
    case loadFailed
}
