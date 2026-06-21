@testable import Fichero
import XCTest

/// Tests for the `Artifact` model — JSON round-trip with Python's
/// snake_case keys, defaults, type helpers (is*, displayName, icon).
/// Artifact is one of the most-touched models in the inspector flow,
/// so coverage here protects every artifact-rendering code path.
final class ArtifactTests: XCTestCase {

    // MARK: - init defaults

    func testInitFillsDefaults() {
        let a = Artifact(documentId: "doc-1", artifactType: "transcription")
        XCTAssertFalse(a.id.isEmpty)              // UUID generated
        XCTAssertEqual(a.documentId, "doc-1")
        XCTAssertEqual(a.artifactType, "transcription")
        XCTAssertEqual(a.version, 1)
        XCTAssertNil(a.content)
        XCTAssertNil(a.data)
        XCTAssertNil(a.sourceArtifactId)
        XCTAssertNil(a.runId)
        XCTAssertFalse(a.reviewed)
    }

    func testInitGeneratesDifferentIDs() {
        let a = Artifact(documentId: "d", artifactType: "x")
        let b = Artifact(documentId: "d", artifactType: "x")
        XCTAssertNotEqual(a.id, b.id)
    }

    // MARK: - JSON round-trip (snake_case ↔ camelCase)

    func testEncodeDecodeRoundTrip() throws {
        let original = Artifact(
            id: "art-1",
            documentId: "doc-1",
            sourceArtifactId: "art-0",
            version: 2,
            artifactType: "entities",
            content: "raw markdown",
            runId: "run-42",
            provider: "openai",
            model: "gpt-4o",
            stepName: "extract_all",
            confidence: 0.85,
            reviewed: true
        )
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(Artifact.self, from: data)
        XCTAssertEqual(decoded.id, "art-1")
        XCTAssertEqual(decoded.documentId, "doc-1")
        XCTAssertEqual(decoded.sourceArtifactId, "art-0")
        XCTAssertEqual(decoded.version, 2)
        XCTAssertEqual(decoded.artifactType, "entities")
        XCTAssertEqual(decoded.content, "raw markdown")
        XCTAssertEqual(decoded.runId, "run-42")
        XCTAssertEqual(decoded.provider, "openai")
        XCTAssertEqual(decoded.model, "gpt-4o")
        XCTAssertEqual(decoded.stepName, "extract_all")
        XCTAssertEqual(decoded.confidence, 0.85)
        XCTAssertTrue(decoded.reviewed)
    }

    func testDecodesPythonSnakeCaseShape() throws {
        // Mirror the Python wire format. If a key name drifts on either
        // side, this fails immediately.
        let json = """
        {
            "id": "a1",
            "document_id": "d1",
            "source_artifact_id": "a0",
            "version": 3,
            "artifact_type": "summary",
            "content": "hello",
            "run_id": "r1",
            "provider": "anthropic",
            "model": "claude-3-7",
            "step_name": "summarize",
            "confidence": 0.92,
            "reviewed": false,
            "created_at": "2026-05-10T12:00:00Z"
        }
        """.data(using: .utf8)!
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let a = try decoder.decode(Artifact.self, from: json)
        XCTAssertEqual(a.id, "a1")
        XCTAssertEqual(a.documentId, "d1")
        XCTAssertEqual(a.sourceArtifactId, "a0")
        XCTAssertEqual(a.version, 3)
        XCTAssertEqual(a.artifactType, "summary")
        XCTAssertEqual(a.stepName, "summarize")
    }

    // MARK: - Type helpers

    func testIsTranscription() {
        XCTAssertTrue(
            Artifact(documentId: "d", artifactType: "transcription").isTranscription
        )
        XCTAssertFalse(
            Artifact(documentId: "d", artifactType: "summary").isTranscription
        )
    }

    func testIsEntities() {
        XCTAssertTrue(
            Artifact(documentId: "d", artifactType: "entities").isEntities
        )
        XCTAssertFalse(
            Artifact(documentId: "d", artifactType: "people").isEntities
        )
    }

    // MARK: - Display name

    func testDisplayNameForKnownTypes() {
        let cases: [(String, String)] = [
            ("transcription", "Transcription"),
            ("entities", "Entities"),
            ("summary", "Summary"),
            ("translation", "Translation"),
            ("grouping", "Grouping"),
            ("segmentation", "Segmentation"),
            ("classification", "Classification"),
            ("embedding", "Embedding"),
        ]
        for (type, expected) in cases {
            let a = Artifact(documentId: "d", artifactType: type)
            XCTAssertEqual(
                a.artifactTypeDisplayName,
                expected,
                "Display name for \(type) should be \(expected)"
            )
        }
    }

    func testDisplayNameFallsBackToCapitalised() {
        let a = Artifact(documentId: "d", artifactType: "people")
        XCTAssertEqual(a.artifactTypeDisplayName, "People")
    }

    // MARK: - Icon

    func testIconForKnownTypes() {
        let a = Artifact(documentId: "d", artifactType: "transcription")
        XCTAssertEqual(a.artifactTypeIcon, "text.quote")
        let b = Artifact(documentId: "d", artifactType: "entities")
        XCTAssertEqual(b.artifactTypeIcon, "person.3")
    }

    func testIconFallsBackToDoc() {
        let a = Artifact(documentId: "d", artifactType: "totally-unknown")
        XCTAssertEqual(a.artifactTypeIcon, "doc")
    }

    // MARK: - Timestamps

    func testCreatedAtDefaultIsRecent() {
        let before = Date()
        let artifact = Artifact(documentId: "d", artifactType: "summary")
        let after = Date()
        XCTAssertGreaterThanOrEqual(artifact.createdAt, before)
        XCTAssertLessThanOrEqual(artifact.createdAt, after)
    }

    func testCreatedAtDecodesExpectedDate() throws {
        let json = """
        {
            "id": "ts-2",
            "document_id": "d1",
            "version": 1,
            "artifact_type": "summary",
            "reviewed": false,
            "created_at": "2026-06-21T00:00:00Z"
        }
        """.data(using: .utf8)!
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let decoded = try decoder.decode(Artifact.self, from: json)
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        let comps = cal.dateComponents([.year, .month, .day], from: decoded.createdAt)
        XCTAssertEqual(comps.year, 2026)
        XCTAssertEqual(comps.month, 6)
        XCTAssertEqual(comps.day, 21)
    }

    // MARK: - Equatable / Hashable

    func testEqualityByValueNotIdentity() {
        let now = Date()
        let a = Artifact(
            id: "1", documentId: "d", artifactType: "x", createdAt: now
        )
        let b = Artifact(
            id: "1", documentId: "d", artifactType: "x", createdAt: now
        )
        XCTAssertEqual(a, b)
    }

    func testHashableProducesStableHash() {
        let now = Date()
        let a = Artifact(
            id: "1", documentId: "d", artifactType: "x", createdAt: now
        )
        let b = Artifact(
            id: "1", documentId: "d", artifactType: "x", createdAt: now
        )
        var seen: Set<Artifact> = []
        seen.insert(a)
        XCTAssertTrue(seen.contains(b))
    }
}
