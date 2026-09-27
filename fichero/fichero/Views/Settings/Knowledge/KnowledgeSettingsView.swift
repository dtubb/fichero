import SwiftUI

/// Knowledge settings — the SPARQL endpoints the "Enrich from Wikidata" feature
/// queries. The Wikidata default is always present and cannot be removed, so
/// enrichment can never be left with no endpoint. All endpoint access happens
/// through `KnowledgeSettingsStore` (#5098: the observable-data-layer guard —
/// this view used to call the generated client directly, exactly like
/// `LocalModelsSettingsView` still does); the store owns the request/response
/// mapping and which client (per-library or app-wide fallback) to use.
struct KnowledgeSettingsView: View {
    @Environment(AppState.self) private var appState
    @Environment(LibraryManager.self) private var libraryManager

    @State private var store = KnowledgeSettingsStore()
    @State private var newName: String = ""
    @State private var newURL: String = ""

    var body: some View {
        Form {
            if !appState.isBackendRunning {
                Section {
                    Label("Backend not connected", systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.secondary)
                }
            } else if store.isLoading {
                Section { ProgressView("Loading endpoints…") }
            } else {
                endpointsSection
                addEndpointSection
                if let statusMessage = store.statusMessage {
                    Section {
                        Text(statusMessage)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .formStyle(.grouped)
        .task {
            store.configure(libraryManager: libraryManager)
            await store.load()
        }
    }

    private var endpointsSection: some View {
        Section("SPARQL Endpoints") {
            // Multi-line literal with a trailing `\` so the rendered string is
            // still ONE line — the wrap is in the source, not in the UI.
            Text("""
                The endpoint the Wikidata enrichment queries for an entity's statements. \
                A failed endpoint surfaces a clear error — never a silent fallback.
                """)
                .font(.caption)
                .foregroundStyle(.secondary)
            Picker("Default endpoint", selection: $store.selectedURL) {
                ForEach(store.endpoints) { endpoint in
                    Text(endpoint.name).tag(endpoint.url)
                }
            }

            ForEach(store.endpoints) { endpoint in
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(endpoint.name).font(.body)
                        Text(endpoint.url)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                    }
                    Spacer()
                    if endpoint.url == KnowledgeSettingsStore.wikidataDefaultURL {
                        Text("Default")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    } else {
                        Button(role: .destructive) {
                            Task { await store.remove(endpoint) }
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
                // Cleared immediately, before the save round trip — matching the
                // view's original ordering, so the fields don't sit populated
                // while the network call is in flight.
                let name = newName
                let url = newURL
                newName = ""
                newURL = ""
                Task { await store.add(name: name, url: url) }
            }
            .disabled(
                newName.trimmingCharacters(in: .whitespaces).isEmpty
                    || newURL.trimmingCharacters(in: .whitespaces).isEmpty
            )
        }
    }
}
