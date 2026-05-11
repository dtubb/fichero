@testable import Fichero
import XCTest

/// Tests for the `Note` model — annotation attached to a Document or
/// Artifact, optionally with a bounding box for image highlights.
final class NoteTests: XCTestCase {

    // MARK: - init defaults

    func testInitFillsDefaults() {
        let n = Note(targetType: "Document", targetId: "doc-1", content: "hello")
        XCTAssertFalse(n.id.isEmpty)
        XCTAssertEqual(n.noteType, "comment")  // default
        XCTAssertNil(n.bbox)
        XCTAssertFalse(n.hasPosition)
    }

    // MARK: - JSON round-trip

    func testEncodeDecodeRoundTrip() throws {
        let original = Note(
            id: "n1",
            targetType: "Artifact",
            targetId: "a1",
            content: "needs review",
            noteType: "flag",
            bbox: [10, 20, 100, 200]
        )
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(Note.self, from: data)
        XCTAssertEqual(decoded.id, "n1")
        XCTAssertEqual(decoded.targetType, "Artifact")
        XCTAssertEqual(decoded.targetId, "a1")
        XCTAssertEqual(decoded.content, "needs review")
        XCTAssertEqual(decoded.noteType, "flag")
        XCTAssertEqual(decoded.bbox, [10, 20, 100, 200])
    }

    func testDecodesPythonSnakeCase() throws {
        let json = """
        {
            "id": "n1",
            "target_type": "Document",
            "target_id": "d1",
            "content": "question about this",
            "note_type": "question",
            "bbox": null,
            "created_at": "2026-05-10T10:00:00Z",
            "updated_at": "2026-05-10T10:00:00Z"
        }
        """.data(using: .utf8)!
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let n = try decoder.decode(Note.self, from: json)
        XCTAssertEqual(n.targetType, "Document")
        XCTAssertEqual(n.noteType, "question")
        XCTAssertNil(n.bbox)
    }

    // MARK: - NoteType enum

    func testNoteTypeDisplayName() {
        XCTAssertEqual(Note.NoteType.comment.displayName, "Comment")
        XCTAssertEqual(Note.NoteType.question.displayName, "Question")
        XCTAssertEqual(Note.NoteType.flag.displayName, "Flag")
        XCTAssertEqual(Note.NoteType.correction.displayName, "Correction")
    }

    func testNoteTypeIcon() {
        XCTAssertEqual(Note.NoteType.comment.icon, "text.bubble")
        XCTAssertEqual(Note.NoteType.question.icon, "questionmark.circle")
        XCTAssertEqual(Note.NoteType.flag.icon, "flag")
        XCTAssertEqual(Note.NoteType.correction.icon, "pencil.circle")
    }

    func testNoteTypeColor() {
        XCTAssertEqual(Note.NoteType.comment.color, "blue")
        XCTAssertEqual(Note.NoteType.question.color, "orange")
        XCTAssertEqual(Note.NoteType.flag.color, "red")
        XCTAssertEqual(Note.NoteType.correction.color, "green")
    }

    func testNoteTypeAllCases() {
        XCTAssertEqual(Note.NoteType.allCases.count, 4)
    }

    // MARK: - Instance helpers

    func testDisplayNameForKnownType() {
        let n = Note(targetType: "Document", targetId: "d", content: "hi", noteType: "flag")
        XCTAssertEqual(n.noteTypeDisplayName, "Flag")
    }

    func testDisplayNameFallsBackToCapitalised() {
        let n = Note(
            targetType: "Document", targetId: "d", content: "hi",
            noteType: "unusual"
        )
        XCTAssertEqual(n.noteTypeDisplayName, "Unusual")
    }

    func testIconForUnknownTypeFallsBack() {
        let n = Note(
            targetType: "Document", targetId: "d", content: "hi",
            noteType: "no-such-type"
        )
        XCTAssertEqual(n.noteTypeIcon, "note.text")
    }

    func testColorForUnknownTypeFallsBack() {
        let n = Note(
            targetType: "Document", targetId: "d", content: "hi",
            noteType: "no-such-type"
        )
        XCTAssertEqual(n.noteTypeColor, "gray")
    }

    // MARK: - hasPosition + target type predicates

    func testHasPosition() {
        let with = Note(
            targetType: "Document", targetId: "d", content: "hi",
            bbox: [0, 0, 50, 50]
        )
        let without = Note(targetType: "Document", targetId: "d", content: "hi")
        XCTAssertTrue(with.hasPosition)
        XCTAssertFalse(without.hasPosition)
    }

    func testIsDocumentNote() {
        let doc = Note(targetType: "Document", targetId: "d", content: "hi")
        let art = Note(targetType: "Artifact", targetId: "a", content: "hi")
        XCTAssertTrue(doc.isDocumentNote)
        XCTAssertFalse(art.isDocumentNote)
    }

    func testIsArtifactNote() {
        let doc = Note(targetType: "Document", targetId: "d", content: "hi")
        let art = Note(targetType: "Artifact", targetId: "a", content: "hi")
        XCTAssertFalse(doc.isArtifactNote)
        XCTAssertTrue(art.isArtifactNote)
    }
}
