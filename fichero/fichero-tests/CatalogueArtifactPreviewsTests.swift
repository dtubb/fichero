@testable import Fichero
import XCTest

/// Tests for the pure data-extraction helpers behind the catalogue
/// inspector previews. The SwiftUI view builders themselves aren't
/// executed at test time (they require an attached view hierarchy),
/// but `CatalogueArtifactPreviews.items(from:)` is the shared entry
/// point that every preview uses — if this stays correct, the
/// previews render consistent content.
final class CatalogueArtifactPreviewsTests: XCTestCase {

    func testItemsReturnsEmptyWhenNoData() {
        let result = CatalogueArtifactPreviews.items(from: [:])
        XCTAssertTrue(result.isEmpty)
    }

    func testItemsReturnsEmptyWhenItemsKeyHasWrongType() {
        let data: [String: AnyCodable] = ["items": AnyCodable("not an array")]
        let result = CatalogueArtifactPreviews.items(from: data)
        XCTAssertTrue(result.isEmpty)
    }

    func testItemsDecodesArrayOfDicts() {
        let raw: [[String: Any]] = [
            ["nombre": "Alice", "contexto": "Role A"],
            ["nombre": "Bob", "contexto": "Role B"]
        ]
        let data: [String: AnyCodable] = ["items": AnyCodable(raw)]
        let result = CatalogueArtifactPreviews.items(from: data)
        XCTAssertEqual(result.count, 2)
        XCTAssertEqual(result[0]["nombre"] as? String, "Alice")
        XCTAssertEqual(result[1]["contexto"] as? String, "Role B")
    }
}
