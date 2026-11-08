@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Accept all N (`wide.review.accept-line-and-all`): the button's words, the request the engine takes, and when it is offered.
struct ReviewAcceptAllTests {
    @Test("the button says the engine's count, singular and plural, and names its undo")
    func words() {
        #expect(ReviewAcceptWords.button(12) == "Accept all 12")
        #expect(ReviewAcceptWords.help(1).contains("the 1 line"))
        #expect(ReviewAcceptWords.help(3).contains("all 3 lines"))
        #expect(ReviewAcceptWords.undoName(1) == "Accept 1 Reading")
        #expect(ReviewAcceptWords.undoName(5) == "Accept 5 Readings")
    }

    @Test("the request carries the page and the transcription kind under the engine's names")
    func request() throws {
        let object = try #require(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(ReviewAcceptAllRequest(documentId: "p1"))) as? [String: String])
        #expect(object == ["document_id": "p1", "kind": "transcription"])
    }

    @MainActor
    @Test("nothing waiting offers no button; a count does")
    func offered() {
        let client = FicheroClient(libraryPath: nil)
        #expect(!ReviewAcceptStore(client: client, documentId: "p1").isOffered)
        #expect(ReviewAcceptStore(client: client, documentId: "p1", count: 2).isOffered)
    }
}
