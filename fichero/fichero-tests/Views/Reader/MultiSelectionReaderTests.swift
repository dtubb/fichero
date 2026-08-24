@testable import Fichero
import Testing

// The multi-selection reader fetches ONLY what the listing snapshot lacks —
// text already in hand is rendered immediately and never re-fetched.
struct MultiSelectionReaderTests {
    @Test("only documents without text in hand are fetched")
    func missingTextIds() {
        let docs = [
            Document(id: "a", name: "A", pageContent: "some transcript"),
            Document(id: "b", name: "B", pageContent: ""),
            Document(id: "c", name: "C")
        ]
        #expect(multiReaderMissingTextIds(docs) == ["b", "c"])
    }

    @Test("a fully-loaded selection fetches nothing")
    func nothingMissing() {
        let docs = [
            Document(id: "a", name: "A", pageContent: "x"),
            Document(id: "b", name: "B", pageContent: "y")
        ]
        #expect(multiReaderMissingTextIds(docs).isEmpty)
    }
}
