// swiftlint:disable type_body_length function_body_length
@testable import Fichero
import Foundation
import XCTest

/// Tests for the human-label → backend entity_type id mapping used by
/// the lozenge tap-to-search flow. The user: 'when I click on a name, it
/// should find other documents with that person's name' — the mapping
/// is what turns the visible 'People' row label into the backend's
/// 'people' artifact_type so the scoped query `people:<name>` works.
///
/// Lives in `LibraryView+ColumnConfig.swift` as `ArtifactEntitiesView.entityTypeId(for:)`.
@MainActor
final class EntityTypeMappingTests: XCTestCase {

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    private static func repoSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    // #4024: ArtifactService.swift's endpoint-calling methods were split out
    // into EntityService.swift (core) + EntityService+*.swift extension
    // files. Concatenate the whole family so endpoint-wiring assertions see
    // all call sites regardless of which extension a method now lives in.
    private static func entityServiceSource() throws -> String {
        // #4024: literal appSource(...) calls (not interpolated) so the
        // appSource-path guardrail can statically verify each split file exists.
        return try [
            Self.appSource("Services/EntityService.swift"),
            Self.appSource("Services/EntityService+Bibliography.swift"),
            Self.appSource("Services/EntityService+CitationGraph.swift"),
            Self.appSource("Services/EntityService+ClaimEntityCRUD.swift"),
            Self.appSource("Services/EntityService+Claims.swift"),
            Self.appSource("Services/EntityService+DocumentMetadata.swift"),
            Self.appSource("Services/EntityService+Entities.swift"),
            Self.appSource("Services/EntityService+EntityCuration.swift"),
            Self.appSource("Services/EntityService+KnowledgeGraph.swift")
        ].joined(separator: "\n")
    }

