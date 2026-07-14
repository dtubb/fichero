#if os(macOS)
@testable import Fichero
import XCTest

/// The app→engine bookmark wire format (#3747).
///
/// This payload is the ONLY way the sandboxed engine can reach a library in
/// ~/Documents: a dynamic Powerbox grant is not inherited by a child process, so
/// the app must mint security-scoped bookmarks and hand them over at spawn. The
/// format is parsed by `parse_bookmarks()` in `fichero/security_scoped_access.py`,
/// and the two must not drift — hence these tests pin the exact shape.
final class EngineBookmarkPayloadTests: XCTestCase {

    private func decode(_ json: String) throws -> [String: String] {
        let data = try XCTUnwrap(json.data(using: .utf8))
        let object = try JSONSerialization.jsonObject(with: data)
        return try XCTUnwrap(object as? [String: String])
    }

    func testPayloadIsPathToBase64JSON() throws {
        let bookmark = Data("BOOKMARKBYTES".utf8)
        let json = try XCTUnwrap(
            FolderAccessManager.bookmarkPayload(from: ["/Users/d/Documents/L.fichero": bookmark])
        )
        let decoded = try decode(json)
        XCTAssertEqual(decoded["/Users/d/Documents/L.fichero"], bookmark.base64EncodedString())
    }

    /// Round-trips through the same decoding the Python side does: base64 → bytes.
    func testBase64RoundTripsBackToTheOriginalBytes() throws {
        let bookmark = Data([0x00, 0xFF, 0x10, 0x42, 0x7F])  // binary, not text
        let json = try XCTUnwrap(FolderAccessManager.bookmarkPayload(from: ["/lib": bookmark]))
        let encoded = try XCTUnwrap(try decode(json)["/lib"])
        XCTAssertEqual(Data(base64Encoded: encoded), bookmark)
    }

    /// A user can have several libraries open; each needs its own grant, so the
    /// payload is a MAP, not a single bookmark.
    func testEveryLibraryGetsItsOwnEntry() throws {
        let json = try XCTUnwrap(FolderAccessManager.bookmarkPayload(from: [
            "/a.fichero": Data("A".utf8),
            "/b.fichero": Data("B".utf8)
        ]))
        let decoded = try decode(json)
        XCTAssertEqual(decoded.count, 2)
        XCTAssertEqual(decoded["/a.fichero"], Data("A".utf8).base64EncodedString())
        XCTAssertEqual(decoded["/b.fichero"], Data("B".utf8).base64EncodedString())
    }

    /// Nil, not "{}" — the DMG build is not sandboxed and must set no env var at all,
    /// so the engine's no-op path is taken.
    func testNoBookmarksYieldsNilNotEmptyJSON() {
        XCTAssertNil(FolderAccessManager.bookmarkPayload(from: [:]))
    }

    /// Unicode paths must survive the JSON encoding — Daniel's real libraries have them.
    func testUnicodePathSurvives() throws {
        let path = "/Users/d/Documents/Diario de Marshall — año 1897.fichero"
        let json = try XCTUnwrap(FolderAccessManager.bookmarkPayload(from: [path: Data("X".utf8)]))
        XCTAssertEqual(try decode(json)[path], Data("X".utf8).base64EncodedString())
    }
}
#endif
