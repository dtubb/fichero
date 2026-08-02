import FicheroAPIClient
import Foundation
import Observation
import OSLog

/// One graph-context merge-candidate pair (#3318) from
/// `/api/kg/entity-curation/candidates` — two entities whose claim-neighborhoods
/// overlap (Jaccard), surfaced for user-confirmed merge. Never merged
/// automatically.
struct EntityReconciliationCandidate: Identifiable, Hashable {
    let entityAId: String
    let entityAName: String
    let entityBId: String
    let entityBName: String
    let jaccard: Double
    let entityType: String?

    var id: String { "\(entityAId)|\(entityBId)" }
}

/// One external-authority match (#3757) from
/// `/api/kg/entity-curation/authority/refresh` — a *locally cached* snapshot
/// (Wikidata / VIAF / LoC) the user can link to an entity. Never a live lookup
/// at render time; the refresh call is the only outbound step.
struct AuthorityCandidate: Identifiable, Hashable {
    let authority: String
    let authorityId: String
    let label: String
    let description: String?
    let sourceURL: String?

    var id: String { "\(authority)|\(authorityId)" }
}

/// Observable domain store for knowledge entities (#1885, keystone template).
///
/// The single endpoint accessor for the entity list a view renders. A view
/// never calls `EntityService` / `KGCurationService`
/// directly: it observes `entities` and dispatches the named actions below.
/// Each action performs the typed write and then refreshes the current scope —
/// today via an explicit reload (no backend push yet), and via `apply(_:)`
/// once the per-library change-stream (#1863) starts emitting. Swapping reload
/// for push is then a no-op at every call site.
///
/// Mirrors `WorkflowExecutionObserver`: typed event in → mutate observable
/// state → SwiftUI re-renders every bound view. One instance per library
/// (registered on `LibraryReference`), shared across that library's windows.
@MainActor
@Observable
final class EntityStore: ObservableDomainStore {
    // ─── Published domain state (views read these directly) ───
    //
    // There used to be a fourth: `entities`, a mirror of the CURRENT document
    // scope, kept in sync by five mutations and a `syncLegacyScope` helper —
    // and read by nothing. Views take the per-document containers below
    // through `entities(forDocument:)` / `isLoading(forDocument:)` /
    // `loadError(forDocument:)`. Its two scalar companions, `isLoading` and
    // `loadError`, were dead for the same reason.
    //
    // It was removed rather than reconciled (#4489): three of this store's
    // four "partial reconciliations" were partial only with respect to state
    // nobody could see. Reconciling it would have made five mutations more
    // expensive to maintain a value with no reader, and would have looked
    // like diligence.
    var libraryEntities: [Components.Schemas.KnowledgeEntity] = []
    var libraryClaimCounts: [String: Int] = [:]
    var isLoadingLibrary = false
    var libraryLoadError: String?
    var entitiesByDocumentId: [String: [Components.Schemas.KnowledgeEntity]] = [:]
    var loadingDocumentIds: Set<String> = []
    var loadErrorsByDocumentId: [String: String] = [:]

    // ─── Transport: the EXISTING generated wrappers, unchanged ───
    let entityService: EntityService
    let kgCurationService: KGCurationService
    private let libraryPath: String
    let log = Logger(subsystem: "app.fichero.fichero", category: "EntityStore")

    /// Document scopes that have been loaded successfully. Multiple inspector
    /// windows on the same library can keep different document buckets warm
    /// without thrashing each other's visible list (#1908).
    var loadedDocumentIds: Set<String> = []
    var lastLoadedDocumentId: String?
    var lastLibraryQuery: String?

    init(
        entityService: EntityService,
        kgCurationService: KGCurationService,
        libraryPath: String
    ) {
        self.entityService = entityService
        self.kgCurationService = kgCurationService
        self.libraryPath = libraryPath
    }

    // ─── External authority curation (#3757) ───
    /// Whether external authority linking (Wikidata / VIAF / LoC) is enabled for
    /// this library. Views observe this; the store is the only endpoint accessor
    /// (observable-data-layer, #1863) — a view never calls the curation service
    /// directly.
    var externalAuthorityEnabled = false
    var isLoadingAuthoritySettings = false
    var authoritySettingsError: String?

    /// Holds the shared 300ms trailing-reload debouncer (#1973). `scheduleReload()`
    /// (called by ChangeEventConsumer) and `resync()` are provided by the
    /// `ObservableDomainStore` extension — no per-store copies.
    let reloadDebouncer = ReloadDebouncer()
}
