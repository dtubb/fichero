@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// The purpose checkboxes and "what runs by itself" after they moved to `RecipeSetupStore+Purposes` (#6390 build
/// fix): same behaviour, no transport needed.
@MainActor
struct RecipeSetupStorePurposesTests {
    private func makeStore() -> RecipeSetupStore {
        let client = FicheroClient(baseURL: URL(string: "https://test.fichero")!, libraryPath: "/tmp/test.fichero")
        return RecipeSetupStore(client: client)
    }

    @Test("ticking a purpose twice leaves it unticked")
    func tickTwiceUnticks() {
        let store = makeStore()
        store.purposes = []
        store.toggle(purpose: "entities")
        #expect(store.purposes == ["entities"])
        store.toggle(purpose: "entities")
        #expect(store.purposes.isEmpty)
    }

    @Test("with no recipe and no answer, nothing runs by itself, and saying so keeps it so")
    func nothingRunsWithoutAnAnswer() {
        let store = makeStore()
        #expect(store.automaticAnswer.runs == false)
        store.setRunsByItself(false)
        #expect(store.automatic?.runs == false)
        #expect(store.automatic?.steps.isEmpty == true)
    }
}
