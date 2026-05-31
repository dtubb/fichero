@testable import Fichero
import Foundation
import XCTest

final class ClaimSummaryCardTests: XCTestCase {

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

    private func decodeClaim(_ json: String) throws -> Components.Schemas.KnowledgeClaim {
        let data = Data(json.utf8)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(Components.Schemas.KnowledgeClaim.self, from: data)
    }
}
