@testable import Fichero
import Foundation
import XCTest

/// Tests for the human-label → backend entity_type id mapping used by
/// the lozenge tap-to-search flow. Daniel: 'when I click on a name, it
/// should find other documents with that person's name' — the mapping
/// is what turns the visible 'People' row label into the backend's
/// 'people' artifact_type so the scoped query `people:<name>` works.
///
/// Lives in `LibraryView+ColumnConfig.swift` as `ArtifactEntitiesView.entityTypeId(for:)`.
@MainActor
final class EntityTypeMappingTests: XCTestCase {

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    private static func repoSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testClaimsAndEntitiesEndpointsAreWired() throws {
        let source = try Self.appSource("Services/ArtifactServiceGenerated.swift")
        let requiredPaths = [
            "/api/claim-links/\\(linkId)",
            "/api/claims/assign-time-period",
            "/api/claims/batch/transition",
            "/api/claims/queues/curated",
            "/api/claims/queues/rejected",
            "/api/claims/queues/shortlisted",
            "/api/claims/queues/unreviewed",
            "/api/claims/resolve-source",
            "/api/claims/\\(claimId)/related",
            "/api/claims/\\(claimId)/transition",
            "/api/classifications",
            "/api/classifications/\\(valueId)",
            "/api/entities/alias-map",
            "/api/entities/claim-counts",
            "/api/entities/digest",
            "/api/entities/resolve/\\(encoded)",
            "/api/entities/top",
            "/api/entities/\\(entityId)/aliases",
            "/api/entities/\\(entityId)/biography",
            "/api/entities/\\(entityId)/co-occurrence",
            "/api/entities/\\(entityId)/documents",
            "/api/entities/\\(entityId)/drill-down"
        ]

        for path in requiredPaths {
            XCTAssertTrue(source.contains(path), "Missing endpoint wiring for \(path)")
        }
    }

    func testMultilingualAndRegistryEndpointsAreWired() throws {
        let source = try Self.appSource("Services/ArtifactServiceGenerated.swift")
        let requiredPaths = [
            "/api/multilingual/claims",
            "/api/multilingual/detect",
            "/api/multilingual/entities",
            "/api/multilingual/entities/search",
            "/api/multilingual/normalize",
            "/api/multilingual/transliterate",
            "/api/registries/claim-kinds",
            "/api/registries/claim-kinds/\\(valueId)",
            "/api/registries/epistemic-statuses",
            "/api/registries/epistemic-statuses/\\(valueId)"
        ]

        for path in requiredPaths {
            XCTAssertTrue(source.contains(path), "Missing endpoint wiring for \(path)")
        }
    }

    func testClaimsEntitiesAllowlistEntriesWereRemoved() throws {
        let allowlist = try Self.repoSource(
            "fichero-engine/tests/contracts/ui_wiring_allowlist_swiftui.json"
        )
        let removedPaths = [
            "/api/claim-links/{link_id}",
            "/api/claims/assign-time-period",
            "/api/entities/digest",
            "/api/multilingual/normalize",
            "/api/registries/epistemic-statuses/{value_id}"
        ]

        for path in removedPaths {
            XCTAssertFalse(
                allowlist.contains("\"\(path)\""),
                "Endpoint should no longer be allowlisted: \(path)"
            )
        }
    }

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
