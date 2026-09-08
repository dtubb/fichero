import FicheroAPIClient
import Foundation
import OSLog
import SwiftUI

private let knowledgeSettingsLogger = Logger(
    subsystem: "app.fichero.fichero", category: "KnowledgeSettings"
)

/// One configured SPARQL endpoint (name + URL) the Wikidata enrichment can query.
struct SparqlEndpointRow: Identifiable, Hashable {
    let name: String
    let url: String
    var id: String { url }
}

/// Knowledge settings — the SPARQL endpoints the "Enrich from Wikidata" feature
/// queries. App-wide (persisted via `get_app_db` setting), configured through
/// `/api/settings/sparql-endpoints`. The Wikidata default is always present and
/// cannot be removed, so enrichment can never be left with no endpoint. Endpoint
/// access routes through the generated client so the bearer token + middleware
/// are supplied, exactly like `LocalModelsSettingsView`.
struct KnowledgeSettingsView: View {
    @Environment(AppState.self) private var appState
    @Environment(LibraryManager.self) private var libraryManager

    @State private var endpoints: [SparqlEndpointRow] = []
    @State private var selectedURL: String = ""
    @State private var isLoading = true
    @State private var statusMessage: String?
    @State private var newName: String = ""
    @State private var newURL: String = ""

    var body: some View {
        Form {
            if !appState.isBackendRunning {
                Section {
                    Label("Backend not connected", systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.secondary)
                }
            } else if isLoading {
                Section { ProgressView("Loading endpoints…") }
            } else {
                endpointsSection
                addEndpointSection
                if let statusMessage {
                    Section {
                        Text(statusMessage)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .formStyle(.grouped)
        .task { await load() }
    }

    private var endpointsSection: some View {
        Section("SPARQL Endpoints") {
            Text("The endpoint the Wikidata enrichment queries for an entity's statements. A failed endpoint surfaces a clear error — never a silent fallback.")
                .font(.caption)
                .foregroundStyle(.secondary)
            Picker("Default endpoint", selection: $selectedURL) {
                ForEach(endpoints) { endpoint in
                    Text(endpoint.name).tag(endpoint.url)
                }
            }
            .onChange(of: selectedURL) { _, _ in Task { await save() } }

            ForEach(endpoints) { endpoint in
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(endpoint.name).font(.body)
                        Text(endpoint.url)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                    }
                    Spacer()
                    if endpoint.url == KnowledgeSettingsView.wikidataDefaultURL {
                        Text("Default")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    } else {
                        Button(role: .destructive) {
                            Task { await remove(endpoint) }
                        } label: {
                            Image(systemName: "trash")
                        }
                        .buttonStyle(.borderless)
                        .help("Remove this endpoint")
                        .accessibilityLabel("Remove this endpoint")
                    }
                }
            }
        }
    }

    private var addEndpointSection: some View {
        Section("Add a custom endpoint") {
            TextField("Name", text: $newName)
            TextField("SPARQL URL (https://…/sparql)", text: $newURL)
            Button("Add endpoint") {
                Task { await add() }
            }
            .disabled(
                newName.trimmingCharacters(in: .whitespaces).isEmpty
                    || newURL.trimmingCharacters(in: .whitespaces).isEmpty
            )
        }
    }

    // MARK: - Data

    static let wikidataDefaultURL = "https://query.wikidata.org/sparql"

    private var client: FicheroClient {
        libraryManager.globalLibrary?.ficheroClient
            ?? FicheroClient(baseURL: EngineConfig.host, transportMode: EngineConfig.transportMode)
    }

    private func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let (status, data) = try await client.requestData(path: "/api/settings/sparql-endpoints")
            guard (200...299).contains(status) else {
                statusMessage = "Couldn't load endpoints (status \(status))."
                return
            }
            apply(data)
        } catch {
            statusMessage = "Couldn't load endpoints: \(error.localizedDescription)"
        }
    }

    private func apply(_ data: Data) {
        guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
        let rawEndpoints = obj["endpoints"] as? [[String: Any]] ?? []
        endpoints = rawEndpoints.compactMap { item in
            guard let name = item["name"] as? String, let url = item["url"] as? String else { return nil }
            return SparqlEndpointRow(name: name, url: url)
        }
        selectedURL = obj["selected_url"] as? String ?? KnowledgeSettingsView.wikidataDefaultURL
    }

    private func add() async {
        let name = newName.trimmingCharacters(in: .whitespacesAndNewlines)
        let url = newURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty, !url.isEmpty else { return }
        endpoints.append(SparqlEndpointRow(name: name, url: url))
        newName = ""
        newURL = ""
        await save()
    }

    private func remove(_ endpoint: SparqlEndpointRow) async {
        endpoints.removeAll { $0.url == endpoint.url }
        if selectedURL == endpoint.url {
            selectedURL = KnowledgeSettingsView.wikidataDefaultURL
        }
        await save()
    }

    private func save() async {
        let payload: [String: Any] = [
            "endpoints": endpoints.map { ["name": $0.name, "url": $0.url] },
            "selected_url": selectedURL,
        ]
        do {
            let body = try JSONSerialization.data(withJSONObject: payload)
            let (status, data) = try await client.requestData(
                path: "/api/settings/sparql-endpoints", method: "PUT", jsonBody: body
            )
            guard (200...299).contains(status) else {
                statusMessage = "Couldn't save endpoints (status \(status))."
                return
            }
            // Reflect what the server actually persisted (it keeps the Wikidata
            // default present and rejects an unknown selection).
            apply(data)
            statusMessage = nil
        } catch {
            statusMessage = "Couldn't save endpoints: \(error.localizedDescription)"
        }
    }
}
