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
        // RULING CHANGE (perf audit 2026-08-19): the token bump is DEBOUNCED —
        // an hour-long import emitting document.updated ~2/sec used to re-run
        // the full 4-leg transient search per event. Synchronously nothing
        // lands; the burst coalesces to one bump after the trailing window
        // (timing owned by ReloadDebouncerWaitTests — the pure wait() math;
        // a live-clock wait here raced the two runners and flaked).
        #expect(store.changeToken == 0)
        let url = try AppSource.root().appendingPathComponent("Models/SearchStore.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        let body = source
            .components(separatedBy: "func apply(_ event: ChangeEvent)")[1]
            .components(separatedBy: "\n    func ")[0]
        #expect(body.contains("changeDebouncer.schedule"))
        // Same order rule as the activity store: the only bump is inside the
        // scheduled closure, never synchronously on the event path.
        let scheduleAt = try #require(body.range(of: "changeDebouncer.schedule"))
        if let bumpAt = body.range(of: "changeToken &+= 1") {
            #expect(scheduleAt.lowerBound < bumpAt.lowerBound)
        }
    }
}
