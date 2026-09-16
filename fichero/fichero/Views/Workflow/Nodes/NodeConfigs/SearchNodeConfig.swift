import SwiftUI

/// Configuration view for search node
struct SearchNodeConfig: View {
    @Binding var node: WorkflowNode

    @Environment(SavedSearchService.self) var savedSearchService

    @State private var selectedSearchId: String = ""
    /// True while `loadInitialState` seeds `selectedSearchId` from config on open, so the picker's
    /// `.onChange` (which rewrites `search_id`/`query`) doesn't fire an autosave merely because the
    /// node was OPENED (workflow-node-config open-is-read-only; the F4-residual pattern). Cleared a
    /// main-hop later so a genuine pick still writes.
    @State private var isLoadingConfig = false

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
                guard !isLoadingConfig else { return }   // on-open seed is not a user edit
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
        isLoadingConfig = true
        if let configValue = node.config?["search_id"],
           case .string(let id) = configValue {
            selectedSearchId = id
        }
        // Clear AFTER this cycle's onChange delivery so the seed above never counts as an edit.
        Task { @MainActor in isLoadingConfig = false }
    }
}
