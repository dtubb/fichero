@testable import Fichero
import FicheroAPIClient
import Foundation
import XCTest

@MainActor
// swiftlint:disable:next type_body_length
final class ClaimSummaryCardTests: XCTestCase {

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testOpenClaimSourceRequestIncludesProvenanceFields() {
        let request = ClaimSummaryCard.openClaimSourceRequest(
            documentId: "doc-9",
            pageLabel: " 12 ",
            charStart: 101,
            charEnd: 127,
            claimId: "claim-42",
            excerpt: " Paris is the capital of France. "
        )

        XCTAssertEqual(request?.documentId, "doc-9")
        XCTAssertEqual(request?.pageLabel, "12")
        XCTAssertEqual(request?.charStart, 101)
        XCTAssertEqual(request?.charEnd, 127)
        XCTAssertEqual(request?.claimId, "claim-42")
        XCTAssertEqual(request?.claimText, "Paris is the capital of France.")
    }

    func testOpenClaimSourceRequestRejectsEmptyDocumentId() {
        let request = ClaimSummaryCard.openClaimSourceRequest(
            documentId: "",
            pageLabel: "12",
            charStart: 101,
            charEnd: 127,
            claimId: "claim-42",
            excerpt: "Paris is the capital of France."
        )

        XCTAssertNil(request)
    }

    func testPageContentClaimSourceHighlightMatchesCharRange() {
        let highlight = PageContentClaimSourceHighlight.match(
            content: "alpha claim omega",
            documentId: "page-1",
            info: [
                "documentId": "page-1",
                "charStart": 6,
                "charEnd": 11
            ]
        )

        XCTAssertEqual(highlight?.before, "alpha ")
        XCTAssertEqual(highlight?.highlighted, "claim")
        XCTAssertEqual(highlight?.after, " omega")
    }

    func testPageContentClaimSourceHighlightMatchesExcerpt() {
        let highlight = PageContentClaimSourceHighlight.match(
            content: "Alpha Claim Omega",
            documentId: "page-1",
            info: [
                "documentId": "page-1",
                "excerpt": "claim"
            ]
        )

        XCTAssertEqual(highlight?.highlighted, "Claim")
    }

