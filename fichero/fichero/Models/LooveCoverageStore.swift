import Foundation
import Observation

/// Observable domain store for the LOOVE language-coverage matrix (#5098's
/// observable-data-layer guard: `LooveCoverageView` used to own `LooveCoverageService`
/// directly, which is the same shape the guard already flags for a view — the fix that
/// stuck for `ModelComparisonService` is this file's template, `ModelComparisonStore`).
///
/// Coverage is a **dev-tier, app-wide** diagnostic with no library scope and no change
/// stream, so — like `ModelComparisonStore` — this deliberately does NOT conform to
/// `ObservableDomainStore` (that protocol is the change-stream substrate). It is a plain
/// `@Observable` accessor: the store is the only thing that touches the endpoint, which
/// is the invariant the guard enforces; the service stays as the transport (it owns the
/// generated OpenAPI client and the request/response mapping) and this store wraps it.
///
/// State is read straight through from the transport (itself `@Observable`), so a
/// mutation the service makes is observed by any view reading the matching store
/// property — no copies, no double book-keeping.
@MainActor
@Observable
final class LooveCoverageStore {
    // ─── Transport: the EXISTING LooveCoverageService, unchanged ───
    let service: LooveCoverageService

    init(service: LooveCoverageService = LooveCoverageService()) {
        self.service = service
    }

    // MARK: - Published domain state (views read these directly)

    var isLoading: Bool { service.isLoading }
    var matrix: CoverageMatrix? { service.matrix }
    var errorMessage: String? { service.errorMessage }
    var pendingLanguages: Set<String> { service.pendingLanguages }

    // MARK: - Named actions (the store, not the view, owns fetching)

    func generate() async { await service.generate() }
    func load(languages: [CoverageLanguage]) async { await service.load(languages: languages) }
}
