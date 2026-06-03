@testable import Fichero
import FicheroAPIClient
import Foundation
import XCTest

@MainActor
final class ClaimSummaryCardTests: XCTestCase {

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testOpenClaimSourceUserInfoIncludesProvenanceFields() {
        let info = ClaimSummaryCard.openClaimSourceUserInfo(
            documentId: "doc-9",
            pageLabel: " 12 ",
            charStart: 101,
            charEnd: 127,
            claimId: "claim-42",
            excerpt: " Paris is the capital of France. "
        )

        XCTAssertEqual(info?["documentId"] as? String, "doc-9")
        XCTAssertEqual(info?["pageLabel"] as? String, "12")
        let charStart = (info?["charStart"] as? Int) ?? (info?["charStart"] as? NSNumber)?.intValue
        let charEnd = (info?["charEnd"] as? Int) ?? (info?["charEnd"] as? NSNumber)?.intValue
        XCTAssertEqual(charStart, 101)
        XCTAssertEqual(charEnd, 127)
        XCTAssertEqual(info?["claimId"] as? String, "claim-42")
        XCTAssertEqual(info?["excerpt"] as? String, "Paris is the capital of France.")
    }

    func testOpenClaimSourceUserInfoRejectsEmptyDocumentId() {
        let info = ClaimSummaryCard.openClaimSourceUserInfo(
            documentId: "",
            pageLabel: "12",
            charStart: 101,
            charEnd: 127,
            claimId: "claim-42",
            excerpt: "Paris is the capital of France."
        )

        XCTAssertNil(info)
    }

    func testSvoChipActionsRevealInlineSourceClaim() throws {
        let source = try Self.appSource("Views/KnowledgeGraph/OntologyBrowser/ClaimSummaryCardView.swift")
        guard let sentenceStart = source.range(of: "private var claimSentence: some View"),
              let fallbackStart = source.range(of: "} else if let excerpt", range: sentenceStart.upperBound..<source.endIndex)
        else {
            XCTFail("ClaimSummaryCard must render SVO before the fallback excerpt")
            return
        }

        let svoRenderer = String(source[sentenceStart.lowerBound..<fallbackStart.lowerBound])
        XCTAssertTrue(svoRenderer.contains("revealSourceClaimInline()"))
        XCTAssertFalse(svoRenderer.contains("focusEntityLozenge"))
        XCTAssertFalse(svoRenderer.contains("ficheroEntitySearchRequested"))
    }

    func testExpandedDetailsShowSourceClaimText() throws {
        let source = try Self.appSource("Views/KnowledgeGraph/OntologyBrowser/ClaimSummaryCard+Details.swift")

        XCTAssertTrue(source.contains("Text(\"Source claim\")"))
        XCTAssertTrue(source.contains("cleanedDisplayText(claim.text)"))
    }

    func testSvoTriplePrefersTypedFields() throws {
        let claim = try decodeClaim("""
        {
          "text": "ignored",
          "source_document_id": "doc-1",
          "subject_canonical": "Ada Lovelace",
          "predicate_verb": "wrote",
          "object_phrase": "the first algorithm"
        }
        """)

        let svo = ClaimSummaryCard.svoTriple(for: claim)

        XCTAssertEqual(svo?.subject, "Ada Lovelace")
        XCTAssertEqual(svo?.verb, "wrote")
        XCTAssertEqual(svo?.object, "the first algorithm")
    }

    func testSvoTripleFallsBackToLegacyMetadata() throws {
        let claim = try decodeClaim("""
        {
          "text": "ignored",
          "source_document_id": "doc-1",
          "metadata": {
            "subject": "Ada Lovelace",
            "verb": "wrote",
            "object": "the first algorithm"
          }
        }
        """)

        let svo = ClaimSummaryCard.svoTriple(for: claim)

        XCTAssertEqual(svo?.subject, "Ada Lovelace")
        XCTAssertEqual(svo?.verb, "wrote")
        XCTAssertEqual(svo?.object, "the first algorithm")
    }

    func testProvenanceBadgesMapsMetadataFields() throws {
        let claim = try decodeClaim("""
        {
          "text": "ignored",
          "source_document_id": "doc-1",
          "confidence_source": "heuristic",
          "metadata": {
            "quotation_kind": "verbatim",
            "corroboration_count": 3
          }
        }
        """)

        let labels = ClaimSummaryCard
            .provenanceBadges(for: claim)
            .map(\.label)

        XCTAssertTrue(labels.contains("Verbatim"))
        XCTAssertTrue(labels.contains("Heuristic"))
        XCTAssertTrue(labels.contains("3x corroborated"))
    }

    func testProvenanceBadgesOmitsZeroCorroboration() throws {
        let claim = try decodeClaim("""
        {
          "text": "ignored",
          "source_document_id": "doc-1",
          "metadata": {
            "corroboration_count": 0
          }
        }
        """)

        let labels = ClaimSummaryCard
            .provenanceBadges(for: claim)
            .map(\.label)

        XCTAssertFalse(labels.contains(where: { $0.contains("corroborated") }))
    }

    func testProvenanceBadgesIncludesHumanCreatedByBadge() throws {
        let claim = try decodeClaim("""
        {
          "text": "ignored",
          "source_document_id": "doc-1",
          "created_by": "human"
        }
        """)

        let labels = ClaimSummaryCard
            .provenanceBadges(for: claim)
            .map(\.label)

        XCTAssertTrue(labels.contains("✏️ Human"))
    }

    func testProvenanceBadgesIncludesAIBadgeForExtractor() throws {
        let claim = try decodeClaim("""
        {
          "text": "ignored",
          "source_document_id": "doc-1",
          "created_by": "extractor"
        }
        """)

        let labels = ClaimSummaryCard
            .provenanceBadges(for: claim)
            .map(\.label)

        XCTAssertTrue(labels.contains("AI"))
    }

    private func decodeClaim(_ json: String) throws -> Components.Schemas.KnowledgeClaim {
        let data = Data(json.utf8)
        let decoder = JSONDecoder()
        return try decoder.decode(Components.Schemas.KnowledgeClaim.self, from: data)
    }
}
