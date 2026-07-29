@testable import Fichero
import XCTest

/// Tests for the NoteService request bodies (Encodable) + NoteLinks value type.
/// These turn UI intent into the exact wire body the backend expects, so their
/// snake_case key mapping + optional omission is pure logic worth pinning.
final class NoteRequestBodyTests: XCTestCase {

    private func encodeToDict<T: Encodable>(_ value: T) throws -> [String: Any] {
        let data = try JSONEncoder().encode(value)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    // MARK: - NoteCreateBody

    func testNoteCreateBodyEncodesSnakeCaseLinks() throws {
        let body = NoteCreateBody(title: "My Note", body: "text",
                                  linkedDocumentIds: ["d1", "d2"])
        let obj = try encodeToDict(body)
        XCTAssertEqual(obj["title"] as? String, "My Note")
        XCTAssertEqual(obj["body"] as? String, "text")
        XCTAssertEqual(obj["linked_document_ids"] as? [String], ["d1", "d2"])  // ← snake_case
        XCTAssertNil(obj["linkedDocumentIds"])  // camelCase never leaks
    }

    /// A nil title is omitted from the payload (encodeIfPresent), not sent null.
    func testNoteCreateBodyOmitsNilTitle() throws {
        let body = NoteCreateBody(title: nil, body: "text", linkedDocumentIds: [])
        let obj = try encodeToDict(body)
        XCTAssertNil(obj["title"])
        XCTAssertEqual(obj["linked_document_ids"] as? [String], [])
    }

    // MARK: - NoteCreateEntityBody

    func testNoteCreateEntityBodyEncodesSnakeCaseEntityLinks() throws {
        let body = NoteCreateEntityBody(title: "Bio", body: "b", kind: "reference",
                                        linkedEntityIds: ["e1"])
        let obj = try encodeToDict(body)
        XCTAssertEqual(obj["kind"] as? String, "reference")
        XCTAssertEqual(obj["linked_entity_ids"] as? [String], ["e1"])  // ← snake_case
        XCTAssertNil(obj["linkedEntityIds"])
    }

    // MARK: - NoteCreateFreeBody / NotePatchBody

    func testNoteCreateFreeBodyEncodesPlainKeys() throws {
        let body = NoteCreateFreeBody(title: "Free", body: "b", kind: "note")
        let obj = try encodeToDict(body)
        XCTAssertEqual(obj["title"] as? String, "Free")
        XCTAssertEqual(obj["body"] as? String, "b")
        XCTAssertEqual(obj["kind"] as? String, "note")
    }

    func testNotePatchBodyEncodesBodyOnly() throws {
        let obj = try encodeToDict(NotePatchBody(body: "updated"))
        XCTAssertEqual(obj["body"] as? String, "updated")
        XCTAssertEqual(obj.keys.count, 1)
    }

    // MARK: - NoteLinks

    func testNoteLinksEmptyIsEmpty() {
        XCTAssertTrue(NoteLinks.empty.isEmpty)
        XCTAssertEqual(NoteLinks.empty.backlinks.count, 0)
        XCTAssertEqual(NoteLinks.empty.forward.count, 0)
    }
}
