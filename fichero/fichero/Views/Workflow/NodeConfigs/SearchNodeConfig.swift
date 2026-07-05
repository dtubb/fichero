import SwiftUI

/// Configuration view for search node
struct SearchNodeConfig: View {
    @Binding var node: WorkflowNode

    @Environment(SavedSearchServiceGenerated.self) var savedSearchService

    @State private var selectedSearchId: String = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Saved Search")
                .font(.caption)
                .foregroundColor(.secondary)

            Picker("Select saved search", selection: $selectedSearchId) {
                Text("Select...").tag("")
                ForEach(savedSearchService.savedSearches) { search in
                    Text(search.name).tag(search.id)
                }
            }
            .pickerStyle(.menu)
            .onChange(of: selectedSearchId) { _, newValue in
                if node.config == nil {
                    node.config = [:]
                }
                node.config?["search_id"] = .string(newValue)
                // Also store the query for display purposes
                if let search = savedSearchService.savedSearches.first(where: { $0.id == newValue }) {
                    node.config?["query"] = .string(search.query)
                }
            }

            if savedSearchService.savedSearches.isEmpty {
                Text("No saved searches. Create one from the Search view.")
                    .font(.caption2)
                    .foregroundColor(.secondary)
                    .italic()
                Button("Reload Saved Searches") {
                    Task {
                        try? await savedSearchService.loadSavedSearches()
                    }
                }
                .buttonStyle(.borderless)
            }
        }
        .task {
            // Load saved searches if not already loaded
            if savedSearchService.savedSearches.isEmpty {
                try? await savedSearchService.loadSavedSearches()
            }
        }
        .onAppear {
            loadInitialState()
        }
    }

    private func loadInitialState() {
        if let configValue = node.config?["search_id"],
           case .string(let id) = configValue {
            selectedSearchId = id
        }
    }
}
