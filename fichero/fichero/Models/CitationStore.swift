import FicheroAPIClient
import Foundation
import Observation
import OSLog

/// Observable domain store for a document's citation graph (#1998).
///
/// Document-scoped consumer of the generic change-stream substrate
/// (`ObservableDomainStore`). Owns the inbound / outbound citations and the
/// citation→claim usage rows the inspector's `CitationGraphPanel` renders. A
/// `citation.*` event from any window refreshes the affected scope in place.
///
/// Wraps the EXISTING `EntityService` transport unchanged
/// (iterate-never-replace): the same `inbound/outboundCitations` + `citationUsages`
/// calls the panel used directly, now owned by the store so every window stays
/// in sync.
@MainActor
@Observable
final class CitationStore: ObservableDomainStore {
    // ─── Published domain state (views read these directly) ───
    private(set) var inbound: [Components.Schemas.DocumentCitation] = []
    private(set) var outbound: [Components.Schemas.DocumentCitation] = []
    private(set) var usages: [EntityCitationUsage] = []
    private(set) var isLoading = false
    private(set) var loadError: String?

    /// The document whose citations are currently held.
    private(set) var currentDocumentId: String?

    // ─── Transport: the EXISTING generated wrapper, unchanged ───
    private let entityService: EntityService
    private let log = Logger(subsystem: "app.fichero.fichero", category: "CitationStore")

    let reloadDebouncer = ReloadDebouncer()

    init(entityService: EntityService) {
        self.entityService = entityService
    }

    // MARK: - Scope + load

    /// Point the store at `documentId` and load its citation graph. Idempotent
    /// against an already-populated identical scope unless `force` is set.
    func setScope(documentId: String, force: Bool = false) async {
        if !force, currentDocumentId == documentId, !(inbound.isEmpty && outbound.isEmpty) {
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
            async let inboundTask = entityService.inboundCitations(forDocumentId: documentId)
            async let outboundTask = entityService.outboundCitations(forDocumentId: documentId)
            async let usageTask = entityService.citationUsages(sourceDocumentId: documentId)
            let (inb, out, use) = try await (inboundTask, outboundTask, usageTask)
            inbound = inb
            outbound = out
            usages = use
        } catch is CancellationError {
            // Superseded by a newer document selection — keep current state.
        } catch {
            loadError = "Couldn't load citations."
            inbound = []
            outbound = []
            usages = []
            log.error(
                "Citations fetch failed for \(documentId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
        }
    }

    // MARK: - Export

    /// BibTeX for the current document scope, for copy / share / drag-out to a
    /// citation manager (#3451). Empty string when nothing is scoped.
    func exportBibTeX() async throws -> String {
        guard let documentId = currentDocumentId else { return "" }
        return try await entityService.exportCitationsBibtex(documentIds: [documentId])
    }

    /// Persisted citations eligible to associate with `targetDocumentId`.
    static func associationIDs(
        from payloads: [CitationDragID],
        targetDocumentId: String
    ) -> [String] {
        Array(Set(payloads.compactMap { payload in
            guard !payload.id.isEmpty,
                  payload.sourceDocumentId != targetDocumentId,
                  payload.targetDocumentId != targetDocumentId else { return nil }
            return payload.id
        })).sorted()
    }

    /// Associate dropped citations through the existing audited patch action.
    func associate(citationIds: [String], with targetDocumentId: String) async {
        do {
            for citationId in citationIds {
                _ = try await entityService.patchCitation(
                    citationId,
                    targetDocumentId: targetDocumentId
                )
            }
            await reload()
        } catch {
            loadError = "Couldn't associate citation."
            log.error("Citation association failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    // MARK: - ObservableDomainStore

    nonisolated var changeDomain: String { "citation" }

    /// Apply one `citation.*` change event. A delete with known `citation_ids`
    /// is a cheap in-place removal (the beachball rule keeps it synchronous);
    /// creates/updates touching the current scope arm the debounced re-fetch.
    /// `inbound` (citations from *other* documents) can't be scoped by this
    /// document's `document_ids`, so it relies on reconnect `resync()` for drift.
    func apply(_ event: ChangeEvent) {
        guard let scope = currentDocumentId else { return }
        switch event.verb {
        case "deleted":
            let removed = Set(event.citationIds)
            if !removed.isEmpty {
                inbound.removeAll { $0.id.map(removed.contains) ?? false }
                outbound.removeAll { $0.id.map(removed.contains) ?? false }
                usages.removeAll { $0.citation.id.map(removed.contains) ?? false }
            } else if scopeMatches(event, scope) {
                scheduleReload()
            }
        case "created", "updated":
            if scopeMatches(event, scope) { scheduleReload() }
        default:
            break
        }
    }

    /// True when the event is unscoped or its `document_ids` cover our scope.
    private func scopeMatches(_ event: ChangeEvent, _ scope: String) -> Bool {
        let ids = Set(event.documentIds)
        return ids.isEmpty || ids.contains(scope)
    }
}
