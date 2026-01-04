import SwiftUI

/// Toolbar for Search view with results summary and save controls
struct SearchViewToolbar: View {
    // Search state
    let isSearching: Bool
    let searchError: String?
    let resultsCount: Int
    let hasQuery: Bool
    let hasActiveFilters: Bool

    // Actions
    let onSaveSearch: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            // Results summary (left side)
            if isSearching {
                HStack(spacing: 8) {
                    ProgressView()
                        .scaleEffect(0.7)
                    Text("Searching...")
                        .foregroundStyle(.secondary)
                        .font(.caption)
                }
            } else if let error = searchError {
                HStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle")
                        .foregroundStyle(.orange)
                    Text(error)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .font(.caption)
                }
            } else {
                Text("\(resultsCount) results")
                    .foregroundStyle(.secondary)
                    .font(.caption)
            }

            Spacer()

            // Save search button (right side)
            if hasQuery || hasActiveFilters {
                Button("Save Search") {
                    onSaveSearch()
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(.ultraThinMaterial)
    }
}
