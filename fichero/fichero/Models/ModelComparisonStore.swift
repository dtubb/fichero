import Foundation
import Observation
import OSLog

/// Observable domain store for model comparison (#1863).
///
/// The single endpoint accessor for the model-comparison surface. Views observe
/// this store and dispatch the named actions below; they never construct or call
/// `ModelComparisonService` directly. The service stays as the transport (it owns
/// the generated OpenAPI client and the request/response mapping) and this store
/// wraps it, exposing the observable state and the verbs the two comparison views
/// need.
///
/// Model comparison is a **dev-tier, app-wide** feature with no library scope and
/// no change stream, so — unlike `EntityStore`/`NoteStore`/`DocumentStore` — it
/// deliberately does NOT conform to `ObservableDomainStore` (that protocol is the
/// change-stream substrate). It is a plain `@Observable` accessor: the store is
/// the only thing that touches the endpoint, which is the invariant #1863 targets.
///
/// State is read straight through from the transport (which is itself
/// `@Observable`), so a mutation the service makes — e.g. a finished `compare(…)`
/// pushing a fresh `lastResult`/`history` — is observed by any view reading the
/// matching store property. No copies, no double book-keeping.
@MainActor
@Observable
final class ModelComparisonStore {
    // ─── Transport: the EXISTING ModelComparisonService, unchanged ───
    let service: ModelComparisonService

    init(service: ModelComparisonService = ModelComparisonService()) {
        self.service = service
    }

    // MARK: - Published domain state (views read these directly)

    var isComparing: Bool { service.isComparing }
    var lastResult: ComparisonResult? { service.lastResult }
    var history: [ComparisonResult] { service.history }
    var presets: [ComparisonPreset] { service.presets }
    var availableModels: [ComparisonModelInfo] { service.availableModels }
    var error: String? { service.error }

    // MARK: - Catalog loaders (the store, not the view, owns fetching)

    func loadModels() async { await service.loadModels() }
    func loadPresets() async { await service.loadPresets() }
    /// Recent comparison history — the sidebar's comparisons bucket (#4335)
    /// loads through the store like every other sidebar data source.
    func loadHistory(limit: Int = 10) async { await service.loadHistory(limit: limit) }

    // MARK: - Named actions

    func compare(prompt: String, models: [ModelSpec], systemPrompt: String? = nil) async {
        await service.compare(prompt: prompt, models: models, systemPrompt: systemPrompt)
    }

    func compareNode(
        workflowId: String,
        nodeId: String,
        models: [ModelSpec],
        pinnedInputs: [String: String] = [:]
    ) async throws -> NodeComparisonResponse {
        try await service.compareNode(
            workflowId: workflowId,
            nodeId: nodeId,
            models: models,
            pinnedInputs: pinnedInputs
        )
    }

    /// Select a previous comparison from `history` as the visible `lastResult`.
    /// Replaces the views writing `service.lastResult` directly — the store owns
    /// every mutation of the comparison state.
    func selectResult(id: ComparisonResult.ID?) {
        guard let id, let match = service.history.first(where: { $0.id == id }) else { return }
        service.lastResult = match
    }
}
