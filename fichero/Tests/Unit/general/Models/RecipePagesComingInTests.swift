import FicheroAPIClient
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

    /// #6252: a project that already holds its pages is told so on Add Material, and adding more is optional.
    func testAProjectWithPagesIsToldWhatIsThere_notAskedForThem() {
        XCTAssertEqual(RecipeSetupStore.materialAlreadyThere(pages: 12, counted: "12 photographs in 3 folders"),
                       "This project already has 12 pages (12 photographs in 3 folders). Adding more is optional.")
        XCTAssertEqual(RecipeSetupStore.materialAlreadyThere(pages: 1, counted: nil),
                       "This project already has 1 page. Adding more is optional.")
        XCTAssertNil(RecipeSetupStore.materialAlreadyThere(pages: 0, counted: nil))
        XCTAssertNil(RecipeSetupStore.materialAlreadyThere(pages: nil, counted: nil))
    }
}