    func testClaimsAndEntitiesEndpointsAreWired() throws {
        let source = try Self.entityServiceSource()
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
            // /api/entities/digest is consumed by the WebKit document view, not a
            // native Swift call site (#3765) — it stays allowlisted, not wired.
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
        let source = try Self.entityServiceSource()
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
        // NB: /api/entities/digest is intentionally still allowlisted (WebKit
        // document view consumes it; no native Swift call site — #3765).
        let removedPaths = [
            "/api/claim-links/{link_id}",
            "/api/claims/assign-time-period",
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

    /// The hermeneutics surface is deferred backlog ("baseline: not yet wired"
    /// in the CI wiring contract) — there is no native Swift call site yet.
    /// This locks that documented deferral: the endpoints must stay in the
    /// not-yet-wired allowlist. When the surface is built, wire it in
    /// ArtifactService AND drop these from the allowlist together.
    func testHermeneuticsEndpointsRemainDeferred() throws {
        let allowlist = try Self.repoSource(
            "fichero-engine/tests/contracts/ui_wiring_allowlist_swiftui.json"
        )
        let deferredPaths = [
            "/api/hermeneutics/circle-state",
            "/api/hermeneutics/circle-state/{state_id}",
            "/api/hermeneutics/circle-state/{state_id}/backtrack",
            "/api/hermeneutics/circle-state/{state_id}/navigate",
            // /api/hermeneutics/frameworks + /interpretations are WIRED in
            // ArtifactService (native call sites), so they are correctly
            // absent from the allowlist — only the collection-level frameworks/{id}
            // and the rest below remain deferred.
            "/api/hermeneutics/frameworks/{framework_id}",
            "/api/hermeneutics/patterns",
            "/api/hermeneutics/patterns/{pattern_id}",
            "/api/hermeneutics/patterns/{pattern_id}/claims/{claim_id}",
            // /suggestions was a permanent-501 stub — DELETED in the
            // 2026-07-27 endpoint cleanup, so it no longer appears here.
            "/api/hermeneutics/taxonomy/methods"
        ]

        for path in deferredPaths {
            XCTAssertTrue(
                allowlist.contains("\"\(path)\""),
                "Deferred endpoint should stay allowlisted until wired: \(path)"
            )
        }
    }

    func testKnowledgeGraphCoreEndpointsAreWired() throws {
        let source = try Self.entityServiceSource()
        let requiredPaths = [
            "/api/kg/entities/\\(entityId)/bio",
            "/api/kg/entity-curation/candidates",
            "/api/kg/graph/centrality",
            "/api/kg/graph/clustering",
            "/api/kg/graph/communities",
            "/api/kg/graph/components",
            "/api/kg/graph/cooccurrence/\\(entityId)",
            "/api/kg/graph/metrics",
            "/api/kg/graph/pagerank",
            "/api/kg/graph/path",
            "/api/kg/graph/similar/\\(entityId)",
            "/api/kg/graph/traverse/\\(entityId)",
            "/api/kg/graph/triangles/\\(entityId)",
            "/api/kg/inclusion",
            "/api/kg/mutations",
            "/api/kg/mutations/\\(mutationId)/undo",
            "/api/kg/predictions/\\(runId)/apply",
            "/api/kg/rebuild",
            "/api/kg/render/paragraph",
            "/api/kg/reset",
            "/api/kg/search",
            "/api/kg/sparql",
            "/api/kg/triangulation",
            "/api/kg/triangulation/entity/\\(entityId)",
            "/api/kg/triangulation/recompute"
        ]

        for path in requiredPaths {
            XCTAssertTrue(source.contains(path), "Missing endpoint wiring for \(path)")
        }
    }

    /// The /api/kg/interpretations/* alias mount (same router mounted twice,
    /// #1126) was DELETED in the 2026-07-27 endpoint cleanup — 13 duplicate
    /// spec paths with zero callers. /api/hermeneutics/* is the one URL.
    /// Lock the deletion: the alias must never reappear in the allowlist,
    /// which would mean the duplicate mount came back.
    func testKnowledgeGraphInterpretationAliasStaysDeleted() throws {
        let allowlist = try Self.repoSource(
            "fichero-engine/tests/contracts/ui_wiring_allowlist_swiftui.json"
        )
        XCTAssertFalse(
            allowlist.contains("/api/kg/interpretations"),
            "The kg/interpretations alias mount was deleted — it must not return"
        )
    }

    func testKnowledgeGraphPredictionAndReviewEndpointsAreWired() throws {
        let source = try Self.entityServiceSource()
        let requiredPaths = [
            "/api/kg/pykeen/models/\\(modelId)",
            "/api/kg/pykeen/predict/\\(entityId)",
            "/api/kg/pykeen/stored",
            "/api/kg/pykeen/stored/\\(predictionId)",
            "/api/kg/pykeen/stored/\\(predictionId)/verify",
            "/api/kg/pykeen/train",
            "/api/kg/pykeen/training-jobs",
            "/api/kg/pykeen/training-jobs/\\(modelId)",
            "/api/kg/review/graph-candidates",
            "/api/kg/review/labels",
            "/api/kg/review/pairs",
            "/api/kg/review/pairs/\\(pairId)/accept",
            "/api/kg/review/pairs/\\(pairId)/reject"
        ]

        for path in requiredPaths {
            XCTAssertTrue(source.contains(path), "Missing endpoint wiring for \(path)")
        }
    }

    func testKnowledgeGraphAllowlistEntriesWereRemoved() throws {
        let allowlist = try Self.repoSource(
            "fichero-engine/tests/contracts/ui_wiring_allowlist_swiftui.json"
        )
        let removedPaths = [
            "/api/kg/entities/{entity_id}/bio",
            "/api/kg/entity-curation/candidates",
            "/api/kg/graph/centrality",
            "/api/kg/graph/clustering",
            "/api/kg/graph/communities",
            "/api/kg/graph/components",
            "/api/kg/graph/cooccurrence/{entity_id}",
            "/api/kg/graph/metrics",
            "/api/kg/graph/pagerank",
            "/api/kg/graph/path",
            "/api/kg/graph/similar/{entity_id}",
            "/api/kg/graph/traverse/{entity_id}",
            "/api/kg/graph/triangles/{entity_id}",
            "/api/kg/inclusion",
            // /api/kg/interpretations/* stay allowlisted (deferred backlog) —
            // see testKnowledgeGraphInterpretationEndpointsRemainDeferred.
            "/api/kg/mutations",
            "/api/kg/mutations/{mutation_id}/undo",
            "/api/kg/predictions/{run_id}/apply",
            "/api/kg/pykeen/models/{model_id}",
            "/api/kg/pykeen/predict/{entity_id}",
            "/api/kg/pykeen/stored",
            "/api/kg/pykeen/stored/{prediction_id}",
            "/api/kg/pykeen/stored/{prediction_id}/verify",
            "/api/kg/pykeen/train",
            "/api/kg/pykeen/training-jobs",
            "/api/kg/pykeen/training-jobs/{model_id}",
            "/api/kg/rebuild",
            "/api/kg/render/paragraph",
            "/api/kg/reset",
            "/api/kg/review/graph-candidates",
            "/api/kg/review/labels",
            "/api/kg/review/pairs",
            "/api/kg/review/pairs/{pair_id}/accept",
            "/api/kg/review/pairs/{pair_id}/reject",
            "/api/kg/search",
            "/api/kg/sparql",
            "/api/kg/triangulation",
            "/api/kg/triangulation/entity/{entity_id}",
            "/api/kg/triangulation/recompute"
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
// swiftlint:enable type_body_length function_body_length
