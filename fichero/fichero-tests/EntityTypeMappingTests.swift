@testable import Fichero
import XCTest

/// Tests for the human-label → backend entity_type id mapping used by
/// the lozenge tap-to-search flow. Daniel: 'when I click on a name, it
/// should find other documents with that person's name' — the mapping
/// is what turns the visible 'People' row label into the backend's
/// 'people' artifact_type so the scoped query `people:<name>` works.
///
/// Lives in `LibraryView+ColumnConfig.swift` as `ArtifactEntitiesView.entityTypeId(for:)`.
final class EntityTypeMappingTests: XCTestCase {

    // MARK: - Standard six types

    func testPeopleMaps() {
        XCTAssertEqual(ArtifactEntitiesView.entityTypeId(for: "People"), "people")
    }

    func testPlacesMaps() {
        XCTAssertEqual(ArtifactEntitiesView.entityTypeId(for: "Places"), "places")
    }

    func testOrganizationsMaps() {
        XCTAssertEqual(
            ArtifactEntitiesView.entityTypeId(for: "Organizations"),
            "organizations"
        )
    }

    func testDatesMaps() {
        XCTAssertEqual(ArtifactEntitiesView.entityTypeId(for: "Dates"), "dates")
    }

    func testEventsMaps() {
        XCTAssertEqual(ArtifactEntitiesView.entityTypeId(for: "Events"), "events")
    }

    func testKeywordsMaps() {
        XCTAssertEqual(
            ArtifactEntitiesView.entityTypeId(for: "Keywords"),
            "keywords"
        )
    }

    // MARK: - Case-insensitivity

    func testCaseInsensitive() {
        XCTAssertEqual(ArtifactEntitiesView.entityTypeId(for: "PEOPLE"), "people")
        XCTAssertEqual(ArtifactEntitiesView.entityTypeId(for: "people"), "people")
        XCTAssertEqual(ArtifactEntitiesView.entityTypeId(for: "PlAcEs"), "places")
    }

    // MARK: - Unknown labels

    func testUnknownLabelFallsBackToLowercased() {
        // Defensive: if a new label appears in the UI we don't crash;
        // we just lower-case it so the scoped query still has a shape.
        XCTAssertEqual(
            ArtifactEntitiesView.entityTypeId(for: "Buildings"),
            "buildings"
        )
    }
}
