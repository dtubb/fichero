import Combine
import FicheroAPIClient
import Foundation
import Observation
import OSLog
import SwiftUI

let documentStoreLogger = Logger(subsystem: "app.fichero.fichero", category: "DocumentStore")

/// Document change types for reactive updates.
enum DocumentChange {
    case collectionsUpdated([Document])
    case collectionSelected(Document)
    case documentsUpdated([Document])
    case documentDeleted(Document)
    case documentCreated(Document)
}

/// Main state container for documents.
///
/// This is the bridge between the backend API and SwiftUI views.
/// It manages loading state, caching, and provides reactive updates.
@MainActor
@Observable
final class DocumentStore {
    // MARK: - Private Properties

    let logger = Logger(subsystem: "app.fichero.fichero", category: "DocumentStore")

    /// Publisher for document changes.
    @ObservationIgnored
    private let documentChanges = PassthroughSubject<DocumentChange, Error>()
    @ObservationIgnored
    private var cancellables = Set<AnyCancellable>()
    // MARK: - Observable State

    /// All collections (top-level documents)
    var collections: [Document] = [] {
        didSet { processingIndexDirty = true }
    }

    /// Currently selected collection
    var selectedCollection: Document?

    /// Documents in the current view (children of selected item)
    var currentDocuments: [Document] = [] {
        didSet {
            revision += 1
            processingIndexDirty = true
        }
    }

    /// Cheap O(1) change token for views that only need to know the visible
    /// document set changed, not diff the whole array. Also bumped by the
    /// change-stream splice when a batch lands ONLY in `childrenCache` /
    /// `collections` (#4318): those containers are `@ObservationIgnored`, so
    /// without the bump a workflow's mid-run page_content write would never
    /// re-render the content pane. Internal(set) so the splice extension
    /// (`DocumentStore+ChangeStream`) can bump it.
    var revision: Int = 0

    /// Document ids touched by the most recent in-place splice / removal,
    /// paired with `revision`. Views that care about ONE document (the
    /// inspector's page-content panel) read this inside their
    /// `.onChange(of: revision)` handler so a library-wide event storm does
    /// not trigger per-page refetches for unrelated rows (#4318).
    @ObservationIgnored
    var lastChangedDocumentIds: Set<String> = []

    /// Currently selected document for detail view
    var selectedDocument: Document?

    /// Loading states
    var isLoading = false
    var isLoadingChildren = false

    /// Connection status
    var isConnected = false

    /// Last error
    var error: Error?

    /// Per-document workflow status overlay, keyed by document.id. Survives
    /// reloads of `currentDocuments` / `collections` / `childrenCache` so a
    /// failed-state (red X) icon stays visible after navigating away and back.
    /// Without this, Document.status was reset to .pending on every reload —
    /// success icons appeared persistent only because artifact existence
    /// derived completion separately, while errors silently disappeared (#791).
    /// In-memory only; clears on app restart.
    var workflowStatusOverrides: [String: Status] = [:] {
        didSet { processingIndexDirty = true }
    }

    /// Workspace documents (is_workspace == true) — the curated-items
    /// workspaces surfaced in the Research sidebar's Workspaces section (#1617).
    var workspaces: [Document] = []

    /// File/page identities whose per-file fanout slot has finished (the
    /// `fileComplete` SSE event arrived) but whose enclosing workflow is still
    /// running reduce-phase nodes that further touch the page (extract_all,
    /// etc.). Keyed by the stable page/document identity from the workflow
    /// stream so sibling PDF pages that share one parent path do not collapse
    /// onto one pending slot (#2634).
    @ObservationIgnored
    var pendingFanoutCompletions: [String: FileProgressIdentity] = [:]

    /// Identities currently marked `.processing` by a live workflow stream,
    /// keyed by stable identity. Terminal paths use this to clear residual
    /// spinners for documents whose `fileComplete`/`fileError` never arrived —
    /// a stopped run, or an SSE stream that died mid-flight (#4346/#4349) —
    /// so no document keeps a permanent spinner. In-memory only.
    @ObservationIgnored
    var activeProcessingIdentities: [String: FileProgressIdentity] = [:]

    /// Publisher for document changes.
    var documentChangePublisher: AnyPublisher<DocumentChange, Error> {
        documentChanges.eraseToAnyPublisher()
    }

    // MARK: - Private

    let api: APIClient  // Internal access for LibraryImageView and other components

    /// Typed documents client (#3030). Shares `api`'s FicheroClient, throws on
    /// non-`.ok`, and maps generated schemas → local `Document` via its own
    /// converters. Store methods route documents-domain reads/writes through
    /// this instead of the hand-rolled `api.get/post/delete`.
    @ObservationIgnored
    let documentService: DocumentService

