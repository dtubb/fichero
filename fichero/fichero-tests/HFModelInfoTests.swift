@testable import Fichero
import XCTest

/// Tests for HFModelInfo — the HuggingFace model row. Snake_case decode plus the
/// display helpers formattedDownloads (M/K/plain thresholds) and shortName/author
/// (id slash-splitting). Pure value logic, no live engine.
final class HFModelInfoTests: XCTestCase {

    private func model(id: String = "org/model", downloads: Int = 0) -> HFModelInfo {
        HFModelInfo(id: id, downloads: downloads, likes: 0, pipelineTag: nil,
                    libraryName: nil, createdAt: nil, tags: [])
    }

    // MARK: - Decode

    func testDecodesSnakeCaseKeys() throws {
        let json = Data("""
        {
            "id": "meta-llama/Llama-3.1-8B",
            "downloads": 1500000,
            "likes": 42,
            "pipeline_tag": "text-generation",
            "library_name": "transformers",
            "created_at": "2026-05-10T10:00:00Z",
            "tags": ["llm", "chat"]
        }
        """.utf8)
        let info = try JSONDecoder().decode(HFModelInfo.self, from: json)
        XCTAssertEqual(info.id, "meta-llama/Llama-3.1-8B")
        XCTAssertEqual(info.pipelineTag, "text-generation")   // ← pipeline_tag
        XCTAssertEqual(info.libraryName, "transformers")       // ← library_name
        XCTAssertEqual(info.createdAt, "2026-05-10T10:00:00Z") // ← created_at
        XCTAssertEqual(info.tags, ["llm", "chat"])
    }

    func testDecodesWithOptionalsAbsent() throws {
        let json = Data("""
        { "id": "x/y", "downloads": 3, "likes": 0, "tags": [] }
        """.utf8)
        let info = try JSONDecoder().decode(HFModelInfo.self, from: json)
        XCTAssertNil(info.pipelineTag)
        XCTAssertNil(info.libraryName)
        XCTAssertNil(info.createdAt)
    }

    // MARK: - formattedDownloads

    func testFormattedDownloadsThresholds() {
        XCTAssertEqual(model(downloads: 999).formattedDownloads, "999")     // plain
        XCTAssertEqual(model(downloads: 1_000).formattedDownloads, "1.0K")  // K boundary
        XCTAssertEqual(model(downloads: 12_345).formattedDownloads, "12.3K")
        XCTAssertEqual(model(downloads: 1_000_000).formattedDownloads, "1.0M")  // M boundary
        XCTAssertEqual(model(downloads: 1_234_567).formattedDownloads, "1.2M")
        XCTAssertEqual(model(downloads: 0).formattedDownloads, "0")
    }

    // MARK: - shortName / author

    func testShortNameAndAuthorSplitCanonicalId() {
        let info = model(id: "meta-llama/Llama-3.1-8B")
        XCTAssertEqual(info.shortName, "Llama-3.1-8B")   // after last slash
        XCTAssertEqual(info.author, "meta-llama")         // before first slash
    }

    func testShortNameAndAuthorWithoutSlash() {
        let info = model(id: "solo-model")
        XCTAssertEqual(info.shortName, "solo-model")   // no slash → whole id
        XCTAssertEqual(info.author, "")                 // no slash → empty
    }

    /// A nested id splits from opposite ends: author is the first segment,
    /// shortName the last.
    func testShortNameAndAuthorWithNestedId() {
        let info = model(id: "a/b/c")
        XCTAssertEqual(info.author, "a")
        XCTAssertEqual(info.shortName, "c")
    }
}
