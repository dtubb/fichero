@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `HtrUnitedStore` (#5571): the store shows what the engine says a dataset may be used as, and asks for nothing without a language.
struct HtrUnitedStoreTests {
    private func dataset(as uses: [String]) throws -> Components.Schemas.HtrUnitedDataset {
        let json = """
        {"title":"T","url":"https://example.org","description":"d","languages":["la"],"scripts":["Latn"],
         "handwriting":true,"format":"PAGE","licence":{"name":"CC-BY","url":""},"as":\(uses.map { "\"\($0)\"" }),
         "importable":true}
        """
        return try JSONDecoder().decode(Components.Schemas.HtrUnitedDataset.self, from: Data(json.utf8))
    }

    @Test func allowsOnlyWhatTheEngineListed() throws {
        let open = try dataset(as: ["test-set", "training"])
        #expect(HtrUnitedStore.allows(open, "test-set"))
        #expect(HtrUnitedStore.allows(open, "training"))
        let unaccepted = try dataset(as: [])
        #expect(!HtrUnitedStore.allows(unaccepted, "training"), "empty until the licence is accepted")
    }

    @MainActor @Test func noLanguageIsAnEmptyListWithNoCall() async {
        // A client with no reachable engine: a call would set errorMessage.
        let store = HtrUnitedStore(client: FicheroClient(libraryPath: nil))
        await store.load(languages: [], scripts: ["Latn"])
        #expect(store.datasets.isEmpty)
        #expect(store.fetchedAt == nil)
        #expect(store.errorMessage == nil)
    }
}
