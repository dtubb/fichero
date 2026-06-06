import Combine
import Foundation
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
class DocumentStore: ObservableObject {
    // MARK: - Private Properties

    let logger = Logger(subsystem: "app.fichero.fichero", category: "DocumentStore")

    /// Publisher for document changes.
    private let documentChanges = PassthroughSubject<DocumentChange, Error>()
    private var cancellables = Set<AnyCancellable>()
    // MARK: - Published State

    /// All collections (top-level documents)
    @Published var collections: [Document] = []

    /// Currently selected collection
    @Published var selectedCollection: Document?

    /// Documents in the current view (children of selected item)
    @Published var currentDocuments: [Document] = []

    /// Currently selected document for detail view
    @Published var selectedDocument: Document?

    /// Loading states
    @Published var isLoading = false
    @Published var isLoadingChildren = false

    /// Connection status
    @Published var isConnected = false

    /// Last error
    @Published var error: Error?

    /// Per-document workflow status overlay, keyed by document.id. Survives
    /// reloads of `currentDocuments` / `collections` / `childrenCache` so a
    /// failed-state (red X) icon stays visible after navigating away and back.
    /// Without this, Document.status was reset to .pending on every reload —
    /// success icons appeared persistent only because artifact existence
    /// derived completion separately, while errors silently disappeared (#791).
    /// In-memory only; clears on app restart.
    @Published var workflowStatusOverrides: [String: Status] = [:]

    /// Workspace documents (is_workspace == true) — the curated-items
    /// workspaces surfaced in the Research sidebar's Workspaces section (#1617).
    @Published var workspaces: [Document] = []

    /// File paths whose per-file fanout slot has finished (the `fileComplete`
    /// SSE event arrived) but whose enclosing workflow is still running
    /// reduce-phase nodes that further touch the page (extract_all, etc.).
    /// Held here so the sidebar/grid keep showing a spinner — flipping to
    /// the green checkmark happens only when the workflow's `complete`
    /// event fires and `flushPendingFanoutCompletions` runs (#948).
    var pendingFanoutCompletionPaths: Set<String> = []

    /// Publisher for document changes.
    var documentChangePublisher: AnyPublisher<DocumentChange, Error> {
        documentChanges.eraseToAnyPublisher()
    }

    // MARK: - Private

    let api: APIClient  // Internal access for LibraryImageView and other components

    /// Publish a document change event.
    func publish(_ change: DocumentChange) {
        documentChanges.send(change)
    }

    /// Cache of children by parent ID
    var childrenCache: [String: [Document]] = [:]

    // MARK: - Initialization

    /// Initialize with a per-window APIClient instance.
    /// This ensures operations in one window don't affect other windows.
    init(apiClient: APIClient) {
        self.api = apiClient
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

    // MARK: - Loading Collections

    /// Load all documents from the backend to build full tree.
    func loadCollections() async {
        isLoading = true
        error = nil

        do {
            logger.info("Loading all documents for tree building...")
            // Load ALL documents so SidebarItemBuilder can construct full hierarchy from parent_id
            // No limit - load everything for complete tree structure
            let query = ["offset": "0"]
            let response: DocumentListResponse = try await api.get("/documents", query: query)
            collections = applyStatusOverrides(response.items)
            isConnected = true
            logger.info("Loaded \(self.collections.count) documents total")

            let rootCount = self.collections.filter { $0.parentId == nil }.count
            let childCount = self.collections.count - rootCount
            logger.info("  - \(rootCount) root items, \(childCount) nested items")

            // Publish change
            publish(.collectionsUpdated(collections))

            // Auto-select first root collection if none selected
            if selectedCollection == nil, let first = collections.first(where: { $0.parentId == nil }) {
                await selectCollection(first)
            }
        } catch {
            logger.error("ERROR loading documents: \(String(describing: error))")
            self.error = error
            isConnected = false
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

    /// Load children of a document.
    func loadChildren(of document: Document) async {
        isLoadingChildren = true

        let libraryPath = self.api.currentLibraryPath ?? "nil"
        logger.info("loadChildren called for document: \(document.id), library path: \(libraryPath)")

        do {
            let response: DocumentListResponse = try await self.api.get("/documents/\(document.id)/children")
            let children = applyStatusOverrides(response.items)
            self.childrenCache[document.id] = children
            self.currentDocuments = children
            logger.info("loadChildren succeeded, got \(children.count) children")
        } catch {
            logger.error("loadChildren failed: \(error.localizedDescription)")
            self.error = error
            self.currentDocuments = []
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
            let response: DocumentListResponse = try await api.get("/documents/\(parentId)/children")
            let fresh = response.items
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
            let response: DocumentListResponse = try await api.get("/documents/\(documentId)/children")
            let fresh = response.items
            childrenCache[documentId] = applyStatusOverrides(fresh)
            return childrenCache[documentId] ?? []
        } catch {
            // Surface the failure: an empty result here is otherwise
            // indistinguishable from a genuinely empty folder, leaving the
            // user with no children and no explanation (#1718).
            logger.error(
                "children(of:) failed to load children for \(documentId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
            return []
        }
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
