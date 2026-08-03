import FicheroAPIClient
import Foundation
import Observation
import OSLog

/// Observable domain store for knowledge claims (#1862, mirrors `EntityStore`).
///
/// The single endpoint accessor for the claim list a view renders. A view never
/// calls `EntityService` / `KGCurationService` claim methods
/// directly: it observes `claims` and dispatches the named actions below. Each
/// action performs the typed write and then refreshes the current scope — today
/// via an explicit reload, and via `apply(_:)` once the per-library change-stream
/// (#1863) emits `claim.*` events. Swapping reload for push is then a no-op at
/// every call site.
///
/// Claims are loaded against one of two scopes (whichever the view set last):
///   • a *document* scope (`loadClaims(forDocument:)`) — the inspector claims
///     list, backed by `/api/claims?source_document_id=…`;
///   • an *entity* scope (`loadClaims(forEntity:)`) — the entity-detail / related
///     claims panel, backed by `/api/claims?entity_id=…`.
///
/// Mirrors `WorkflowExecutionObserver`: typed event in → mutate observable state
/// → SwiftUI re-renders every bound view. One instance per library (registered on
/// `LibraryReference`), shared across that library's windows.
@MainActor
@Observable
final class ClaimStore: ObservableDomainStore {
    /// The scope the store is currently loaded against. Determines which query
    /// `reload()` re-issues and which change events the store reacts to.
    enum Scope: Equatable {
        case none
        case document(String)
        case entity(String)
    }

    // ─── Published domain state (views read these directly) ───
    private(set) var claims: [Components.Schemas.KnowledgeClaim] = []
    private(set) var isLoading = false
    private(set) var loadError: String?
    private(set) var scope: Scope = .none

    /// Monotonic counter bumped on every applied `claim.*` change event,
    /// regardless of scope. Views that keep their own (differently-scoped) claim
    /// load — e.g. the OntologyBrowser entity-detail panel's cross-document merge
    /// or the inspector's grouped KG read — observe this token and resync their
    /// own list when it changes. This is how those not-yet-store-backed surfaces
    /// retire their `.ficheroClaim*` NotificationCenter receivers (#1862) while
    /// keeping their bespoke load logic (iterate, never replace).
    private(set) var changeToken: Int = 0

    // ─── Transport: the EXISTING generated wrappers, unchanged ───
    private let entityService: EntityService
    private let kgCurationService: KGCurationService
    private let libraryPath: String
    private let log = Logger(subsystem: "app.fichero.fichero", category: "ClaimStore")

    init(
        entityService: EntityService,
        kgCurationService: KGCurationService,
        libraryPath: String
    ) {
        self.entityService = entityService
        self.kgCurationService = kgCurationService
        self.libraryPath = libraryPath
    }

    // MARK: - Load (the store, not the view, owns fetching)

    /// Load the claims for a document scope. Idempotent: re-loading the same
    /// already-populated scope is a no-op unless `force` is set.
    func loadClaims(
        forDocument documentId: String,
        includeDescendants: Bool = false,
        force: Bool = false
    ) async {
        if !force, scope == .document(documentId), !claims.isEmpty { return }
        await load(.document(documentId)) {
            try await self.entityService.listClaims(
                sourceDocumentId: documentId,
                includeDescendants: includeDescendants,
                limit: 500
            )
        }
    }

    /// Load the claims for an entity scope (entity-detail / related-claims panel).
    /// Idempotent against the same already-populated scope unless `force`.
    func loadClaims(
        forEntity entityId: String,
        force: Bool = false
    ) async {
        if !force, scope == .entity(entityId), !claims.isEmpty { return }
        await load(.entity(entityId)) {
            try await self.entityService.listClaims(
                entityId: entityId,
                limit: 500
            )
        }
    }

