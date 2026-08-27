@testable import Fichero
import XCTest

/// Tests for assorted response DTOs that carry snake_case keys, nesting, or a
/// computed helper and lacked coverage: StorageStats, StatsResponse/
/// EmbeddingStats, ConnectionTestResponse, WebSearchResultItem. Pure decode +
/// value logic, no live engine.
final class ResponseDTODecodingTests: XCTestCase {

    // MARK: - StorageStats

    func testStorageStatsDecodesSnakeCase() throws {
        let json = Data("""
        {
            "total_size": 1500000000,
            "file_count": 12,
            "collection_count": 3,
            "linked_count": 4,
            "copied_count": 8
        }
        """.utf8)
        let stats = try JSONDecoder().decode(StorageStats.self, from: json)
        XCTAssertEqual(stats.totalSize, 1_500_000_000)  // ← total_size
        XCTAssertEqual(stats.fileCount, 12)             // ← file_count
        XCTAssertEqual(stats.collectionCount, 3)
        XCTAssertEqual(stats.linkedCount, 4)
        XCTAssertEqual(stats.copiedCount, 8)
    }

    /// formattedSize delegates to ByteCountFormatter — locale-dependent, so we
    /// only assert it is non-empty and scales with the byte count.
    func testStorageStatsFormattedSizeIsNonEmptyAndScales() {
        func stats(_ bytes: Int64) -> StorageStats {
            StorageStats(totalSize: bytes, fileCount: 0, collectionCount: 0,
                         linkedCount: 0, copiedCount: 0)
        }
        XCTAssertFalse(stats(0).formattedSize.isEmpty)
        XCTAssertNotEqual(stats(1_000).formattedSize, stats(5_000_000_000).formattedSize)
    }

    // MARK: - StatsResponse (nested EmbeddingStats)

    func testStatsResponseDecodesNestedSnakeCase() throws {
        let json = Data("""
        {
            "documents": 40,
            "artifacts": 5,
            "embedding_stats": {"indexed_count": 37, "table_exists": true}
        }
        """.utf8)
        let stats = try JSONDecoder().decode(StatsResponse.self, from: json)
        XCTAssertEqual(stats.documents, 40)
        XCTAssertEqual(stats.artifacts, 5)
        XCTAssertEqual(stats.embeddingStats.indexedCount, 37)   // ← embedding_stats.indexed_count
        XCTAssertTrue(stats.embeddingStats.tableExists)         // ← table_exists
    }

    // MARK: - ConnectionTestResponse (snake_case + optionals)

    func testConnectionTestResponseDecodesWithOptionals() throws {
        let json = Data("""
        {
            "success": true,
            "provider_type": "openai",
            "message": "ok",
            "latency_ms": 123.4,
            "model_tested": "gpt"
        }
        """.utf8)
        let resp = try JSONDecoder().decode(ConnectionTestResponse.self, from: json)
        XCTAssertTrue(resp.success)
        XCTAssertEqual(resp.providerType, "openai")   // ← provider_type
        XCTAssertEqual(resp.latencyMs, 123.4)         // ← latency_ms
        XCTAssertEqual(resp.modelTested, "gpt")       // ← model_tested
    }

    func testConnectionTestResponseOmitsOptionals() throws {
        let json = Data("""
        { "success": false, "provider_type": "local", "message": "down" }
        """.utf8)
        let resp = try JSONDecoder().decode(ConnectionTestResponse.self, from: json)
        XCTAssertFalse(resp.success)
        XCTAssertNil(resp.latencyMs)
        XCTAssertNil(resp.modelTested)
    }

    // MARK: - WebSearchResultItem (id == url)

    func testWebSearchResultItemDecodeAndIdentity() throws {
        let json = Data("""
        { "title": "Result", "url": "https://x.test/p", "snippet": "…" }
        """.utf8)
        let item = try JSONDecoder().decode(WebSearchResultItem.self, from: json)
        XCTAssertEqual(item.title, "Result")
        XCTAssertEqual(item.url, "https://x.test/p")
        XCTAssertEqual(item.id, "https://x.test/p")   // id is the url
    }
}
