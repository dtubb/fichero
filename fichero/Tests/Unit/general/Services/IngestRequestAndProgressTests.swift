@testable import Fichero
import XCTest

/// Tests for the import request bodies (snake_case Encodable), HFModelSearchResponse
/// decode, and ImportProgress display helpers. Pure value logic, no live engine.
/// Includes the regression test for the ImportProgress.percentage total==0 NaN
/// guard fixed alongside these tests.
final class IngestRequestAndProgressTests: XCTestCase {

    private func encodeToDict<T: Encodable>(_ value: T) throws -> [String: Any] {
        let data = try JSONEncoder().encode(value)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    // MARK: - IngestFileRequest

    func testIngestFileRequestEncodesSnakeCase() throws {
        let req = IngestFileRequest(path: "/a/b.pdf", mode: "COPY", parentId: "f-1",
                                    extractText: true, autoEmbed: false, save: true)
        let obj = try encodeToDict(req)
        XCTAssertEqual(obj["path"] as? String, "/a/b.pdf")
        XCTAssertEqual(obj["mode"] as? String, "COPY")
        XCTAssertEqual(obj["parent_id"] as? String, "f-1")     // ← parent_id
        XCTAssertEqual(obj["extract_text"] as? Bool, true)     // ← extract_text
        XCTAssertEqual(obj["auto_embed"] as? Bool, false)      // ← auto_embed
        XCTAssertEqual(obj["save"] as? Bool, true)
        XCTAssertNil(obj["parentId"])  // camelCase never leaks
    }

    func testIngestFileRequestOmitsNilParentId() throws {
        let req = IngestFileRequest(path: "/x", mode: "LINK", parentId: nil,
                                    extractText: false, autoEmbed: false, save: false)
        let obj = try encodeToDict(req)
        XCTAssertNil(obj["parent_id"])  // nil optional omitted
    }

    // MARK: - IngestFolderRequest

    func testIngestFolderRequestEncodesSnakeCase() throws {
        let req = IngestFolderRequest(path: "/dir", copyMode: true, parentId: "f-2",
                                      recursive: false, extractText: true, autoEmbed: true)
        let obj = try encodeToDict(req)
        XCTAssertEqual(obj["copy_mode"] as? Bool, true)        // ← copy_mode
        XCTAssertEqual(obj["parent_id"] as? String, "f-2")     // ← parent_id
        XCTAssertEqual(obj["recursive"] as? Bool, false)
        XCTAssertEqual(obj["extract_text"] as? Bool, true)     // ← extract_text
        XCTAssertEqual(obj["auto_embed"] as? Bool, true)       // ← auto_embed
    }

    // MARK: - HFModelSearchResponse

    func testModelSearchResponseDecodesSnakeCaseAndNestedModels() throws {
        let json = Data("""
        {
            "models": [
                {"id": "org/m", "downloads": 5, "likes": 1, "tags": []}
            ],
            "total": 1,
            "has_more": true
        }
        """.utf8)
        let resp = try JSONDecoder().decode(HFModelSearchResponse.self, from: json)
        XCTAssertEqual(resp.total, 1)
        XCTAssertTrue(resp.hasMore)                 // ← has_more
        XCTAssertEqual(resp.models.first?.id, "org/m")
    }

    // MARK: - ImportProgress

    func testImportProgressPercentage() {
        XCTAssertEqual(ImportProgress(current: 50, total: 100, currentFile: "f").percentage, 50, accuracy: 1e-9)
        XCTAssertEqual(ImportProgress(current: 1, total: 4, currentFile: "f").percentage, 25, accuracy: 1e-9)
        XCTAssertEqual(ImportProgress(current: 0, total: 10, currentFile: "f").percentage, 0, accuracy: 1e-9)
    }

    /// total==0 (empty import) must yield 0, not NaN — the divide-by-zero guard.
    func testImportProgressPercentageZeroTotalIsZeroNotNaN() {
        let percent = ImportProgress(current: 0, total: 0, currentFile: "f").percentage
        XCTAssertEqual(percent, 0)
        XCTAssertFalse(percent.isNaN)
    }

    func testImportProgressDescription() {
        let progress = ImportProgress(current: 2, total: 5, currentFile: "shot.jpg")
        XCTAssertEqual(progress.description, "Importing 2/5: shot.jpg")
    }
}
