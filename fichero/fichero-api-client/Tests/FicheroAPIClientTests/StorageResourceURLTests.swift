import XCTest
@testable import FicheroAPIClient

/// Headless coverage for the `fichero-res://` URL builder/parser — the pure
/// core that every storage-resource adapter (URLProtocol / WKURLSchemeHandler /
/// AVAssetResourceLoaderDelegate) shares. No networking, no app types.
final class StorageResourceURLTests: XCTestCase {

    // MARK: - make

    func testMakeProducesSchemeHostPathAndToken() {
        let url = StorageResourceURL.make(kind: .thumbnail, documentId: "abc123", token: "c1")
        XCTAssertEqual(url.scheme, "fichero-res")
        XCTAssertEqual(url.host, "thumbnail")
        XCTAssertEqual(url.path, "/abc123")
        XCTAssertTrue(url.absoluteString.contains("c=c1"))
    }

    func testMakeUsesKindAsHostForEachKind() {
        XCTAssertEqual(StorageResourceURL.make(kind: .display, documentId: "d", token: "t").host, "display")
        XCTAssertEqual(StorageResourceURL.make(kind: .source, documentId: "d", token: "t").host, "source")
    }

    // MARK: - round-trip

    func testRoundTripForEveryKind() {
        for kind in StorageResourceKind.allCases {
            let url = StorageResourceURL.make(kind: kind, documentId: "doc-\(kind.rawValue)", token: "tok")
            let parsed = StorageResourceURL.parse(url)
            XCTAssertEqual(parsed, .init(kind: kind, documentId: "doc-\(kind.rawValue)", token: "tok"))
        }
    }

    func testRoundTripPreservesReservedCharactersInDocumentId() {
        // Document ids are normally content hashes, but the encoding must be
        // lossless even for reserved characters so nothing silently corrupts.
        let tricky = "a b/c?d#e"
        let url = StorageResourceURL.make(kind: .source, documentId: tricky, token: "c9")
        let parsed = StorageResourceURL.parse(url)
        XCTAssertEqual(parsed?.documentId, tricky)
        XCTAssertEqual(parsed?.token, "c9")
    }

    // MARK: - parse rejection

    func testParseRejectsForeignScheme() {
        XCTAssertNil(StorageResourceURL.parse(URL(string: "https://127.0.0.1:8765/api/storage/thumbnail/x")!))
    }

    func testParseRejectsUnknownKind() {
        XCTAssertNil(StorageResourceURL.parse(URL(string: "fichero-res://bogus/doc?c=t")!))
    }

    func testParseRejectsMissingToken() {
        XCTAssertNil(StorageResourceURL.parse(URL(string: "fichero-res://thumbnail/doc")!))
    }

    func testParseRejectsEmptyDocumentId() {
        XCTAssertNil(StorageResourceURL.parse(URL(string: "fichero-res://thumbnail/?c=t")!))
    }
}
