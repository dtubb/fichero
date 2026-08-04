import Foundation
import Observation
import OSLog

/// Parsed entity-artifact names for one document (#3861).
///
/// The list-row / table-cell entity previews only need the extracted *names*
/// per entity-type, not the raw `Artifact` payloads. Parsing once into this
/// value (in `ArtifactEntityStore`) keeps every consuming view free of decode
/// work and lets `nil` vs a present-but-empty bundle distinguish "still
/// loading" from "loaded, nothing found".
struct ArtifactEntityBundle: Equatable {
    var people: [String] = []
    var places: [String] = []
    var organizations: [String] = []
    var events: [String] = []
    var dates: [String] = []
    var keywords: [String] = []

    var isEmpty: Bool {
        people.isEmpty && places.isEmpty && organizations.isEmpty
            && events.isEmpty && dates.isEmpty && keywords.isEmpty
    }

    /// Names for a single entity-type column (table cell).
    func names(for entityType: String) -> [String] {
        switch entityType {
        case "people": return people
        case "places": return places
        case "organizations": return organizations
        case "events": return events
        case "dates": return dates
        case "keywords": return keywords
        default: return []
        }
    }
}

/// Shared, document-keyed cache for list/table entity previews (#3861).
///
/// Fixes the N+1 fetch storm: previously `ArtifactEntitiesView` and each
/// `ArtifactEntityCell` fired `getArtifacts()` in `.onAppear` — so one document
/// visible as a Mail-style row plus up to six per-type table cells fetched the
/// SAME document up to seven times, and `.onChange(workflowCompletedCount)`
/// force-refetched every visible row/cell at once on any workflow completion.
///
/// Now the store is the single endpoint accessor (observable-data-layer rule,
/// #1863): rows/cells call `ensureLoaded(_:)` and OBSERVE `bundles`; concurrent
/// requests for the same document collapse to one fetch (`inFlight`); a workflow
/// completion invalidates ONLY the document ids that run actually touched.
///
/// Wraps the EXISTING `ArtifactService` transport unchanged (the
/// iterate-never-replace rule): the store owns *when* to fetch and the per-doc
/// dedupe; the service still owns *how* (and its own `artifactsByDocument` cache).
@MainActor
@Observable
final class ArtifactEntityStore {
    /// Parsed previews keyed by documentId. `nil` for an id means "not loaded
    /// yet" (show the silent placeholder); a present-but-empty bundle means
    /// "loaded, no entity artifacts" (show "—").
    private(set) var bundles: [String: ArtifactEntityBundle] = [:]

    /// Documents with a fetch in flight — a second consumer for the same id is a
    /// no-op, so seven views for one document trigger exactly one request.
    private var inFlight: Set<String> = []

    /// Documents whose last read FAILED (#4507) — the third state beside
    /// `bundles`: `nil` = not loaded, present bundle = loaded (possibly
    /// empty), membership here = "could not read". It used to be collapsed
    /// into "loaded empty": a transport failure wrote an empty bundle, so
    /// "couldn't load" rendered as "has none" — a wrong answer presented as a
    /// fact — and, because `ensureLoaded` gates on the bundle being nil, it
    /// was never retried for the rest of the session.
    ///
    /// Membership still stops `ensureLoaded` from re-entering (no retry storm
    /// against a downed engine — the layout the old empty-bundle hack was
    /// protecting stays stable). Recovery paths: `invalidate(_:)` (workflow
    /// completion / manual refresh) and `retryFailedLoads()` (engine became
    /// ready again).
    private(set) var failedDocumentIds: Set<String> = []

    /// Workflow executions whose completion we've already reconciled, so the N
    /// views that each observe `workflowCompletedCount` don't re-invalidate the
    /// same run N times.
    private var seenCompletedThreadIds: Set<String> = []

    private let artifactService: ArtifactService
    private let log = Logger(subsystem: "app.fichero.fichero", category: "ArtifactEntityStore")

