@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@MainActor
@Suite("SearchStore")
struct SearchStoreTests {

    private func makeStore() -> SearchStore {
        SearchStore(searchService: SearchService(ficheroClient: FicheroClient(libraryPath: nil)))
    }

    private func response(query: String) -> SearchResponse {
        SearchResponse(
            results: [
                SearchResult(
                    documentId: "document-1",
                    score: 0.9,
                    contentPreview: nil,
                    metadata: [:],
                    highlights: nil
                )
            ],
            count: 1,
            totalResults: 1,
            query: query,
            searchType: "hybrid",
            executionTimeMs: 0,
            hasMore: false,
            filtersApplied: nil,
            suggestions: nil
        )
    }

    @Test("blank searches clear state without reaching the search service")
    func blankSearchIsLocalNoOp() async {
        let store = makeStore()

        await store.performSearch(query: " \n\t ")

        #expect(store.results.isEmpty)
        #expect(store.searchStats == nil)
        #expect(store.searchFailure == nil)
        #expect(!store.isSearching)
    }

    @Test("request failures set typed failure and clear results")
    func requestFailureClearsSearchState() {
        let store = makeStore()
        store.applySearchResponse(response(query: "previous"))
        store.applySearchFailure(detail: "boom")

        #expect(store.searchFailure == .requestFailed(detail: "boom"))
        #expect(store.searchFailure?.message == "Search failed")
        #expect(store.results.isEmpty)
        #expect(store.searchStats == nil)
    }

    @Test("successful responses clear a previous search failure")
    func responseClearsSearchFailure() {
        let store = makeStore()
        store.applySearchFailure(detail: "boom")
        store.applySearchResponse(response(query: "recovered"))

        #expect(store.searchFailure == nil)
        #expect(store.results.count == 1)
        #expect(store.searchStats?.query == "recovered")
    }

    @Test("cancelled requests preserve the current search state")
    func cancellationPreservesSearchState() {
        let store = makeStore()
        store.applySearchResponse(response(query: "existing"))
        store.handleSearchError(CancellationError())

        #expect(store.searchFailure == nil)
        #expect(store.results.count == 1)
        #expect(store.searchStats?.query == "existing")
    }

    @Test("document change events invalidate cached search state through a token")
    func changeEventsAdvanceToken() throws {
        let store = makeStore()
        let data = try JSONSerialization.data(withJSONObject: ["type": "document.updated"])
        let event = try JSONDecoder().decode(ChangeEvent.self, from: data)

        store.apply(event)
        store.apply(event)

        #expect(store.changeDomains == ["document"])
        #expect(store.changeToken == 2)
    }
}
