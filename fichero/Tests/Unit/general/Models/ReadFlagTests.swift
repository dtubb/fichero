import Foundation
import Testing
@testable import Fichero

@Suite("A page's read flag (#6003)")
struct ReadFlagTests {
    private func document(_ extra: String) throws -> Document {
        let json = """
        {"id":"p1","doc_type":"file","name":"p","status":"completed","metadata":{},
         "created_at":"2026-10-21T10:00:00Z","updated_at":"2026-10-21T10:00:00Z"\(extra)}
        """
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(Document.self, from: Data(json.utf8))
    }

    @Test("a Document with a read_flag gives the note, the Inspector and the row say the same words")
    func flagged() throws {
        let doc = try document(#","read_flag":{"kind":"needs-re-reading","reason":"the repair could not restore its text"}"#)
        #expect(doc.readFlag?.note == "Needs re-reading: the repair could not restore its text")
        #expect(doc.readFlag?.measure == nil)
    }

    @Test("a Document without one gives neither")
    func notFlagged() throws {
        #expect(try document("").readFlag == nil)
        #expect(try document(#","read_flag":null"#).readFlag == nil)
    }

    @Test("another kind shows only its reason, never the kind's id")
    func otherKind() {
        #expect(ReadFlag(kind: "low-confidence", reason: "the line check disagreed", measure: nil).note == "The line check disagreed")
        #expect(!ReadFlag(kind: "low-confidence", reason: "x", measure: nil).note.lowercased().contains("confidence"))
    }

    @Test("an empty reason falls back to a sentence; the first letter is capitalised")
    func emptyAndLowercase() {
        #expect(ReadFlag(kind: "low-confidence", reason: "", measure: nil).note == "This page needs reading again.")
        #expect(ReadFlag(kind: "low-confidence", reason: "  ", measure: nil).note == "This page needs reading again.")
        #expect(ReadFlag(kind: "low-confidence", reason: "the line check disagreed", measure: nil).note == "The line check disagreed")
    }
}