    /// Typed locations client (#3577). Shares `api`'s FicheroClient. Resolves a
    /// navigation `Location` (page-child → parent, page range) through the one
    /// engine route so the UI doesn't re-implement that resolution.
    @ObservationIgnored
    let locationService: LocationService

    /// Publish a document change event.
    func publish(_ change: DocumentChange) {
        documentChanges.send(change)
    }

    /// Cache of children by parent ID
    @ObservationIgnored
    var childrenCache: [String: [Document]] = [:] {
        didSet { processingIndexDirty = true }
    }

    // MARK: - Processing index (2026-08-09)
    //
    // The stall sampler attributed 165-188ms main-thread stalls to
    // `isDocumentBusy`: it linearly scanned currentDocuments + collections +
    // EVERY childrenCache array, per row, per render — O(total documents)
    // multiplied by visible rows. The four didSets above mark the index dirty
    // and `processingDocumentIds` rebuilds it once per mutation, so the per-
    // row question is one set-membership test. @ObservationIgnored: this is a
    // derived cache; observers track the source arrays, never the index.
    @ObservationIgnored
    var processingIndexDirty = true
    @ObservationIgnored
    private var processingIndex: Set<String> = []

    /// Every document id whose status reads `.processing` in any store the
    /// spinners consult (overrides win by construction — they are unioned in).
    var processingDocumentIds: Set<String> {
        if processingIndexDirty {
            var ids = Set(workflowStatusOverrides.filter { $0.value == .processing }.keys)
            for doc in currentDocuments where doc.status == .processing { ids.insert(doc.id) }
            for doc in collections where doc.status == .processing { ids.insert(doc.id) }
            for kids in childrenCache.values {
                for kid in kids where kid.status == .processing { ids.insert(kid.id) }
            }
            processingIndex = ids
            processingIndexDirty = false
        }
        return processingIndex
    }

    // MARK: - Change-stream substrate (#1995 / #1996)

    /// Shared 300ms trailing-reload coalescer (the #1973 beachball fix). Used by
    /// the `ObservableDomainStore` conformance below to fold a burst of
    /// `document.*` events into a single granular fetch+splice.
    @ObservationIgnored
    let reloadDebouncer = ReloadDebouncer()

    /// Document ids touched by `document.updated`/`document.created` events,
    /// accumulated across a burst and flushed once by the debouncer. The flush
    /// fetches and splices ONLY these rows — the library table is never
    /// wholesale-reloaded on a single event.
    @ObservationIgnored
    var pendingPatchIds: Set<String> = []

    /// In-flight page-content saves, keyed by document id. These are
    /// STORE-OWNED unstructured tasks so a view re-render / blur that cancels
    /// the editor's own task can't abort the PUT mid-flight (NSURLError -999,
    /// #2466). See `savePageContent(documentId:perform:)` in
    /// `DocumentStore+Helpers`. Internal (not private) so that extension can
    /// reach it.
    @ObservationIgnored
    var pageContentSaveTasks: [String: Task<String?, Never>] = [:]

    /// Document ids this device just wrote, with the time of the write. Used to
    /// drop the change-stream ECHO of our own save so a self-echoed
    /// `document.updated` doesn't re-fetch + re-splice the row (which changes the
    /// inspector's `document` identity and forces the page editor to rebuild —
    /// width / cursor / scroll reset, #2478). A genuine update from ANOTHER
    /// device is keyed differently in time and still applies in place (#2479).
    /// Entries self-expire via `ownWriteEchoWindow` so a marker can never
    /// suppress a later, legitimate remote edit to the same document.
    @ObservationIgnored
    var recentOwnWrites: [String: Date] = [:]

    /// How long an own-write marker suppresses its echo. The echo arrives over
    /// SSE within a few hundred ms of the PUT; a generous window absorbs jitter
    /// while staying far below the cadence of human cross-device edits.
    @ObservationIgnored
    let ownWriteEchoWindow: TimeInterval = 5

    /// Flush hook the active page-content editor registers (#2476). An external
    /// navigation (image prev/next, inspector tab switch) calls
    /// `flushActivePageEdit()` BEFORE changing the focused document so the
    /// in-flight edit is persisted via the store-owned save instead of being
    /// discarded when the editor reseeds to the new document. Nil when no
    /// editable page-content editor is focused.
    @ObservationIgnored
    var activePageEditFlush: (@MainActor () async -> Void)?

    // MARK: - Initialization

    /// Initialize with a per-window APIClient instance.
    /// This ensures operations in one window don't affect other windows.
    init(apiClient: APIClient) {
        self.api = apiClient
        self.documentService = DocumentService(ficheroClient: apiClient.client)
        self.locationService = LocationService(ficheroClient: apiClient.client)
    }