    func testPageContentClaimSourceHighlightRejectsDifferentDocument() {
        let highlight = PageContentClaimSourceHighlight.match(
            content: "alpha claim omega",
            documentId: "page-1",
            info: [
                "documentId": "page-2",
                "excerpt": "claim"
            ]
        )

        XCTAssertNil(highlight)
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

    func testVerbAndObjectChipsEnterInlineEditing() throws {
        let source = try Self.appSource("Views/KnowledgeGraph/OntologyBrowser/ClaimSummaryCardView.swift")

        XCTAssertTrue(source.contains("private func beginInlineEditing()"))
        XCTAssertTrue(source.contains("Text(svo.verb)"))
        XCTAssertTrue(source.contains("Text(svo.object)"))
        XCTAssertTrue(source.contains("beginInlineEditing()"))
    }

    func testExpandedDetailsShowSourceClaimText() throws {
        let source = try Self.appSource("Views/KnowledgeGraph/OntologyBrowser/ClaimSummaryCard+Details.swift")

        XCTAssertTrue(source.contains("Text(\"Source claim\")"))
        XCTAssertTrue(source.contains("cleanedDisplayText(claim.text)"))
    }

    func testCollapsedSourceExcerptOpensClaimSource() throws {
        let source = try Self.appSource("Views/KnowledgeGraph/OntologyBrowser/ClaimSummaryCardView.swift")
        guard let excerptStart = source.range(of: "} else if let excerpt = cleanedDisplayText(claim.sourceExcerpt)"),
              let noSvoStart = source.range(of: "No subject-verb-object", range: excerptStart.upperBound..<source.endIndex)
        else {
            XCTFail("ClaimSummaryCard must render source excerpts in the collapsed sentence area")
            return
        }

        let excerptRenderer = String(source[excerptStart.lowerBound..<noSvoStart.lowerBound])
        XCTAssertTrue(excerptRenderer.contains("openClaimSource()"))
        XCTAssertFalse(excerptRenderer.contains("ficheroEntitySearchRequested"))
    }

    func testExpandedSourceExcerptOpensClaimSource() throws {
        let source = try Self.appSource("Views/KnowledgeGraph/OntologyBrowser/ClaimSummaryCard+Details.swift")
        guard let excerptStart = source.range(of: "if let excerpt = cleanedDisplayText(claim.sourceExcerpt)"),
              let loadingStart = source.range(of: "if isLoadingDetails", range: excerptStart.upperBound..<source.endIndex)
        else {
            XCTFail("ClaimSummaryCard details must render the source excerpt before loading details")
            return
        }

        let excerptRenderer = String(source[excerptStart.lowerBound..<loadingStart.lowerBound])
        XCTAssertTrue(excerptRenderer.contains("openClaimSource()"))
        XCTAssertFalse(excerptRenderer.contains("ficheroEntitySearchRequested"))
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

        // No emoji per #1864 — plain "Human" badge.
        XCTAssertTrue(labels.contains("Human"))
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

    func testClaimFocusPreservesEntityInspectionContext() throws {
        let source = try Self.appSource("Views/KnowledgeGraph/OntologyBrowser/ClaimSummaryCardView.swift")

        XCTAssertTrue(source.contains("var focusedEntityId: String?"))
        XCTAssertTrue(source.contains("entityId: focusedEntityId"))
    }

    func testMentionSummariesDeduplicateSourcePagesAndFormatDate() throws {
        let first = try decodeClaim("""
        {
          "id": "claim-1",
          "text": "ignored",
          "source_document_id": "doc-1",
          "source_page_label": "12",
          "time_start": "1923-01-01"
        }
        """)
        let duplicatePage = try decodeClaim("""
        {
          "id": "claim-2",
          "text": "ignored",
          "source_document_id": "doc-1",
          "source_page_label": "12",
          "time_start": "1923-01-02"
        }
        """)
        let secondPage = try decodeClaim("""
        {
          "id": "claim-3",
          "text": "ignored",
          "source_document_id": "doc-1",
          "source_page_label": "13",
          "temporal_context": "Early January 1923"
        }
        """)

        let mentions = EntityDetailView.mentionSummaries(
            from: [first, duplicatePage, secondPage],
            documents: [:]
        )

        XCTAssertEqual(mentions.count, 2)
        XCTAssertEqual(mentions[0].claim.id, "claim-1")
        XCTAssertEqual(mentions[0].lineLabel, "Monday, January 1, 1923 · p. 12")
        XCTAssertEqual(mentions[1].lineLabel, "Early January 1923 · p. 13")
    }

    func testMentionDateLabelFallsBackToDocumentMetadata() throws {
        let claim = try decodeClaim("""
        {
          "id": "claim-1",
          "text": "ignored",
          "source_document_id": "doc-1"
        }
        """)
        let document = Document(
            id: "doc-1",
            docType: .page,
            name: "Page 1",
            sequence: 7,
            metadata: ["event_date": AnyCodable("1923-01-02")]
        )

        XCTAssertEqual(
            EntityDetailView.mentionDateLabel(for: claim, document: document),
            "Tuesday, January 2, 1923"
        )
        XCTAssertEqual(
            EntityDetailView.normalizedPageLabel(for: claim, document: document),
            "p. 7"
        )
    }

    func testParseDuplicateCandidatesExcludesSelfAndWeakMatches() {
        // #3317: the /semantic response includes the entity itself (score ~1.0)
        // and weak matches; both must be dropped, cross-script variants kept.
        let json = """
        {"items":[
          {"id":"self","canonical_name":"Andagoya","entity_type":"location","similarity_score":1.0},
          {"id":"e2","canonical_name":"Andagóya","entity_type":"location","similarity_score":0.91},
          {"id":"e3","name":"Andagoia","entity_type":"location","similarity_score":0.55},
          {"id":"e4","canonical_name":"Weak","entity_type":"location","similarity_score":0.2}
        ],"count":4}
        """
        let candidates = EntityDetailView.parseDuplicateCandidates(Data(json.utf8), excluding: "self")

        XCTAssertEqual(candidates.map(\.id), ["e2", "e3"])   // self + weak(<0.4) dropped
        XCTAssertEqual(candidates.first?.name, "Andagóya")   // cross-script variant kept
        XCTAssertEqual(candidates.first?.score, 0.91)
        XCTAssertEqual(candidates.last?.name, "Andagoia")    // "name" fallback when no canonical_name
        XCTAssertTrue(EntityDetailView.parseDuplicateCandidates(Data(), excluding: "x").isEmpty)
    }

    func testLocationEntitiesHideGenericClaimsSection() {
        let location = makeKnowledgeEntity(id: "entity-1", name: "Andagoya", type: .location)
        let person = makeKnowledgeEntity(id: "entity-2", name: "Crawfurd", type: .person)

        XCTAssertFalse(EntityDetailView.showsClaimsSection(for: location))
        XCTAssertTrue(EntityDetailView.showsClaimsSection(for: person))
    }

    private func decodeClaim(_ json: String) throws -> Components.Schemas.KnowledgeClaim {
        let data = Data(json.utf8)
        let decoder = JSONDecoder()
        return try decoder.decode(Components.Schemas.KnowledgeClaim.self, from: data)
    }
}
