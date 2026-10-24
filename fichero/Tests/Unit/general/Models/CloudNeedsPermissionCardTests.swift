import FicheroAPIClient
import Foundation
@testable import Fichero
import Testing

/// #5768 (`source.onboard.pages-may-leave`): a cloud card stays on the list, greyed and saying "needs permission",
/// until the person has said pages may leave this Mac. What breaks without it: the card is pressable and downloads
/// or is chosen against the person's answer, or it says nothing and the person cannot tell why it does nothing.
@MainActor
@Suite("A cloud card that needs permission (#5768)")
struct CloudNeedsPermissionCardTests {
    private static func card(needsPermission: Bool?, refused: String? = nil) throws -> Components.Schemas.ModelCandidate {
        let flag = (needsPermission.map { ",\"needs_permission\":\($0)" } ?? "")
            + (refused.map { ",\"refused\":\"\($0)\"" } ?? "")
        let json = """
        {"id":"openrouter:gpt","name":"A cloud reader","source":"provider","offered_because":"","pin":{},
         "jobs":["read-a-line"],"open_licence":true,"size":"","measured":"","in_recipe_rules":true,
         "runs_where":"cloud","availability":"download","availability_words":"Runs in the cloud","chosen":false\(flag)}
        """
        return try JSONDecoder().decode(Components.Schemas.ModelCandidate.self, from: Data(json.utf8))
    }

    @Test("the engine's flag is what greys the card, and its absence means nothing to ask")
    func flag() throws {
        #expect(ModelFinderCard.needsPermission(try Self.card(needsPermission: true)))
        #expect(!ModelFinderCard.needsPermission(try Self.card(needsPermission: false)))
        #expect(!ModelFinderCard.needsPermission(try Self.card(needsPermission: nil)))
    }

    @Test("a card that needs permission offers neither Use nor Download, and says why in one sentence")
    func nothingToPress() throws {
        let card = try Self.card(needsPermission: true)
        #expect(!ModelFinderCard.offersUse(card))
        #expect(!ModelFinderCard.offersDownload(card))
        #expect(ModelFinderCard.permissionWords == "Needs permission: pages would leave this Mac.")
    }

    @Test("a card that does not need permission is offered as before")
    func unchanged() throws {
        let card = try Self.card(needsPermission: false)
        #expect(ModelFinderCard.offersUse(card))
    }

    @Test("the refusal is said once: a card that needs permission does not repeat it under its permission line (#6033)")
    func saidOnce() throws {
        let words = "it runs in the cloud and this project keeps pages on this Mac"
        #expect(ModelFinderCard.refusedLine(try Self.card(needsPermission: true, refused: words)) == nil)
        #expect(ModelFinderCard.refusedLine(try Self.card(needsPermission: false, refused: words)) == words)
    }
}
