@testable import Fichero
import Testing

/// `sharing.multiuser-switch-says-the-refusal` (docs/contributor_manual/specs/source/sharing-two-macs.md §10.4, #6299): the
/// engine's refusal reaches the person in words. Written 2026-10-31, not yet built (no Xcode run on this Mac).
struct MultiuserSwitchWordsTests {
    @Test("the 2026-10-31 400 reads as the engine's own detail, never 'Unexpected response'")
    func fourHundredSaysTheDetail() {
        let words = MultiuserSwitchWords.sentence(status: 400, detail: "Missing X-Fichero-Library-Path header. Please open a library document first.")
        #expect(words.hasPrefix("Missing X-Fichero-Library-Path"))
        #expect(!words.contains("Unexpected response"))
    }

    @Test("the password gap and the owner rule read as the next step")
    func designedRefusals() {
        #expect(MultiuserSwitchWords.sentence(status: 409, detail: "Multi-user needs the owner's account to have a password first: set one, then turn it on")
                == MultiuserSwitchWords.passwordFirst)
        #expect(MultiuserSwitchWords.sentence(status: 403, detail: "sign in as the owner to change Multi-user") == MultiuserSwitchWords.ownerOnly)
    }

    @Test("no detail at all still gives a sentence that names the status and a way out")
    func noDetail() {
        let words = MultiuserSwitchWords.sentence(status: 503, detail: nil)
        #expect(words.contains("503") && words.contains("Try again"))
        for banned in ["undocumented", "statusCode", "Unexpected response"] { #expect(!words.contains(banned)) }
    }
}