    // MARK: - Connection

    /// Check if the backend is available.
    func checkConnection() async {
        do {
            _ = try await api.healthCheck()
            isConnected = true
        } catch {
            isConnected = false
        }
    }

    // MARK: - Transient-failure retry (#3972)
    /// Transient engine-unreachable/transport failures may retry; auth/TLS/permission are definitive. Pure seam (#3972).
    static func isRetriableLoadFailure(_ error: Error) -> Bool {
        switch AccessError.classify(error) {
        case .engineUnreachable, .transport: return true
        default: return false
        }
    }
    /// Retry a fetch with short backoff on a transient failure so one blip doesn't trip the outage pane while 200s still flow (#3972).
    func fetchWithRetry<T>(_ operation: () async throws -> T) async throws -> T {
        var attempt = 0
        while true {
            do { return try await operation() } catch {
                attempt += 1
                guard attempt <= 3, Self.isRetriableLoadFailure(error) else { throw error }
                try await Task.sleep(for: .seconds(0.3 * Double(attempt)))
            }
        }
    }
    // MARK: - Loading Collections

    var sidebarDocuments: [Document] {
        var seen = Set<String>()
        return (collections + childrenCache.values.flatMap { $0 }).filter { seen.insert($0.id).inserted }
    }

    /// The ordering currently requested from the listing routes (#3322).
    ///
    /// nil — the overwhelmingly common case — means the stored sibling order,
    /// which is what every client-ordered sort field wants. Only
    /// `document_date` sets this, because only its ordering lives in the
    /// engine.
    private(set) var listingSort: ListingSort?

    /// Point the store at a new server ordering and reload if the request
    /// actually changed. Returns whether a refetch happened.
    ///
    /// The refetch is conditional rather than unconditional on purpose: sorting
    /// by Name and by Type are both free today, and making them round-trip so
    /// that Date does not look special would spend a request on every sort
    /// change to buy nothing. `ListingSort.requiresRefetch(from:to:)` is where
    /// that decision lives.
    @discardableResult
    func setListingSort(_ sort: ListingSort?) async -> Bool {
        guard ListingSort.requiresRefetch(from: listingSort, to: sort) else { return false }
        listingSort = sort
        await refresh()
        return true
    }

    /// Load root documents only; descendants are loaded lazily into `childrenCache`.
    func loadCollections() async {
        isLoading = true
        error = nil

        do {
            logger.info("Loading root documents for sidebar...")
            collections = applyStatusOverrides(try await fetchWithRetry { try await documentService.getRoots(sort: self.listingSort) })
            childrenCache.removeAll()
            isConnected = true
            logger.info("Loaded \(self.collections.count) root documents")

            // Publish change
            publish(.collectionsUpdated(collections))

            // Prefetch one level down so ROOT folders show their disclosure
            // chevrons before any click (#3355). Roots are already rendered from
            // `collections` above; this fills the chevrons in shortly after.
            await prefetchChildContainerChildren(of: collections)

            // Auto-select first root collection if none selected
            if selectedCollection == nil, let first = collections.first(where: { $0.parentId == nil }) {
                await selectCollection(first)
            }
        } catch {
            // Superseded/cancelled load is not a failure — skip logging and the
            // error/disconnected state, but still clear `isLoading` below.
            if !error.isCancellationError {
                logger.error("ERROR loading documents: \(String(describing: error))")
                self.error = error
                isConnected = false
            }
        }

        isLoading = false
    }

    /// Refresh collections AND the currently-selected collection's children
    /// from the backend. Reloading both is important because most callers
    /// ("I just imported a folder", "I just moved an item") want the grid
    /// view (`currentDocuments`) to reflect the change too — not just the
    /// sidebar tree (`collections`). Without the child reload, a drop into
    /// the currently-viewed folder shows the new folder in the sidebar but
    /// a stale empty grid (#576).
    func refresh() async {
        await loadCollections()
        if let selected = selectedCollection {
            await loadChildren(of: selected)
        }
    }

    // MARK: - Selection

    /// Select a collection and load its children.
    func selectCollection(_ collection: Document) async {
        selectedCollection = collection
        await loadChildren(of: collection)
    }

    // Sidebar child loading + one-level chevron prefetch (#3355) live in
    // DocumentStore+SidebarPrefetch.swift: loadSidebarChildren(of:),
    // cacheSidebarChildren(of:), prefetchChildContainerChildren(of:).

