@testable import Fichero
import XCTest

/// Review 208 of #5813: between adding a folder and its first page landing, the engine counts no page, but the app
/// must not say there is "no material yet".
@MainActor
final class RecipePagesComingInTests: XCTestCase {
    private let engineSays = "This project has no material yet: add your pages in Set Up › Your Material, and the plan follows from them."

    private func store() -> RecipeSetupStore {
        RecipeSetupStore(client: FicheroClient(baseURL: URL(string: "https://127.0.0.1:8765")!,
                                               libraryPath: "/tmp/RecipePagesComingInTests.fichero"))
    }

    func testWithNothingAddedTheEnginesSentenceStands() {
        XCTAssertEqual(store().refusalWords(engineSays, fallback: "x"), engineSays)
    }

    func testOnceMaterialIsAddedItSaysThePagesAreComingIn() {
        let store = store()
        store.materialAdded = "Box 7: 200 added (copy)."
        XCTAssertEqual(store.refusalWords(engineSays, fallback: "x"), RecipeSetupStore.pagesStillComingIn)
    }

    func testAnotherRefusalIsNeverRewritten() {
        let store = store()
        store.materialAdded = "Box 7: 200 added (copy)."
        XCTAssertEqual(store.refusalWords("Unknown script", fallback: "x"), "Unknown script")
        XCTAssertEqual(store.refusalWords(nil, fallback: "fallback"), "fallback")
    }
}
