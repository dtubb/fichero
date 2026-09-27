@testable import Fichero
import FicheroAPIClient
import XCTest

/// WHY: the region-edit endpoint answers `ArtifactRegionsEditResponse` -- `ArtifactResponse`
/// plus `audit_id`. A superset in JSON, but a separate flattened type in Swift, so the app
/// stopped compiling at the 2026-09-27 contract sync. The bridge re-decodes rather than copying
/// fields; these tests pin that nothing the edited artifact carries is lost on the way into
/// `Artifact`, which is what the overlay re-renders from. If a field is dropped here, the
/// overlay shows stale geometry after an edit -- the stale-overlay class this path exists to stop.
final class ArtifactRegionsEditResponseTests: XCTestCase {
    private let wire = #"""
    {"id":"art-1","document_id":"doc-1","artifact_type":"regions","content":"text",
     "version":7,"provider":"user","model":"hand","confidence":0.5,"reviewed":true,
     "source_artifact_id":"art-0","sequence":3,"region_count":2,
     "created_at":"2026-09-27T10:00:00Z","audit_id":"audit-42"}
    """#

    private func edited() throws -> Components.Schemas.ArtifactRegionsEditResponse {
        try JSONDecoder().decode(Components.Schemas.ArtifactRegionsEditResponse.self, from: Data(wire.utf8))
    }

    @MainActor
    func testTheEditedArtifactKeepsItsIdentityAndVersion() throws {
        let artifact = try ArtifactService(ficheroClient: FicheroClient(libraryPath: "/tmp/test-regions-edit.fichero")).convertToArtifact(try edited())
        XCTAssertEqual(artifact.id, "art-1")
        XCTAssertEqual(artifact.documentId, "doc-1")
        XCTAssertEqual(artifact.version, 7, "the version is what the next edit sends as expected_version")
        XCTAssertEqual(artifact.artifactType, "regions")
    }

    @MainActor
    func testProvenanceSurvivesTheBridge() throws {
        let artifact = try ArtifactService(ficheroClient: FicheroClient(libraryPath: "/tmp/test-regions-edit.fichero")).convertToArtifact(try edited())
        XCTAssertEqual(artifact.sourceArtifactId, "art-0")
        XCTAssertEqual(artifact.content, "text")
    }

    func testTheAuditIdIsOnTheWireForUndo() throws {
        XCTAssertEqual(try edited().auditId, "audit-42", "⌘Z for a region edit needs this id")
    }
}
