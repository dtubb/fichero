@testable import Fichero
import Foundation
import Testing

/// `sharing.undocumented-never-reaches-the-person` (Step 2.2): no sentence shows a code or the client's own words.
struct PersonFacingErrorTests {
    private enum FakeResponse { case success, undocumented(statusCode: Int, String), notFound, conflict }

    @Test func noMappedSentenceContainsTheClientsWords() {
        let banned = ["undocumented", "statusCode", "content-length", "HTTPBody"]
        for status in [401, 403, 404, 409, 422, 429, 500, 502, 418, 0] {
            let text = PersonFacingError.message(for: status)
            #expect(!text.isEmpty)
            for word in banned { #expect(!text.contains(word), "\(status): \(word)") }
        }
    }

    @Test func theMultiUserOffBodyMapsToTheAccountsOffSentence() {
        #expect(PersonFacingError.message(for: 404, detail: "multi-user auth is disabled") == PersonFacingError.accountsOffSentence)
        #expect(PersonFacingError.message(for: 409, detail: "multi-user auth is disabled") == PersonFacingError.accountsOffSentence)
        #expect(PersonFacingError.message(for: 404, context: .init(accountsOff: true)) == PersonFacingError.accountsOffSentence)
    }

    @Test func aNotFoundAddsTheContextsFix() {
        let text = PersonFacingError.message(for: 404, context: .init(fix: "Update Fichero on that Mac."))
        #expect(text == "That isn't available on this Mac right now. Update Fichero on that Mac.")
    }

    @Test func anUnknownStatusIsTheGenericLine() {
        #expect(PersonFacingError.message(for: 418) == "Fichero couldn't do that. Try again.")
    }

    @Test func theEnginesWordsOnAConflictAreKept() {
        #expect(PersonFacingError.message(for: 409, detail: "That name is taken.") == "That name is taken.")
    }

    @Test func aResponseCaseGivesItsStatusWithoutPrintingIt() {
        #expect(PersonFacingError.status(of: FakeResponse.undocumented(statusCode: 404, "x")) == 404)
        #expect(PersonFacingError.status(of: FakeResponse.notFound) == 404)
        #expect(PersonFacingError.status(of: FakeResponse.conflict) == 409)
        let text = PersonFacingError.message(forResponse: FakeResponse.undocumented(statusCode: 503, "x"))
        #expect(text.contains("server had a problem") && !text.contains("undocumented"))
    }
}
