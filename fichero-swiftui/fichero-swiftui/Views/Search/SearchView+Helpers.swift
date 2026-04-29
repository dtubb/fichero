import OSLog
import SwiftUI

private let logger = Logger(subsystem: "com.fichero.fichero", category: "SearchView")

/// Helper methods for SearchView
extension SearchView {
    func clearFilters() {
        queryText = ""
        searchResults = []
        searchError = nil
    }

    func loadDocument(_ id: String) {
        Task {
            do {
                let doc: Document = try await apiClient.get("/documents/\(id)")
                await MainActor.run {
                    detailDocument = doc
                }
            } catch {
                logger.error("Failed to load document: \(error.localizedDescription)")
            }
        }
    }

    func performSearch() {
        guard !queryText.trimmingCharacters(in: .whitespaces).isEmpty else {
            searchResults = []
            searchStats = nil
            searchError = nil
            return
        }

        logger.info("Starting enhanced search for: \(queryText)")
        isSearching = true
        searchError = nil

        Task {
            do {
                logger.info("Calling searchService.search with enhanced parameters...")

                let response = try await searchService.searchCompatible(
                    query: queryText,
                    limit: 50,
                    minScore: 0.0,
                    searchType: "hybrid",
                    filters: nil,
                    sortBy: "relevance",
                    sortOrder: "desc",
                    offset: 0,
                    useFuzzyMatch: false,
                    highlightResults: true
                )

                logger.info("Got \(response.count) results (total: \(response.totalResults))")
                await MainActor.run {
                    searchResults = response.results
                    searchStats = response
                    isSearching = false
                }
            } catch {
                logger.error("Search error: \(String(describing: error))")
                await MainActor.run {
                    searchError = error.localizedDescription
                    searchResults = []
                    searchStats = nil
                    isSearching = false
                }
            }
        }
    }

}
