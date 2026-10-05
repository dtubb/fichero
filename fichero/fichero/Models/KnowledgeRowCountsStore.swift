import FicheroAPIClient
import Foundation
import Observation

/// One of a project's knowledge rows, as `GET /api/stats/knowledge` counts them (#5413).
enum KnowledgeRowKind: String, CaseIterable, Hashable {
    case entities
    case claims
    case citations
    case references
    case interpretations
    case frameworks
    case patterns

    /// The kinds whose count a change event of `domain` can move. `interpretation.*` is the one
    /// hermeneutic event the engine sends, so it covers frameworks and patterns too.
    static func kinds(forChangeDomain domain: String) -> Set<KnowledgeRowKind> {
        switch domain {
        case "entity": return [.entities]
        case "claim": return [.claims]
        case "citation": return [.citations]
        case "reference": return [.references]
        case "interpretation": return [.interpretations, .frameworks, .patterns]
        default: return []
        }
    }

    /// The sidebar row this kind draws, if the sidebar has one. Only Entities and Claims have a
    /// project-wide table to open today; the other counts are read and kept so their row is
    /// one case here once that table exists.
    var sidebarCollection: KnowledgeCollectionKind? {
        switch self {
        case .entities: return .entities
        case .claims: return .claims
        case .citations, .references, .interpretations, .frameworks, .patterns: return nil
        }
    }

    func count(in response: Components.Schemas.KnowledgeRowCountsResponse) -> Int {
        switch self {
        case .entities: return response.entities
        case .claims: return response.claims
        case .citations: return response.citations
        case .references: return response.references
        case .interpretations: return response.interpretations
        case .frameworks: return response.frameworks
        case .patterns: return response.patterns
        }
    }
}

/// How many items each of a project's knowledge rows holds, from the engine
/// (`GET /api/stats/knowledge`, #5413, `sidebar.knowledge.rows-only-when-non-empty`). The sidebar
/// draws a knowledge row only when its count is above 0.
///
/// One per project (on `LibraryReference`), registered with that project's change stream: an
/// `entity.*`, `claim.*`, `citation.*`, `reference.*` or `interpretation.*` event asks the route
/// again and writes only the counts of the kinds that changed, in place.
@MainActor
@Observable
final class KnowledgeRowCountsStore: ChangeEventConsumer {
    /// Nothing is drawn before the first read: a missing count is treated as 0.
    private(set) var counts: [KnowledgeRowKind: Int] = [:]
    private(set) var errorMessage: String?

    @ObservationIgnored private let client: FicheroClient
    @ObservationIgnored private let reloadDebouncer: ReloadDebouncer
    /// The kinds named by events since the last read; a burst of events reads the route once.
    @ObservationIgnored private var pendingKinds: Set<KnowledgeRowKind> = []

    /// `counts` seeds a preview canvas; the app starts empty and loads.
    init(
        client: FicheroClient,
        counts: [KnowledgeRowKind: Int] = [:],
        reloadDebouncer: ReloadDebouncer = ReloadDebouncer()
    ) {
        self.client = client
        self.counts = counts
        self.reloadDebouncer = reloadDebouncer
    }

    func count(of kind: KnowledgeRowKind) -> Int { counts[kind] ?? 0 }

    /// The rows the sidebar draws for this project, in order: those with a row and a count above 0.
    var nonEmptyRows: [KnowledgeCollectionKind] {
        KnowledgeRowKind.allCases.compactMap { kind in
            count(of: kind) > 0 ? kind.sidebarCollection : nil
        }
    }

    /// Read every count (first load, and a reconnect that may have missed events).
    func load() async {
        await refresh(Set(KnowledgeRowKind.allCases))
    }

    /// Read the route and write only `kinds`' counts, each in place.
    func refresh(_ kinds: Set<KnowledgeRowKind>) async {
        guard !kinds.isEmpty else { return }
        do {
            switch try await client.api.getKnowledgeRowCountsApiStatsKnowledgeGet() {
            case .ok(let success):
                let response = try success.body.json
                for kind in kinds {
                    let value = kind.count(in: response)
                    if counts[kind] != value { counts[kind] = value }
                }
                errorMessage = nil
            case .undocumented(let code, _):
                errorMessage = "Could not read the knowledge counts (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read the knowledge counts: \(error.localizedDescription)"
        }
    }

    /// Read the counts of the kinds events have named since the last read.
    func refreshPendingKinds() async {
        let kinds = pendingKinds
        pendingKinds = []
        await refresh(kinds)
    }

    // MARK: - ChangeEventConsumer

    nonisolated var changeDomains: Set<String> { ["entity", "claim", "citation", "reference", "interpretation"] }

    func apply(_ event: ChangeEvent) {
        let kinds = KnowledgeRowKind.kinds(forChangeDomain: event.domain)
        guard !kinds.isEmpty else { return }
        pendingKinds.formUnion(kinds)
        reloadDebouncer.schedule { [weak self] in
            await self?.refreshPendingKinds()
        }
    }

    func resync() async {
        await load()
    }
}
