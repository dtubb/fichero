import FicheroAPIClient
import Foundation
import Observation
import OSLog

/// Observable domain store for a document's artifacts (#1997).
///
/// Document-scoped consumer of the generic change-stream substrate
/// (`ObservableDomainStore`). A view sets the current document scope and reads
/// `items`; an `artifact.*` event from any window whose `document_ids` cover the
/// current scope refreshes the list in place — no manual reload. Mirrors
/// `DocumentStore+ChangeStream`'s structure, but artifact events carry only the
/// owning `document_ids` (not artifact ids), so every verb routes through the
/// debounced scope re-fetch rather than a per-row splice.
///
/// Wraps the EXISTING `ArtifactService` transport unchanged (the
/// iterate-never-replace rule): the store owns *when* to fetch; the service
/// still owns *how*.
@MainActor
@Observable
final class ArtifactStore: ObservableDomainStore {
    // ─── Published domain state (views read these directly) ───
    private(set) var items: [Artifact] = []
    private(set) var isLoading = false
    private(set) var loadError: String?

    /// The document whose artifacts are currently held. `nil` until a view
    /// calls `setScope`. The granular `apply(_:)` filters events against it.
    private(set) var currentDocumentId: String?

    /// Whether the current scope includes descendant (page-child) artifacts. A
    /// parent PDF's extractor workflows write per-page outputs to its page
    /// children, so the Content tab loads with this true; the Artifacts tab
    /// loads strict per-document (false). Part of the scope so `reload()` and the
    /// idempotence check honor it (#3186).
    private(set) var currentIncludeDescendants = false

    // ─── Transport: the EXISTING generated wrapper, unchanged ───
    private let artifactService: ArtifactService
    private let log = Logger(subsystem: "app.fichero.fichero", category: "ArtifactStore")

    /// One shared trailing-reload debouncer (the #1973 beachball fix), supplied
    /// to the `ObservableDomainStore` extension's `scheduleReload()`.
    let reloadDebouncer = ReloadDebouncer()

    init(artifactService: ArtifactService) {
        self.artifactService = artifactService
    }

    // MARK: - Scope + load (the store, not the view, owns fetching)

    /// The scope `items` were actually fetched for, set only on a SUCCESSFUL
    /// load (#4348). Distinct from `currentDocumentId`, which is the scope being
    /// *asked* for and is assigned before the await — the gap between the two is
    /// exactly where stale rows would be mislabelled as the new document's.
    private var loadedScope: String?

    /// Identity of a scope for staleness purposes. `includeDescendants` is part
    /// of it because the same document yields a different row set either way.
    private static func scopeKey(documentId: String, includeDescendants: Bool) -> String {
        "\(documentId)|\(includeDescendants)"
    }

    /// Point the store at `documentId` and load its artifacts. Idempotent: a
    /// repeated set of the same already-loaded scope is a no-op unless `force`
    /// is set (reload button / post-mutation refresh).
    func setScope(documentId: String, includeDescendants: Bool = false, force: Bool = false) async {
        // A virtual page cursor is a page that is NOT imported as a document —
        // it has no artifacts by definition. Asking the engine 404'd once per
        // swipe on unprocessed PDFs (2026-08-11 console churn).
        if Document.isVirtualPageCursorId(documentId) {
            items = []
            currentDocumentId = documentId
            currentIncludeDescendants = includeDescendants
            loadedScope = Self.scopeKey(documentId: documentId, includeDescendants: includeDescendants)
            loadError = nil
            return
        }
        let scope = Self.scopeKey(documentId: documentId, includeDescendants: includeDescendants)
        // Guards on the scope actually LOADED, not on `!items.isEmpty`. Now that
        // a failed fetch can leave rows in place, "non-empty" no longer means
        // "loaded" — a scope whose fetch failed would never be retried (#4348).
        if !force, loadedScope == scope { return }
        currentDocumentId = documentId
        currentIncludeDescendants = includeDescendants
        await reload()
    }

    /// Re-fetch the current document scope (reconnect resync / post-event).
    func reload() async {
        guard let documentId = currentDocumentId else { return }
        let scope = Self.scopeKey(
            documentId: documentId, includeDescendants: currentIncludeDescendants
        )
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            items = try await artifactService.getArtifacts(
                forDocumentId: documentId,
                forceRefresh: true,
                includeDescendants: currentIncludeDescendants
            )
            loadedScope = scope
            log.debug(
                "Loaded \(self.items.count, privacy: .public) artifacts for \(documentId, privacy: .public)"
            )
        } catch {
            switch StaleDataPolicy.onFailure(
                isCancellation: error.isCancellationError,
                loadedScope: loadedScope,
                requestedScope: scope
            ) {
            case .ignore:
                // Superseded by a newer document selection — keep current state.
                return
            case .keepStale:
                // The rows on screen are this document's, just not refreshed.
                // Showing them under the error banner is the honest report.
                break
            case .clear:
                items = []
                loadedScope = nil
            }
            loadError = "Couldn't load artifacts: \(error.localizedDescription)"
            log.error(
                "Failed to load artifacts for \(documentId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
        }
    }

    /// Delete the given artifacts, then reconcile the scope against the server
    /// (#2519). The store — not the view — owns the endpoint (observable-data-
    /// layer rule). Best-effort batch: a failure on one id is logged and the
    /// rest still attempt, then a single `reload()` reflects the server truth so
    /// the list updates in place. Each artifact is deleted under its OWN
    /// `documentId` (a long doc's artifacts hang off page children, not the
    /// scope doc). Returns the number that failed to delete.
    @discardableResult
    func delete(_ artifacts: [Artifact]) async -> Int {
        guard !artifacts.isEmpty else { return 0 }
        var failed = 0
        for artifact in artifacts {
            do {
                try await artifactService.deleteArtifact(
                    id: artifact.id,
                    documentId: artifact.documentId
                )
            } catch {
                failed += 1
                log.error(
                    "Failed to delete artifact \(artifact.id, privacy: .public): \(error.localizedDescription, privacy: .public)"
                )
            }
        }
        await reload()
        return failed
    }

    /// Update an artifact's content, then splice the fresh value into `items` in
    /// place — stable identity, no wholesale reload (the no-wholesale-list-re-
    /// render rule). The store, not the view, owns the endpoint (#3186 / #1863).
    /// Returns the updated artifact.
    @discardableResult
    func update(id: String, documentId: String, content: String) async throws -> Artifact {
        let updated = try await artifactService.updateArtifact(
            id: id,
            documentId: documentId,
            content: content
        )
        if let index = items.firstIndex(where: { $0.id == updated.id }) {
            items[index] = updated
        }
        return updated
    }

    // MARK: - ObservableDomainStore

    nonisolated var changeDomain: String { "artifact" }

    /// Apply one `artifact.*` change event. Artifact events carry the owning
    /// `document_ids` only (not the artifact id), so there's no cheap per-row
    /// splice: when the event touches the current scope (or is unscoped) arm the
    /// debounced scope re-fetch; a workflow event storm coalesces into a single
    /// trailing reload (#1973).
    func apply(_ event: ChangeEvent) {
        guard let scope = currentDocumentId else { return }
        let ids = Set(event.documentIds)
        guard ids.isEmpty || ids.contains(scope) else { return }
        switch event.verb {
        case "created", "updated", "deleted":
            scheduleReload()
        default:
            break
        }
    }
}