    init(artifactService: ArtifactService) {
        self.artifactService = artifactService
    }

    // MARK: - Per-service sharing

    // ponytail: one store per ArtifactService (i.e. per library),
    // resolved from the service the views already hold in their environment —
    // avoids threading a new @Environment object through the window/scene roots
    // (a separate lane). The map is never pruned; libraries are few, so the
    // upgrade path (clear on library close) isn't worth its wiring yet.
    private static var registry: [ObjectIdentifier: ArtifactEntityStore] = [:]

    static func shared(for artifactService: ArtifactService) -> ArtifactEntityStore {
        let key = ObjectIdentifier(artifactService)
        if let existing = registry[key] { return existing }
        let store = ArtifactEntityStore(artifactService: artifactService)
        registry[key] = store
        return store
    }

    // MARK: - Reads (views observe these)

    func bundle(for documentId: String) -> ArtifactEntityBundle? {
        bundles[documentId]
    }

    /// True when the last read for `documentId` failed (#4507). Views render
    /// this distinctly from "loaded, nothing found" — a failed read is not a
    /// measurement of zero.
    func loadFailed(for documentId: String) -> Bool {
        failedDocumentIds.contains(documentId)
    }

    // MARK: - Loading (the store, not the view, owns fetching)

    /// Load `documentId` once. No-op if already loaded or a fetch is in flight —
    /// this is what collapses the per-row + per-cell N+1 into a single request.
    func ensureLoaded(_ documentId: String) {
        guard bundles[documentId] == nil,
              !failedDocumentIds.contains(documentId),   // failed ≠ unloaded (#4507)
              !inFlight.contains(documentId) else { return }
        inFlight.insert(documentId)
        Task { await fetch(documentId, forceRefresh: false) }
    }

    /// Batch-warm the visible set (each id still deduped). Handed the folder's
    /// visible document ids by the caller; there is no server batch endpoint, so
    /// this fans out one deduped request per not-yet-loaded document.
    func prefetch(_ documentIds: [String]) {
        for id in documentIds { ensureLoaded(id) }
    }

    /// Re-fetch the given ids from the server (workflow completion / manual
    /// refresh). Keeps the existing bundle visible until the fresh value lands
    /// (no empty flash), and blocks a re-entrant `ensureLoaded` via `inFlight`.
    func invalidate(_ documentIds: Set<String>) {
        let ids = documentIds.filter { !inFlight.contains($0) }
        guard !ids.isEmpty else { return }
        // A refetch is a fresh answer either way — clear the failed mark so
        // its outcome, not the stale failure, decides the rendered state (#4507).
        failedDocumentIds.subtract(ids)
        for id in ids { inFlight.insert(id) }
        Task {
            for id in ids { await fetch(id, forceRefresh: true) }
        }
    }

    /// Re-fetch every document whose last read failed (#4507). Called when the
    /// engine transitions to ready: reads that failed while it was down or
    /// starting are the exact population worth one retry. Idempotent — the
    /// first caller moves the ids into `inFlight`; concurrent callers see an
    /// empty failed set.
    func retryFailedLoads() {
        guard !failedDocumentIds.isEmpty else { return }
        invalidate(failedDocumentIds)
    }

    /// Invalidate only the documents that newly-completed workflow runs touched.
    /// Idempotent across the many rows/cells that each observe
    /// `workflowCompletedCount`: once a run's threadId is seen it's never
    /// reprocessed, and only documents we currently hold are refetched.
    func reconcileCompletions(_ observer: WorkflowExecutionObserver) {
        let newThreadIds = observer.completedExecutions.keys.filter {
            !seenCompletedThreadIds.contains($0)
        }
        guard !newThreadIds.isEmpty else { return }

        var affected: Set<String> = []
        for threadId in newThreadIds {
            seenCompletedThreadIds.insert(threadId)
            if let execution = observer.completedExecutions[threadId] {
                affected.formUnion(execution.documentProgress.keys)
            }
        }

        // Failed reads count as held (#4507): a run that touched a document
        // whose earlier read failed is fresh evidence worth a refetch — the
        // demo-shaped case is a read that failed while the engine was busy
        // RUNNING the workflow whose completion lands here.
        let held = affected.filter { bundles[$0] != nil || failedDocumentIds.contains($0) }
        guard !held.isEmpty else { return }
        log.debug("Reconciling \(held.count, privacy: .public) affected docs after workflow completion")
        invalidate(held)
    }

