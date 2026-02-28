import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "SearchView")

/// Helper methods for SearchView
extension SearchView {
    var hasActiveFilters: Bool {
        filters.docTypes != nil ||
        filters.fileTypes != nil ||
        filters.statuses != nil ||
        filters.hasContent != nil
    }

    func clearFilters() {
        queryText = ""
        filters = SearchFilters()
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
                let filterDict = buildFilterDictionary()

                let response = try await searchService.searchCompatible(
                    query: queryText,
                    limit: 50,
                    minScore: 0.0,
                    searchType: searchType,
                    filters: filterDict.isEmpty ? nil : filterDict,
                    sortBy: sortBy,
                    sortOrder: sortOrder,
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

    func buildFilterDictionary() -> [String: String] {
        var filterDict: [String: String] = [:]
        if let docTypes = filters.docTypes, !docTypes.isEmpty {
            filterDict["doc_type"] = docTypes.map { $0.rawValue }.joined(separator: ",")
        }
        if let fileTypes = filters.fileTypes, !fileTypes.isEmpty {
            filterDict["file_type"] = fileTypes.map { $0.rawValue }.joined(separator: ",")
        }
        if let statuses = filters.statuses, !statuses.isEmpty {
            filterDict["status"] = statuses.map { $0.rawValue }.joined(separator: ",")
        }
        if let hasContent = filters.hasContent {
            filterDict["has_content"] = hasContent ? "true" : "false"
        }
        return filterDict
    }

    func saveSearch() {
        guard !queryText.isEmpty else { return }
        isSaving = true

        Task {
            do {
                _ = try await savedSearchService.saveSearch(
                    query: queryText,
                    isSmartSearch: isSmartSearch,
                    searchType: searchType,
                    sortBy: sortBy,
                    sortDirection: sortOrder
                )
                await MainActor.run {
                    isSaving = false
                    onSearchSaved?()
                }
            } catch {
                logger.error("Failed to save search: \(error.localizedDescription)")
                await MainActor.run {
                    isSaving = false
                }
            }
        }
    }
}
