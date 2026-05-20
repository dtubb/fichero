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
