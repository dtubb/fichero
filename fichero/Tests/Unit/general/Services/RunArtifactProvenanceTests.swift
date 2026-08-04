@testable import Fichero
import XCTest

/// Artifact preview + provenance carried off the run record (#4284).
///
/// This app is the FIRST Swift consumer of `content_preview` /
/// `content_truncated` / `content_chars`, so nothing had ever exercised them.
/// A client that renders a 2,000-character preview as though it were the
/// whole artifact is silently misreporting a transcription — the reader
/// cannot tell a short document from a clipped one. These pin that it can.
final class RunArtifactProvenanceTests: XCTestCase {

    private func decodeArtifact(_ json: String) throws -> WorkflowRunArtifact {
        try JSONDecoder().decode(WorkflowRunArtifact.self, from: Data(json.utf8))
    }

    // MARK: - Wire shape

    /// Hand-written snake_case keys: one typo and provenance silently reads
    /// as "not recorded" forever.
    func testDecodesEveryProvenanceAndPreviewFieldFromTheWire() throws {
        let artifact = try decodeArtifact(#"""
        {
          "artifact_id": "art-1",
          "artifact_type": "transcription",
          "document_id": "doc-1",
          "document_name": "Carta 1863",
          "source_document_id": "doc-0",
          "source_document_name": "Legajo 4",
          "run_id": "run-1",
          "step_name": "node-2",
          "node_name": "Transcribe",
          "sequence": 3,
          "created_at": "2026-08-03T05:00:00Z",
          "provider": "anthropic",
          "model": "claude-sonnet-4-6",
          "content_chars": 12431,
          "content_preview": "firmado Ospina",
          "content_truncated": true,
          "has_structured_data": false
        }
        """#)

        XCTAssertEqual(artifact.provider, "anthropic")
        XCTAssertEqual(artifact.model, "claude-sonnet-4-6")
        XCTAssertEqual(artifact.contentChars, 12431)
        XCTAssertEqual(artifact.contentPreview, "firmado Ospina")
        XCTAssertTrue(artifact.isTruncated)
        XCTAssertEqual(artifact.nodeName, "Transcribe")
        XCTAssertEqual(artifact.sourceDocumentName, "Legajo 4")
    }

    // MARK: - Truncation must be stated

    func testTruncatedPreviewIsMarkedTruncatedWithBothCounts() throws {
        let artifact = try decodeArtifact(#"""
        {
          "artifact_id": "a", "artifact_type": "transcription", "document_id": "d",
          "content_chars": 12431, "content_preview": "firmado Ospina",
          "content_truncated": true
        }
        """#)

        let notice = try XCTUnwrap(artifact.truncationNotice)
        // Grouping separators are locale-dependent (#2092), so compare against
        // the same formatting the notice itself uses rather than "12,431".
        XCTAssertTrue(notice.contains(12431.formatted()), notice)
        XCTAssertTrue(notice.contains(14.formatted()), "must state how much is shown: \(notice)")
        XCTAssertTrue(notice.lowercased().contains("preview"), notice)
    }

    /// The counterpart: content that IS complete must carry no clip notice,
    /// or the warning becomes noise and stops being read.
    func testCompletePreviewCarriesNoTruncationNotice() throws {
        let artifact = try decodeArtifact(#"""
        {
          "artifact_id": "a", "artifact_type": "transcription", "document_id": "d",
          "content_chars": 14, "content_preview": "firmado Ospina",
          "content_truncated": false
        }
        """#)

        XCTAssertFalse(artifact.isTruncated)
        XCTAssertNil(artifact.truncationNotice)
    }

    /// Truncated but the server did not say by how much: still say it is
    /// incomplete. An unknown remainder is not no remainder.
    func testTruncatedWithoutCountsStillSaysItIsNotTheFullText() throws {
        let artifact = try decodeArtifact(#"""
        {
          "artifact_id": "a", "artifact_type": "transcription", "document_id": "d",
          "content_preview": "firmado Ospina", "content_truncated": true
        }
        """#)

        let notice = try XCTUnwrap(artifact.truncationNotice)
        XCTAssertTrue(notice.lowercased().contains("not the full text"), notice)
    }

    /// An old response with no preview fields at all must not claim to be
    /// truncated — there is nothing being shown to over-claim about.
    func testLegacyArtifactWithoutPreviewFieldsIsNotMarkedTruncated() throws {
        let artifact = try decodeArtifact(#"""
        {"artifact_id": "a", "artifact_type": "transcription", "document_id": "d"}
        """#)

        XCTAssertFalse(artifact.isTruncated)
        XCTAssertNil(artifact.truncationNotice)
        XCTAssertNil(artifact.contentPreview)
    }

    // MARK: - Provenance

    func testProviderAndModelReadAsOneProvenanceLine() throws {
        let artifact = try decodeArtifact(#"""
        {
          "artifact_id": "a", "artifact_type": "t", "document_id": "d",
          "provider": "anthropic", "model": "claude-sonnet-4-6"
        }
        """#)
        XCTAssertEqual(artifact.providerModelText, "anthropic · claude-sonnet-4-6")
    }

    /// No recorded origin must read as no recorded origin. Inventing or
    /// inheriting a model would attach false provenance to a real artifact.
    func testArtifactWithNoRecordedModelReportsNone() throws {
        let artifact = try decodeArtifact(#"""
        {"artifact_id": "a", "artifact_type": "t", "document_id": "d"}
        """#)
        XCTAssertNil(artifact.providerModelText)
    }

    func testEmptyStringsAreNotTreatedAsRecordedProvenance() throws {
        let artifact = try decodeArtifact(#"""
        {
          "artifact_id": "a", "artifact_type": "t", "document_id": "d",
          "provider": "", "model": ""
        }
        """#)
        XCTAssertNil(artifact.providerModelText)
    }

    func testPartialProvenanceStillReportsWhatIsKnown() throws {
        let artifact = try decodeArtifact(#"""
        {
          "artifact_id": "a", "artifact_type": "t", "document_id": "d",
          "model": "claude-sonnet-4-6"
        }
        """#)
        XCTAssertEqual(artifact.providerModelText, "claude-sonnet-4-6")
    }

    // MARK: - Steps on the run record

    func testRunDecodesStepRecordsWithTheirArtifacts() throws {
        let run = try JSONDecoder().decode(WorkflowRunResponse.self, from: Data(#"""
        {
          "thread_id": "t1", "workflow_id": "w1", "workflow_name": "Transcribe",
          "status": "completed",
          "steps": [
            {
              "node_id": "node-1", "node_name": "Load", "tool": "load",
              "status": "completed", "produced_nothing": false,
              "artifacts": [
                {
                  "artifact_id": "a1", "artifact_type": "transcription",
                  "document_id": "d1", "provider": "anthropic",
                  "model": "claude-sonnet-4-6", "content_truncated": true,
                  "content_chars": 9000, "content_preview": "abc"
                }
              ]
            },
            {
              "node_id": "node-2", "node_name": "Extract", "tool": "ner",
              "status": "completed", "produced_nothing": true
            },
            {
              "node_id": "node-3", "node_name": "Summarise", "tool": "summarise",
              "status": "not_run"
            }
          ]
        }
        """#.utf8))

        XCTAssertEqual(run.steps.count, 3)
        XCTAssertFalse(run.steps[0].didProduceNothing)
        XCTAssertTrue(run.steps[1].didProduceNothing)
        XCTAssertEqual(run.steps[2].status, "not_run")
        XCTAssertFalse(run.steps[2].didProduceNothing, "a step that never ran produced nothing by absence, not by outcome")
        XCTAssertEqual(run.steps[0].artifacts?.first?.model, "claude-sonnet-4-6")
        XCTAssertTrue(run.steps[0].artifacts?.first?.isTruncated == true)
    }

    /// Legacy runs predate step records entirely; decoding must yield an
    /// empty list, not a failure.
    func testLegacyRunWithoutStepsDecodesToNoSteps() throws {
        let run = try JSONDecoder().decode(WorkflowRunResponse.self, from: Data(#"""
        {"thread_id": "t1", "workflow_id": "w1", "workflow_name": "W", "status": "completed"}
        """#.utf8))
        XCTAssertTrue(run.steps.isEmpty)
    }
}