    private func load(
        _ newScope: Scope,
        _ fetch: @escaping () async throws -> [Components.Schemas.KnowledgeClaim]
    ) async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            let loaded = try await fetch()
            claims = loaded
            scope = newScope
            log.debug("Loaded \(loaded.count, privacy: .public) claims for scope")
        } catch {
            if error.isCancellationError {
                // Superseded by a newer selection — keep current state.
                return
            }
            loadError = "Couldn't load claims: \(error.localizedDescription)"
            claims = []
            scope = newScope
            log.error("Failed to load claims: \(error.localizedDescription, privacy: .public)")
        }
    }

    /// Re-fetch the current scope (post-mutation / reconnect resync).
    func reload() async {
        switch scope {
        case .none:
            return
        case .document(let documentId):
            await loadClaims(forDocument: documentId, force: true)
        case .entity(let entityId):
            await loadClaims(forEntity: entityId, force: true)
        }
    }

    // MARK: - Named actions (map 1:1 to the audited action layer, #1848)

    /// Set the curation state of `claimIds` and optionally write library-wide
    /// suppress rules, then refresh.
    func setCuration(
        claimIds: [String],
        to state: Components.Schemas.ClaimCurationState,
        suppressRules: [Components.Schemas.ClaimRuleCreateRequest] = []
    ) async throws {
        if !claimIds.isEmpty {
            _ = try await kgCurationService.batchSetClaimCurationState(
                claimIds: claimIds,
                curationState: state
            )
        }
        if !suppressRules.isEmpty {
            _ = try await kgCurationService.batchCreateClaimRules(suppressRules)
        }
        await reload()
    }

    /// Transition a single claim's lifecycle state (review-queue actions), then
    /// refresh.
    func transition(claimId: String, to state: String) async throws {
        _ = try await entityService.transitionClaim(claimId, state: state)
        await reload()
    }

    /// Batch-transition multiple claims' lifecycle state, then refresh.
    func batchTransition(claimIds: [String], to state: String) async throws {
        _ = try await entityService.batchTransitionClaims(claimIds: claimIds, state: state)
        await reload()
    }

    /// Edit a claim in place (`InlineClaimEditor`, #1135). Returns the updated
    /// claim so callers can update not-yet-migrated surfaces.
    ///
    /// **Updates the one row, never the list** (#4393, #4389). This used to end
    /// in `await reload()` like every other action here, and for a patch that is
    /// wrong twice over. The server has just handed back the authoritative
    /// updated claim, so re-fetching 500 rows asks a question already answered;
    /// and replacing the whole array re-renders every row, which loses scroll
    /// position and selection at the exact moment the user is mid-edit. An edit
    /// that makes the list jump reads as an edit that failed.
    ///
    /// A patch cannot move a claim out of the current scope — neither
    /// `source_document_id` nor `entity_ids` is patchable — so the row that was
    /// there is still there. When the id is genuinely absent (the claim was
    /// edited from a surface holding a different scope) this falls back to a
    /// reload rather than silently dropping the result on the floor.
    @discardableResult
    func patch(
        claimId: String,
        text: String? = nil,
        subjectCanonical: String? = nil,
        predicateVerb: String? = nil,
        objectPhrase: String? = nil,
        sourcePageLabel: String? = nil,
        curationState: Components.Schemas.ClaimCurationState? = nil,
        claimType: Components.Schemas.ClaimType? = nil,
        epistemicStatus: Components.Schemas.EpistemicStatus? = nil,
        confidence: Double? = nil,
        speakerName: String? = nil,
        speakerEntityId: String? = nil
    ) async throws -> Components.Schemas.KnowledgeClaim {
        let updated = try await entityService.patchClaim(
            claimId,
            text: text,
            subjectCanonical: subjectCanonical,
            predicateVerb: predicateVerb,
            objectPhrase: objectPhrase,
            sourcePageLabel: sourcePageLabel,
            curationState: curationState,
            claimType: claimType,
            epistemicStatus: epistemicStatus,
            confidence: confidence,
            speakerName: speakerName,
            speakerEntityId: speakerEntityId
        )
        if let index = claims.firstIndex(where: { $0.id == claimId }) {
            claims[index] = updated
        } else {
            await reload()
        }
        return updated
    }

    /// Merge `absorbedIds` into `survivorId`, then refresh. Returns the audit
    /// response so callers can offer unmerge.
    @discardableResult
    func merge(
        absorbedIds: [String],
        into survivorId: String
    ) async throws -> Components.Schemas.ClaimAuditResponse {
        let response = try await kgCurationService.mergeClaims(
            survivorId: survivorId,
            absorbedIds: absorbedIds
        )
        await reload()
        return response
    }

    /// Reverse a prior claim merge by its audit id, then refresh.
    @discardableResult
    func unmerge(auditId: String) async throws -> Components.Schemas.ClaimAuditResponse {
        let response = try await kgCurationService.unmergeClaims(auditId: auditId)
        await reload()
        return response
    }

    /// Link two claims (contradicts / supports / …), then refresh.
    @discardableResult
    func link(
        claimId: String,
        relatedClaimId: String,
        relationType: Components.Schemas.ClaimRelationType,
        linkQuality: Double? = nil,
        evidence: String? = nil
    ) async throws -> Components.Schemas.KnowledgeClaimLink {
        let linkResult = try await entityService.createClaimLink(
            claimId: claimId,
            relatedClaimId: relatedClaimId,
            relationType: relationType,
            linkQuality: linkQuality,
            evidence: evidence
        )
        await reload()
        return linkResult
    }

    /// Delete the given claims, then refresh.
    func delete(claimIds: [String]) async throws {
        for claimId in claimIds {
            try await entityService.deleteClaim(claimId)
        }
        await reload()
    }

    // MARK: - ChangeEventConsumer (called by LibraryChangeStream, NOT by views)

    nonisolated var changeDomain: String { "claim" }

    func apply(_ event: ChangeEvent) {
        switch event.verb {
        case "updated", "merged", "linked", "created":
            // Reconstructing the grouped/scoped list from ids alone isn't cheap;
            // reload the current scope (a single document/entity-scoped query).
            changeToken &+= 1
            scheduleReload()
        case "deleted":
            changeToken &+= 1
            let deleted = Set(event.claimIds)
            claims.removeAll { claim in
                guard let id = claim.id else { return false }
                return deleted.contains(id)
            }
        default:
            break
        }
    }

    /// Holds the shared 300ms trailing-reload debouncer (#1973). `scheduleReload()`
    /// (called above for non-delete verbs) and `resync()` are provided by the
    /// `ObservableDomainStore` extension — no per-store copies.
    let reloadDebouncer = ReloadDebouncer()
}
