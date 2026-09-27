import FicheroAPIClient
import Foundation
import Observation
import OSLog

private let knowledgeSettingsStoreLogger = Logger(
    subsystem: "app.fichero.fichero", category: "KnowledgeSettingsStore"
)

/// One configured SPARQL endpoint (name + URL) the Wikidata enrichment can query.
struct SparqlEndpointRow: Identifiable, Hashable {
    let name: String
    let url: String
    var id: String { url }
}

/// Observable domain store for the Knowledge settings pane's SPARQL endpoints (#5098's
/// observable-data-layer guard: `KnowledgeSettingsView` used to call `client.api.*`
/// directly — the one offence the guard names, not the "already a store in different
/// clothes" shape `LooveCoverageService` turned out to be).
///
/// App-wide (persisted via `get_app_db`), configured through
/// `/api/settings/sparql-endpoints`. `configure(libraryManager:)` is called once from
/// the view's `.task` — the store cannot read `@Environment` itself, so the view hands
/// over the ONE thing it is allowed to decide (which client to prefer), and every actual
/// endpoint call happens here.
@MainActor
@Observable
final class KnowledgeSettingsStore {
    static let wikidataDefaultURL = "https://query.wikidata.org/sparql"

    private(set) var endpoints: [SparqlEndpointRow] = []
    /// `didSet` here is exactly what `.onChange(of: selectedURL)` was on the view (the
    /// picker's own selection AND the value `apply(_:)` writes back after a load/save
    /// both go through this one write, matching the view's original behaviour).
    var selectedURL: String = "" {
        didSet {
            guard oldValue != selectedURL else { return }
            Task { await save() }
        }
    }
    private(set) var isLoading = true
    private(set) var statusMessage: String?

    private weak var libraryManager: LibraryManager?

    /// The client the view resolved this session's library through (#1894's own
    /// precedent): reuse an already-connected per-library client when one exists,
    /// falling back to a fresh app-wide one. Called once from the view's `.task`.
    func configure(libraryManager: LibraryManager) {
        self.libraryManager = libraryManager
    }

    private var client: FicheroClient {
        libraryManager?.globalLibrary?.ficheroClient
            ?? FicheroClient(baseURL: EngineConfig.host, transportMode: EngineConfig.transportMode)
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let response = try await client.api.getSparqlEndpointsApiSettingsSparqlEndpointsGet(.init())
            switch response {
            case .ok(let ok):
                apply(try ok.body.json)
            case .undocumented(let status, _):
                statusMessage = "Couldn't load endpoints (status \(status))."
            }
        } catch {
            statusMessage = "Couldn't load endpoints: \(error.localizedDescription)"
        }
    }

    func add(name: String, url: String) async {
        let trimmedName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedURL = url.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedName.isEmpty, !trimmedURL.isEmpty else { return }
        endpoints.append(SparqlEndpointRow(name: trimmedName, url: trimmedURL))
        await save()
    }

    func remove(_ endpoint: SparqlEndpointRow) async {
        endpoints.removeAll { $0.url == endpoint.url }
        if selectedURL == endpoint.url {
            selectedURL = Self.wikidataDefaultURL
        }
        await save()
    }

    private func apply(_ config: Components.Schemas.SparqlEndpointsConfig) {
        endpoints = (config.endpoints ?? []).map { SparqlEndpointRow(name: $0.name, url: $0.url) }
        selectedURL = config.selectedUrl ?? Self.wikidataDefaultURL
    }

    private func save() async {
        let config = Components.Schemas.SparqlEndpointsConfig(
            endpoints: endpoints.map { Components.Schemas.SparqlEndpoint(name: $0.name, url: $0.url) },
            selectedUrl: selectedURL
        )
        do {
            let response = try await client.api.setSparqlEndpointsApiSettingsSparqlEndpointsPut(
                .init(body: .json(config))
            )
            switch response {
            case .ok(let ok):
                // Reflect what the server actually persisted (it keeps the
                // Wikidata default present and rejects an unknown selection).
                apply(try ok.body.json)
                statusMessage = nil
            case .unprocessableContent:
                statusMessage = "Couldn't save endpoints: the server rejected the request."
            case .undocumented(let status, _):
                statusMessage = "Couldn't save endpoints (status \(status))."
            }
        } catch {
            statusMessage = "Couldn't save endpoints: \(error.localizedDescription)"
        }
    }
}
