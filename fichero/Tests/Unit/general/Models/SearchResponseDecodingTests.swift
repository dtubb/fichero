@testable import Fichero
import XCTest

/// Tests for the SearchResult / SearchResponse custom decoders. DocumentModelTests
/// covers Document's enums + AnyCodable, and ContractTests covers Document decode,
/// but these two search DTOs (snake_case keys + defaulted array fields) were
/// untested. Pure decode, no live engine.
final class SearchResponseDecodingTests: XCTestCase {

    // MARK: - SearchResult

    func testSearchResultDecodesSnakeCaseAndMetadata() throws {
        let json = Data("""
        {
            "document_id": "doc-1",
            "score": 0.87,
            "content_preview": "a snippet",
            "metadata": {"title": "My Doc", "pages": 3},
            "highlights": ["hit"]
        }
        """.utf8)
        let result = try JSONDecoder().decode(SearchResult.self, from: json)
        XCTAssertEqual(result.documentId, "doc-1")   // ← document_id
        XCTAssertEqual(result.id, "doc-1")            // id == documentId
        XCTAssertEqual(result.score, 0.87)
        XCTAssertEqual(result.contentPreview, "a snippet")  // ← content_preview
        XCTAssertEqual(result.highlights, ["hit"])
        XCTAssertEqual(result.metadata["title"]?.value as? String, "My Doc")
        XCTAssertEqual(result.metadata["pages"]?.value as? Int, 3)
        // transcript_excerpts absent → defaults to [].
        XCTAssertEqual(result.transcriptExcerpts.count, 0)
    }

    /// Optional fields absent stay nil; the excerpt array still defaults to [].
    func testSearchResultOptionalFieldsAbsent() throws {
        let json = Data("""
        { "document_id": "doc-2", "score": 0.1, "metadata": {} }
        """.utf8)
        let result = try JSONDecoder().decode(SearchResult.self, from: json)
        XCTAssertNil(result.contentPreview)
        XCTAssertNil(result.highlights)
        XCTAssertTrue(result.metadata.isEmpty)
        XCTAssertEqual(result.transcriptExcerpts.count, 0)
    }

    // MARK: - SearchResponse

    func testSearchResponseDecodesSnakeCaseKeys() throws {
        let json = Data("""
        {
            "results": [
                {"document_id": "d1", "score": 1.0, "metadata": {}}
            ],
            "count": 1,
            "total_results": 42,
            "query": "cats",
            "search_type": "hybrid",
            "execution_time_ms": 12.5,
            "has_more": true,
            "filters_applied": {"kind": "pdf"},
            "suggestions": ["cat", "kitten"]
        }
        """.utf8)
        let resp = try JSONDecoder().decode(SearchResponse.self, from: json)
        XCTAssertEqual(resp.results.count, 1)
        XCTAssertEqual(resp.results.first?.documentId, "d1")
        XCTAssertEqual(resp.count, 1)
        XCTAssertEqual(resp.totalResults, 42)          // ← total_results
        XCTAssertEqual(resp.query, "cats")
        XCTAssertEqual(resp.searchType, "hybrid")      // ← search_type
        XCTAssertEqual(resp.executionTimeMs, 12.5)     // ← execution_time_ms
        XCTAssertTrue(resp.hasMore)                     // ← has_more
        XCTAssertEqual(resp.filtersApplied, ["kind": "pdf"])  // ← filters_applied
        XCTAssertEqual(resp.suggestions, ["cat", "kitten"])
        // entity_hits / claim_hits absent → default [].
        XCTAssertEqual(resp.entityHits.count, 0)
        XCTAssertEqual(resp.claimHits.count, 0)
    }

    /// A minimal response (no optional keys, no entity/claim hits) decodes with
    /// hits defaulted to [] and optionals nil.
    func testSearchResponseMinimalDefaultsHitsAndOptionals() throws {
        let json = Data("""
        {
            "results": [],
            "count": 0,
            "total_results": 0,
            "query": "",
            "search_type": "keyword",
            "execution_time_ms": 0.0,
            "has_more": false
        }
        """.utf8)
        let resp = try JSONDecoder().decode(SearchResponse.self, from: json)
        XCTAssertTrue(resp.results.isEmpty)
        XCTAssertEqual(resp.entityHits.count, 0)
        XCTAssertEqual(resp.claimHits.count, 0)
        XCTAssertNil(resp.filtersApplied)
        XCTAssertNil(resp.suggestions)
        XCTAssertFalse(resp.hasMore)
    }
}
