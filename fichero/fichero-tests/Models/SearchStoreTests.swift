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

    @Test("blank searches clear state without reaching the search service")
    func blankSearchIsLocalNoOp() async {
        let store = makeStore()

        await store.performSearch(query: " \n\t ")

        #expect(store.results.isEmpty)
        #expect(store.searchStats == nil)
        #expect(store.searchError == nil)
        #expect(!store.isSearching)
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
