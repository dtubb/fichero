@testable import Fichero
import FicheroAPIClient
import Testing

/// Owner ruling 2026-10-18 (#5788, `source.onboard.five-ways-in`): setup offers Copy, Leave in place and Move;
/// Index and Keep arranged are set on a synced folder in the Inspector.
@MainActor
struct SetupThreeWaysInTests {
    @Test func setupOffersCopyLeaveInPlaceMoveInThatOrder() {
        #expect(SetupWayIn.setupChoices == [.copy, .link, .move])
        #expect(SetupWayIn.setupChoices.map(\.title) == ["Copy", "Leave in place", "Move"])
    }

    @Test func aSavedIndexOrKeepArrangedShowsAsLeaveInPlace() {
        #expect(SetupWayIn.index.shownInSetup == .link)
        #expect(SetupWayIn.keepArranged.shownInSetup == .link)
        #expect(SetupWayIn.copy.shownInSetup == .copy)
        #expect(SetupWayIn.move.shownInSetup == .move)
    }

    /// No direction is asked (ruled 2026-10-18): with none chosen, a script reads in the engine's derived one.
    @Test func aScriptWithNoChosenDirectionReadsLeftToRightUntilTheEngineSaysOtherwise() {
        let store = RecipeSetupStore(client: FicheroClient(libraryPath: nil))
        #expect(store.direction(of: "Latn") == "ltr")
    }
}
