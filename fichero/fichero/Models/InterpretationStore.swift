import FicheroAPIClient
import Foundation
import Observation
import OSLog

/// Observable domain store for a document's hermeneutic interpretations (#2009).
///
/// Document-scoped consumer of the generic change-stream substrate
/// (`ObservableDomainStore`). Owns the interpretations (hermeneutic statements)
/// the inspector's `DocumentInterpretationsSection` renders. An
/// `interpretation.*` event from any window (chat, another window, this one)
/// refreshes the affected scope in place, so a created/edited interpretation
/// shows up live everywhere.
///
/// **Scoping:** interpretations are document-scoped, so the backend
/// `interpretation.*` events (#2008) carry `document_ids`. A document-scoped
/// panel filters on `documentIds`; `ChangeEvent` has no `interpretation_ids`
/// field, so there is no cheap granular delete-by-id path — any
/// scope-matching event arms the debounced re-fetch (the same shape
/// `CitationStore`'s `inbound` collection relies on).
///
/// Wraps the EXISTING `EntityServiceGenerated.listDocumentInterpretations`
/// transport unchanged (iterate-never-replace): the same call the panel made
/// directly, now owned by the store so every window stays in sync.
@MainActor
@Observable
final class InterpretationStore: ObservableDomainStore {
    // ─── Published domain state (views read these directly) ───
    private(set) var items: [Components.Schemas.Interpretation] = []
    private(set) var frameworks: [Components.Schemas.InterpretiveFramework] = []
    private(set) var isLoading = false
    private(set) var isLoadingFrameworks = false
    private(set) var loadError: String?
    private(set) var frameworksError: String?

    /// The document whose interpretations are currently held.
    private(set) var currentDocumentId: String?

    // ─── Transport: the EXISTING generated wrapper, unchanged ───
    private let entityService: EntityServiceGenerated
    private let log = Logger(subsystem: "app.fichero.fichero", category: "InterpretationStore")

    let reloadDebouncer = ReloadDebouncer()

    init(entityService: EntityServiceGenerated) {
        self.entityService = entityService
    }

    // MARK: - Scope + load

    /// Point the store at `documentId` and load its interpretations. Idempotent
    /// against an already-populated identical scope unless `force` is set.
    func setScope(documentId: String, force: Bool = false) async {
        if !force, currentDocumentId == documentId, !items.isEmpty {
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
            items = try await entityService.listDocumentInterpretations(documentId: documentId)
        } catch is CancellationError {
            // Superseded by a newer document selection — keep current state.
        } catch {
            loadError = error.localizedDescription
            items = []
            log.error(
                "Interpretations fetch failed for \(documentId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
        }
    }

    func loadFrameworks() async {
        guard frameworks.isEmpty else { return }
        isLoadingFrameworks = true
        frameworksError = nil
        defer { isLoadingFrameworks = false }
        do {
            frameworks = try await entityService.listFrameworks()
        } catch is CancellationError {
            // Superseded by closing the interpretation form.
        } catch {
            frameworksError = error.localizedDescription
        }
    }

    @discardableResult
    func create(
        frameworkId: String,
        documentId: String,
        act: Components.Schemas.InterpretiveActType,
        text: String,
        confidence: Double
    ) async throws -> Components.Schemas.Interpretation {
        let created = try await entityService.createInterpretation(
            frameworkId: frameworkId,
            documentId: documentId,
            act: act,
            interpretationText: text,
            confidence: confidence
        )
        await reload()
        return created
    }

    @discardableResult
    func update(
        interpretationId: String,
        text: String,
        confidence: Double
    ) async throws -> Components.Schemas.Interpretation {
        let updated = try await entityService.updateInterpretation(
            interpretationId: interpretationId,
            interpretationText: text,
            confidence: confidence
        )
        await reload()
        return updated
    }

    // MARK: - ObservableDomainStore

    nonisolated var changeDomain: String { "interpretation" }

    /// Apply one `interpretation.*` change event. Interpretations carry no
    /// `interpretation_ids` on `ChangeEvent`, so there is no cheap granular
    /// delete; any event whose `document_ids` cover the current scope (or that
    /// is unscoped) arms the debounced re-fetch.
    func apply(_ event: ChangeEvent) {
        guard let scope = currentDocumentId else { return }
        switch event.verb {
        case "created", "updated", "deleted":
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