    // MARK: - Private

    /// Caller MUST have inserted `documentId` into `inFlight` before spawning
    /// this — both `ensureLoaded` and `invalidate` do, so a re-entrant read can't
    /// start a duplicate fetch; this always clears the flag when done.
    private func fetch(_ documentId: String, forceRefresh: Bool) async {
        defer { inFlight.remove(documentId) }
        // Strict per-document scope ("{id}|own") — per-row counts must NOT include
        // page-child descendants, matching the prior view behaviour + V2 convention.
        let cacheKey = "\(documentId)|own"
        if !forceRefresh, let cached = artifactService.artifactsByDocument[cacheKey] {
            apply(fetchOutcome: .success(cached), for: documentId)
            return
        }
        do {
            let fetched = try await artifactService.getArtifacts(
                forDocumentId: documentId,
                forceRefresh: forceRefresh,
                includeDescendants: false
            )
            apply(fetchOutcome: .success(fetched), for: documentId)
        } catch {
            log.warning(
                "Artifact read failed for \(documentId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
            apply(fetchOutcome: .failure(error), for: documentId)
        }
    }

    /// Reduce one fetch outcome into the three-state cache (#4507). Internal
    /// (not private) so the failure transition is unit-testable without a
    /// network: the defect this replaces — `try?` writing an EMPTY bundle on
    /// failure — survived precisely because no test could reach it.
    func apply(fetchOutcome: Result<[Artifact], any Error>, for documentId: String) {
        switch fetchOutcome {
        case .success(let artifacts):
            failedDocumentIds.remove(documentId)
            bundles[documentId] = Self.parse(artifacts)
        case .failure:
            // NEVER write a bundle here. An empty bundle means "measured, zero
            // entities"; this branch means "could not measure". Collapsing the
            // two was #4507: 'couldn't load' rendered as 'has none' for the
            // rest of the session. The failed mark keeps the row's layout
            // settled (the old hack's actual goal) without asserting a zero.
            failedDocumentIds.insert(documentId)
        }
    }

    // MARK: - Parsing (moved out of the views)

    static func parse(_ artifacts: [Artifact]) -> ArtifactEntityBundle {
        var bundle = ArtifactEntityBundle()
        for artifact in artifacts {
            switch artifact.artifactType {
            case "people":
                bundle.people = extractNames(artifact, key: "name")
            case "places":
                bundle.places = extractNames(artifact, key: "name")
            case "organizations":
                bundle.organizations = extractNames(artifact, key: "name")
            case "events":
                bundle.events = extractNames(artifact, key: "event")
            case "keywords":
                bundle.keywords = extractKeywords(artifact)
            case "dates":
                bundle.dates = extractDates(artifact)
            default:
                break
            }
        }
        return bundle
    }

    static func extractNames(_ artifact: Artifact, key: String) -> [String] {
        guard let data = artifact.data,
              let value = data["items"]?.value,
              let items = value as? [[String: Any]] else { return [] }
        return items.compactMap { $0[key] as? String }
    }

    static func extractKeywords(_ artifact: Artifact) -> [String] {
        guard let data = artifact.data,
              let value = data["keywords"]?.value,
              let array = value as? [String] else { return [] }
        return array
    }

    static func extractDates(_ artifact: Artifact) -> [String] {
        guard let data = artifact.data,
              let value = data["items"]?.value,
              let items = value as? [[String: Any]] else { return [] }
        return items.compactMap { item in
            (item["date_normalized"] as? String) ?? (item["date"] as? String)
        }
    }
}
