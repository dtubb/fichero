import FicheroAPIClient
import Foundation
import XCTest

@testable import Fichero

/// Tolerant-decoding invariant for `CanvasItemDisplay` (#2294/#3082): a single
/// malformed row must never drop the whole canvas item list. An unknown or
/// missing `kind` falls back to `.note`; optional fields decode to nil; only the
/// structurally-required `id`/`folderId` throw. Pure JSON round-trips — no store,
/// no network.
final class CanvasItemDisplayDecodingTests: XCTestCase {

    private func decode(_ json: String) throws -> CanvasItemDisplay {
        try JSONDecoder().decode(CanvasItemDisplay.self, from: Data(json.utf8))
    }

    func testFullRowDecodesEveryField() throws {
        let item = try decode(#"""
        {"id":"i1","folderId":"f1","kind":"link","text":"hi",
         "sourceItemId":"a","targetItemId":"b"}
        """#)
        XCTAssertEqual(item.id, "i1")
        XCTAssertEqual(item.folderId, "f1")
        XCTAssertEqual(item.kind, .link)
        XCTAssertEqual(item.text, "hi")
        XCTAssertEqual(item.sourceItemId, "a")
        XCTAssertEqual(item.targetItemId, "b")
    }

    func testEveryKnownKindDecodes() throws {
        let cases: [(String, Components.Schemas.CanvasItemKind)] = [
            ("note", .note), ("quote", .quote), ("work_note", .workNote),
            ("link", .link), ("text", .text)
        ]
        for (raw, expected) in cases {
            let item = try decode(#"{"id":"i","folderId":"f","kind":"\#(raw)"}"#)
            XCTAssertEqual(item.kind, expected, "raw kind=\(raw)")
        }
    }

    func testUnknownKindFallsBackToNote() throws {
        // The invariant: a kind this client build doesn't know must NOT throw —
        // it degrades to .note so the row (and the whole list) survives.
        let item = try decode(#"{"id":"i","folderId":"f","kind":"sticky_diagram"}"#)
        XCTAssertEqual(item.kind, .note)
    }

    func testMissingKindFallsBackToNote() throws {
        let item = try decode(#"{"id":"i","folderId":"f"}"#)
        XCTAssertEqual(item.kind, .note)
    }

    func testMissingOptionalFieldsDecodeToNil() throws {
        let item = try decode(#"{"id":"i","folderId":"f","kind":"note"}"#)
        XCTAssertNil(item.text)
        XCTAssertNil(item.sourceItemId)
        XCTAssertNil(item.targetItemId)
    }

    func testNullOptionalFieldsDecodeToNil() throws {
        let item = try decode(#"""
        {"id":"i","folderId":"f","kind":"note","text":null,
         "sourceItemId":null,"targetItemId":null}
        """#)
        XCTAssertNil(item.text)
        XCTAssertNil(item.sourceItemId)
        XCTAssertNil(item.targetItemId)
    }

    func testMissingRequiredIdThrows() {
        XCTAssertThrowsError(try decode(#"{"folderId":"f","kind":"note"}"#))
    }

    func testMissingRequiredFolderIdThrows() {
        XCTAssertThrowsError(try decode(#"{"id":"i","kind":"note"}"#))
    }
}