    /// Load children of a document.
    func loadChildren(of document: Document) async {
        isLoadingChildren = true
        // The async half of a sidebar click (#4228/#4235). Paired with the
        // synchronous `selectionCommit` bar, this is what tells a slow click
        // caused by main-thread work apart from one caused by the engine —
        // the distinction both of those issues asked for and could not make.
        InteractionProfile.begin(.contentDataLoad, detail: document.id)
        defer { InteractionProfile.end(.contentDataLoad, detail: document.id) }

        let libraryPath = self.api.currentLibraryPath ?? "nil"
        logger.info("loadChildren called for document: \(document.id), library path: \(libraryPath)")

        do {
            let children = applyStatusOverrides(
                try await fetchWithRetry {
                    try await documentService.getChildren(document.id, sort: self.listingSort)
                }
            )
            self.childrenCache[document.id] = children
            self.currentDocuments = children
            logger.info("loadChildren succeeded, got \(children.count) children")
        } catch {
            // Superseded/cancelled load is not a failure — keep current documents
            // and skip the error state, but still clear `isLoadingChildren` below.
            if !error.isCancellationError {
                logger.error("loadChildren failed: \(error.localizedDescription)")
                self.error = error
                self.currentDocuments = []
            }
        }

        self.isLoadingChildren = false
    }

    /// Refresh status fields ONLY for documents that are currently pending
    /// or processing — surgical update so the table doesn't flash every
    /// poll. Fetches the parent's children, then mutates `currentDocuments`
    /// in place: each row whose status flipped is replaced with the fresh
    /// version; everything else stays referentially identical.
    ///
    /// SwiftUI's Table diffs `currentDocuments` via Document.Equatable
    /// (Document is Codable+Hashable so == is auto-synthesized). Replacing
    /// only the changed rows means only those rows re-render — no
    /// whole-list flash. (#518 follow-up: 0.0.3's blanket poll was too
    /// aggressive on libraries with stuck-pending rows.)
    @MainActor
    func refreshPendingStatusesOnly(in parentId: String) async {
        // Snapshot pending row ids before the fetch — we only care about
        // these. If none, nothing to do.
        let pendingIds = Set(
            currentDocuments
                .filter { $0.status == .pending || $0.status == .processing }
                .map(\.id)
        )
        guard !pendingIds.isEmpty else { return }

        do {
            let fresh = try await documentService.getChildren(parentId)
            let freshById = Dictionary(uniqueKeysWithValues: fresh.map { ($0.id, $0) })

            // Walk currentDocuments. For each pending row whose status
            // changed in the fresh fetch, swap in the new value. Untouched
            // rows keep referential identity → no re-render.
            var didChange = false
            var updated = currentDocuments
            for index in updated.indices where pendingIds.contains(updated[index].id) {
                guard let freshDoc = freshById[updated[index].id] else { continue }
                if freshDoc.status != updated[index].status {
                    updated[index] = freshDoc
                    didChange = true
                }
            }
            if didChange {
                currentDocuments = updated
                // Also refresh the cached children copy so subsequent
                // navigations see the same statuses.
                childrenCache[parentId] = updated
            }
        } catch {
            // Swallow — poll-driven refresh; a transient failure shouldn't
            // surface as a user-facing error.
            logger.debug("refreshPendingStatusesOnly failed: \(error.localizedDescription)")
        }
    }

    /// Get cached children or load from backend.
    func children(of documentId: String) async -> [Document] {
        if let cached = childrenCache[documentId] {
            return cached
        }

        do {
            let fresh = try await documentService.getChildren(documentId)
            childrenCache[documentId] = applyStatusOverrides(fresh)
            return childrenCache[documentId] ?? []
        } catch {
            if error.isCancellationError { return [] }   // superseded — not a failure
            // Surface the failure: an empty result here is otherwise
            // indistinguishable from a genuinely empty folder, leaving the
            // user with no children and no explanation (#1718).
            logger.error(
                "children(of:) failed to load children for \(documentId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
            return []
        }
    }

    /// Batch per-item column metadata (#3758): entity / annotation / note /
    /// bbox counts for the given library items, feeding the library list and
    /// column-browser columns. Read-only. The store is the only endpoint
    /// accessor — views call this, never the service. Empty input
    /// short-circuits (the backend returns an empty set anyway); the backend
    /// caps a batch at 200 ids.
    func libraryItemColumns(
        itemIds: [String],
        includeDescendants: Bool = false
    ) async throws -> [Components.Schemas.LibraryItemColumnsRow] {
        guard !itemIds.isEmpty else { return [] }
        return try await documentService.libraryItemColumns(
            itemIds: itemIds,
            includeDescendants: includeDescendants
        )
    }
}

// MARK: - Preview Support

extension DocumentStore {
    /// Create a store with empty data for previews.
    static var preview: DocumentStore {
        let store = DocumentStore(apiClient: APIClient())
        store.collections = []
        return store
    }
}
