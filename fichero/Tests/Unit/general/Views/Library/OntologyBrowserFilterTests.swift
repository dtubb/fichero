@testable import Fichero
import FicheroAPIClient
import Foundation
import XCTest

/// Tests for the pure filter helpers on OntologyBrowser (#498). Locks
/// the @AppStorage CSV parser and the kind-filter rule so the chip-row
/// UI never silently drops or keeps the wrong entities.
@MainActor
final class OntologyBrowserFilterTests: XCTestCase {

    // MARK: - parseHiddenKinds (CSV parser)

    func testParseEmptyStringReturnsEmptySet() {
        XCTAssertTrue(OntologyBrowser.parseHiddenKinds("").isEmpty)
    }

    func testParseSingleKindReturnsOneElement() {
        let result = OntologyBrowser.parseHiddenKinds("person")
        XCTAssertEqual(result, ["person"])
    }

    func testParseMultipleCommaSeparated() {
        let result = OntologyBrowser.parseHiddenKinds("person,location,event")
        XCTAssertEqual(result, ["person", "location", "event"])
    }

    func testParseSkipsEmptySegments() {
        // Defensive: a leading/trailing/double comma shouldn't introduce
        // empty strings in the set (which would shadow a real "" kind).
        let result = OntologyBrowser.parseHiddenKinds(",person,,event,")
        XCTAssertEqual(result, ["person", "event"])
    }

    // MARK: - filterEntities

    func testFilterEntitiesEmptyHiddenReturnsAll() {
        let entities = [makeEntity(id: "1", type: .person)]
        let result = OntologyBrowser.filterEntities(entities, hidden: [])
        XCTAssertEqual(result.count, 1)
    }

    func testFilterEntitiesDropsHiddenKind() {
        let entities = [
            makeEntity(id: "1", type: .person),
            makeEntity(id: "2", type: .location),
            makeEntity(id: "3", type: .event)
        ]
        let result = OntologyBrowser.filterEntities(entities, hidden: ["person"])
        XCTAssertEqual(result.map(\.id), ["2", "3"])
    }

    func testFilterEntitiesMultipleHidden() {
        let entities = [
            makeEntity(id: "1", type: .person),
            makeEntity(id: "2", type: .location),
            makeEntity(id: "3", type: .event)
        ]
        let result = OntologyBrowser.filterEntities(
            entities, hidden: ["person", "location"]
        )
        XCTAssertEqual(result.map(\.id), ["3"])
    }

    func testFilterEntitiesNilTypeTreatedAsOther() {
        // KnowledgeEntity.entityType is optional in the OpenAPI schema —
        // when nil, we treat it as 'other' for filtering purposes.
        let entities = [makeEntity(id: "x", type: nil)]
        let withOtherHidden = OntologyBrowser.filterEntities(entities, hidden: ["other"])
        XCTAssertTrue(withOtherHidden.isEmpty)

        let withPersonHidden = OntologyBrowser.filterEntities(entities, hidden: ["person"])
        XCTAssertEqual(withPersonHidden.count, 1)  // nil ≠ person
    }

    func testFilterEntitiesHidingAllReturnsEmpty() {
        let entities = [
            makeEntity(id: "1", type: .person),
            makeEntity(id: "2", type: .location)
        ]
        let result = OntologyBrowser.filterEntities(
            entities, hidden: ["person", "location", "organization", "event", "concept", "other"]
        )
        XCTAssertTrue(result.isEmpty)
    }

    // MARK: - OCR garbage heuristics

    func testIsOcrGarbageRejectsSingleCharacter() {
        XCTAssertTrue(OntologyBrowser.isOcrGarbage("x"))
    }

    func testIsOcrGarbageRejectsNumericOnly() {
        XCTAssertTrue(OntologyBrowser.isOcrGarbage("12345"))
    }

    func testIsOcrGarbageAcceptsNormalName() {
        XCTAssertFalse(OntologyBrowser.isOcrGarbage("Eugenio Córdoba"))
    }

    func testIsOcrGarbageRejectsTimestampFormat() {
        // "12:10" is the exact pattern reported in #2482 — pure digits + colon, zero letters.
        XCTAssertTrue(OntologyBrowser.isOcrGarbage("12:10"))
    }

    func testIsOcrGarbageRejectsBboxFragment() {
        XCTAssertTrue(OntologyBrowser.isOcrGarbage("0.42:0.87"))
    }

    func testIsOcrGarbageAcceptsAlphanumericMix() {
        // Names like "Section 12" or "COVID-19" contain letters and must not be filtered.
        XCTAssertFalse(OntologyBrowser.isOcrGarbage("Section 12"))
        XCTAssertFalse(OntologyBrowser.isOcrGarbage("COVID-19"))
    }

    // MARK: - Truncation warning

    func testTruncationMessageHiddenBelowCap() {
        XCTAssertNil(OntologyBrowser.truncationMessage(entityCount: 99, searchText: ""))
    }

    func testTruncationMessageWarnsForUnfilteredListAtCap() {
        XCTAssertEqual(
            OntologyBrowser.truncationMessage(entityCount: 100, searchText: ""),
            "Showing the first 100 entities. Refine the list to narrow the graph."
        )
    }

    func testTruncationMessageWarnsForSearchResultsAtCap() {
        XCTAssertEqual(
            OntologyBrowser.truncationMessage(entityCount: 100, searchText: "paris"),
            "Showing the first 100 matching entities. Refine the search to narrow the list."
        )
    }

    // MARK: - EntityRow display-label fallback

    func testEntityRowFallbackForEmptyCanonicalName() {
        // An entity with an empty canonicalName must not render as blank — it
        // should fall back to a type+id hint. We verify via EntityRow's
        // displayLabel property (tested via the OntologyBrowser's isOcrGarbage
        // heuristic since the route now blocks storing garbage names, but
        // pre-existing rows in the DB may still have empty names).
        let entity = Components.Schemas.KnowledgeEntity(
            id: "abc123",
            canonicalName: "",
            entityType: .person,
            aliases: [],
            description: nil,
            language: nil,
            metadata: nil,
            mergedIntoId: nil,
            createdAt: Date(),
            updatedAt: Date()
        )
        // EntityRow.displayLabel: empty name → falls back to "person ·abc123"
        let row = EntityRow(entity: entity, claimCount: 0, style: .browser)
        XCTAssertEqual(row.displayLabelForTesting, "person ·abc123")
    }

    func testEntityRowPassesThroughCleanName() {
        let entity = Components.Schemas.KnowledgeEntity(
            id: "e1",
            canonicalName: "María García",
            entityType: .person,
            aliases: [],
            description: nil,
            language: nil,
            metadata: nil,
            mergedIntoId: nil,
            createdAt: Date(),
            updatedAt: Date()
        )
        let row = EntityRow(entity: entity, claimCount: 0, style: .browser)
        XCTAssertEqual(row.displayLabelForTesting, "María García")
    }

    // MARK: - Helpers

    private func makeEntity(
        id: String,
        type: Components.Schemas.EntityTypeOutput?
    ) -> Components.Schemas.KnowledgeEntity {
        Components.Schemas.KnowledgeEntity(
            id: id,
            canonicalName: "Entity \(id)",
            entityType: type,
            aliases: [],
            description: nil,
            language: nil,
            metadata: nil,
            mergedIntoId: nil,
            createdAt: Date(),
            updatedAt: Date()
        )
    }
}
