import Foundation
import XCTest

@testable import Fichero

/// `SpatialLibraryProjector.project` promises, in its own doc comment, that the
/// same input yields the same output "including positions", and that index
/// order is documents first then entities so appending a document never
/// reshuffles the ones already placed.
///
/// Nothing asserted that. These tests exist because #4353 split `project` into
/// `documentNodes` / `entityNodes` / `links`, and a phyllotaxis layout is
/// exactly the kind of thing a refactor can perturb silently — every position
/// still looks plausible, just not the one it was before.
///
/// Named for what it covers rather than for the type under test: the Swift
/// Testing suite in `Services/MindPalaceLinkTypeTests.swift` already owned
/// `SpatialLibraryProjectorTests`, and two files claiming one name compiled
/// individually while the target could not build at all.
final class SpatialLibraryProjectorGeometryTests: XCTestCase {

    private func input(documents: Int, entities: Int, claims: [SpatialLibraryInput.Claim] = [])
        -> SpatialLibraryInput {
        SpatialLibraryInput(
            documents: (0..<documents).map {
                SpatialLibraryInput.Document(id: "d\($0)", name: "Doc \($0)", parentId: nil)
            },
            entities: (0..<entities).map {
                SpatialLibraryInput.Entity(id: "e\($0)", canonicalName: "Entity \($0)", entityType: nil)
            },
            claims: claims
        )
    }

    // MARK: - Determinism

    func testProjectionIsDeterministicIncludingPositions() {
        let source = input(documents: 12, entities: 7)
        let first = SpatialLibraryProjector.project(source)
        let second = SpatialLibraryProjector.project(source)

        XCTAssertEqual(first.nodes, second.nodes, "same input must yield identical nodes")
        XCTAssertEqual(first.links, second.links, "same input must yield identical links")
    }

    // MARK: - Index order is a contract

    func testDocumentsAreEmittedBeforeEntities() {
        let projection = SpatialLibraryProjector.project(input(documents: 3, entities: 2))
        let kinds = projection.nodes.map(\.nodeType)

        XCTAssertEqual(kinds, [.source, .source, .source, .entity, .entity])
    }

    func testAppendingADocumentDoesNotMoveTheEntitiesAlreadyPlaced() {
        // The whole point of "documents first, then entities" is that growth at
        // the end is additive. Entity positions depend on the entity count, so
        // this pins document growth specifically.
        let before = SpatialLibraryProjector.project(input(documents: 4, entities: 3))
        let after = SpatialLibraryProjector.project(input(documents: 5, entities: 3))

        let beforeDocs = before.nodes.filter { $0.nodeType == .source }
        let afterDocs = after.nodes.filter { $0.nodeType == .source }

        XCTAssertEqual(afterDocs.count, beforeDocs.count + 1)
        // Documents 0..3 keep their exact coordinates; only the new one is added.
        for (old, new) in zip(beforeDocs, afterDocs) {
            XCTAssertEqual(old.id, new.id)
            XCTAssertEqual(old.positionX, new.positionX, accuracy: 1e-12, "doc \(old.id) x moved")
            XCTAssertEqual(old.positionZ, new.positionZ, accuracy: 1e-12, "doc \(old.id) z moved")
        }
    }

    // MARK: - Layer separation

    func testDocumentsSitOnTheBasePlaneAndEntitiesAreRaised() {
        let projection = SpatialLibraryProjector.project(input(documents: 3, entities: 3))

        for node in projection.nodes where node.nodeType == .source {
            XCTAssertEqual(node.positionY, 0, "documents lie on the base plane")
        }
        for node in projection.nodes where node.nodeType == .entity {
            XCTAssertGreaterThanOrEqual(node.positionY, 1.2, "entities are raised above the docs")
        }
    }

    // MARK: - Links

    func testParentChildLinkOnlyWhenTheParentIsPresent() {
        let withParent = SpatialLibraryInput(
            documents: [
                SpatialLibraryInput.Document(id: "parent", name: "Parent", parentId: nil),
                SpatialLibraryInput.Document(id: "child", name: "Child", parentId: "parent")
            ],
            entities: [],
            claims: []
        )
        XCTAssertEqual(SpatialLibraryProjector.project(withParent).links.count, 1)

        // A parent outside the projected set must not produce a dangling link.
        let danglingParent = SpatialLibraryInput(
            documents: [SpatialLibraryInput.Document(id: "child", name: "Child", parentId: "absent")],
            entities: [],
            claims: []
        )
        XCTAssertTrue(SpatialLibraryProjector.project(danglingParent).links.isEmpty)
    }

    func testClaimLinksIgnoreEntitiesThatAreNotProjected() {
        let claim = SpatialLibraryInput.Claim(
            id: "c0",
            predicateVerb: "mentions",
            sourceDocumentId: "d0",
            entityIds: ["e0", "ghost"]
        )
        let projection = SpatialLibraryProjector.project(input(documents: 1, entities: 1, claims: [claim]))

        XCTAssertFalse(projection.links.isEmpty, "the present entity still links")
        for link in projection.links {
            XCTAssertFalse(
                link.sourceId.contains("ghost") || link.targetId.contains("ghost"),
                "an unprojected entity must never appear in a link"
            )
        }
    }

    func testEmptyInputProjectsNothing() {
        let projection = SpatialLibraryProjector.project(input(documents: 0, entities: 0))
        XCTAssertTrue(projection.isEmpty)
        XCTAssertTrue(projection.links.isEmpty)
    }
}
