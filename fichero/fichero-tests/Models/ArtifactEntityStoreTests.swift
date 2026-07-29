@testable import Fichero
import XCTest

/// Covers the parsing logic moved out of `ArtifactEntitiesView` /
/// `ArtifactEntityCell` into the shared `ArtifactEntityStore` (#3861). The N+1
/// fix hinges on `parse` producing the SAME per-type name lists the views used
/// to build inline, so a document visible as a row + up to six type cells reads
/// one shared bundle instead of firing seven `getArtifacts()` calls.
@MainActor
final class ArtifactEntityStoreTests: XCTestCase {
    private func artifact(_ type: String, data: [String: AnyCodable]) -> Artifact {
        Artifact(documentId: "d1", artifactType: type, data: data)
    }

    func testParseMapsEachEntityTypeToItsField() {
        let artifacts = [
            artifact("people", data: ["items": AnyCodable([["name": "Alice"], ["name": "Bob"]])]),
            artifact("places", data: ["items": AnyCodable([["name": "Quibdó"]])]),
            artifact("organizations", data: ["items": AnyCodable([["name": "ACME"]])]),
            artifact("events", data: ["items": AnyCodable([["event": "Flood"]])]),
            artifact("keywords", data: ["keywords": AnyCodable(["war", "peace"])]),
            artifact("dates", data: ["items": AnyCodable([["date_normalized": "1990-01-02"], ["date": "raw"]])])
        ]

        let bundle = ArtifactEntityStore.parse(artifacts)

        XCTAssertEqual(bundle.people, ["Alice", "Bob"])
        XCTAssertEqual(bundle.places, ["Quibdó"])
        XCTAssertEqual(bundle.organizations, ["ACME"])
        XCTAssertEqual(bundle.events, ["Flood"])
        XCTAssertEqual(bundle.keywords, ["war", "peace"])
        // Dates prefer date_normalized, fall back to date.
        XCTAssertEqual(bundle.dates, ["1990-01-02", "raw"])
        XCTAssertFalse(bundle.isEmpty)
    }

    func testParseOfNoEntityArtifactsIsEmpty() {
        // A non-entity artifact type (e.g. transcription) contributes nothing.
        let bundle = ArtifactEntityStore.parse([artifact("transcription", data: [:])])
        XCTAssertTrue(bundle.isEmpty)
        XCTAssertEqual(bundle.people, [])
    }

    func testNamesForEntityTypeMatchesTheParsedField() {
        let bundle = ArtifactEntityStore.parse([
            artifact("people", data: ["items": AnyCodable([["name": "Alice"]])]),
            artifact("keywords", data: ["keywords": AnyCodable(["war"])])
        ])
        // The per-column table cell reads through names(for:) — it must agree
        // with the multiLine row's per-field reads.
        XCTAssertEqual(bundle.names(for: "people"), ["Alice"])
        XCTAssertEqual(bundle.names(for: "keywords"), ["war"])
        XCTAssertEqual(bundle.names(for: "places"), [])
        XCTAssertEqual(bundle.names(for: "unknown"), [])
    }
}
