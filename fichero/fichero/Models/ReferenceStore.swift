import FicheroAPIClient
import Foundation
import Observation
import OSLog

/// Observable domain store for a document's extracted bibliography (#1999).
///
/// Consumer of the generic change-stream substrate (`ObservableDomainStore`)
/// backing the inspector's `DocumentBibliographyPanel`. Owns the document's own
/// reference (`selfRef`) plus the scholarly references it cites, loaded from
/// `GET /api/documents/{id}/citations`.
///
/// **Scoping caveat:** references are *library-wide* bibliography rows, and the
/// backend `reference.*` events carry only `reference_ids` — no `document_ids`.
/// A document-scoped panel therefore can't tell from the event alone whether an
/// edited reference appears in *this* document's bibliography, so any
/// `reference.*` event refreshes the current scope (debounced). A delete with
/// known `reference_ids` is removed in place first.
///
/// Wraps the EXISTING `EntityService.listDocumentCitations` transport
/// unchanged (iterate-never-replace).
@MainActor
@Observable
final class ReferenceStore: ObservableDomainStore {
    // ─── Published domain state (views read these directly) ───
    private(set) var references: [Components.Schemas.Reference] = []
    private(set) var selfRef: Components.Schemas.Reference?
    private(set) var isLoading = false
    private(set) var loadError: String?

    /// The document whose bibliography is currently held.
    private(set) var currentDocumentId: String?

    // ─── Transport: the EXISTING generated wrapper, unchanged ───
    private let entityService: EntityService
    private let log = Logger(subsystem: "app.fichero.fichero", category: "ReferenceStore")

    let reloadDebouncer = ReloadDebouncer()

    init(entityService: EntityService) {
        self.entityService = entityService
    }

    // MARK: - Scope + load

    /// Point the store at `documentId` and load its bibliography. Idempotent
    /// against an already-populated identical scope unless `force` is set.
    func setScope(documentId: String, force: Bool = false) async {
        if !force, currentDocumentId == documentId, !(references.isEmpty && selfRef == nil) {
            return
        }
        currentDocumentId = documentId
        await reload()
    }

    /// Re-fetch the current document scope (reconnect resync / post-event).
    func reload() async {
        guard let documentId = currentDocumentId else { return }
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            let resp = try await entityService.listDocumentCitations(documentId: documentId)
            selfRef = resp._self
            references = resp.references
        } catch is CancellationError {
            // Superseded by a newer document selection — keep current state.
        } catch {
            loadError = error.localizedDescription
            log.error(
                "Bibliography fetch failed for \(documentId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
        }
    }

    // MARK: - Mutations (#3258)

    /// Delete a bibliography reference. The backend delete is undoable and
    /// 409-guarded; the `reference.deleted` change event removes the row via
    /// `apply`, but we also drop it locally so the UI updates immediately even
    /// before the event round-trips. Throws on transport/permission failure so
    /// the caller can surface it.
    func deleteReference(_ referenceId: String) async throws {
        try await entityService.deleteReference(referenceId)
        references.removeAll { $0.id == referenceId }
        if selfRef?.id == referenceId { selfRef = nil }
    }

    /// Run the bibliography extractor over the current document, then re-fetch.
    /// The extractor writes `reference.*` rows; `reference.created` events also
    /// refresh the scope via `apply`, so this is a belt-and-suspenders reload.
    func runExtractor() async throws {
        guard let documentId = currentDocumentId else { return }
        _ = try await entityService.runBibliographyExtractor(forDocumentId: documentId)
        await reload()
    }

    /// Patch a reference's metadata (undoable, 409-guarded server-side). Reloads
    /// to pick up server-normalized values; the `reference.updated` event also
    /// refreshes the scope.
    func patchReference(_ referenceId: String, patch: [String: Any]) async throws {
        _ = try await entityService.patchReference(referenceId, patch: patch)
        await reload()
    }

    /// Resolve a reference's metadata from its DOI/ISBN against the external
    /// bibliographic sources (CrossRef/etc.). The backend persists the resolved
    /// fields onto the document's bibliography; we reload to show them.
    func resolveReference(doi: String?, isbn: String?) async throws {
        guard let documentId = currentDocumentId else { return }
        _ = try await entityService.resolveBibliography(doi: doi, isbn: isbn, documentId: documentId)
        await reload()
    }

    // MARK: - ObservableDomainStore

    nonisolated var changeDomain: String { "reference" }

    /// Apply one `reference.*` change event. A delete with known `reference_ids`
    /// is a cheap in-place removal; any other reference event refreshes the
    /// current scope via the debouncer (events carry no `document_ids`, so we
    /// can't cheaply tell whether the edited reference is in this bibliography).
    func apply(_ event: ChangeEvent) {
        guard currentDocumentId != nil else { return }
        switch event.verb {
        case "deleted":
            let removed = Set(event.referenceIds)
            if !removed.isEmpty {
                references.removeAll { $0.id.map(removed.contains) ?? false }
                if let selfId = selfRef?.id, removed.contains(selfId) { selfRef = nil }
            } else {
                scheduleReload()
            }
        case "created", "updated":
            scheduleReload()
        default:
            break
        }
    }
}
