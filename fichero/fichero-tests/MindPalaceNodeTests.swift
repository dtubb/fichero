@testable import Fichero
import XCTest

final class MindPalaceNodeTests: XCTestCase {

    func testThumbnailURLUsesStorageEndpoint() {
        let baseURL = URL(string: "http://127.0.0.1:8765/api")!

        let url = MindPalaceNode.thumbnailURL(forSourceId: "doc-123", baseURL: baseURL)

        XCTAssertEqual(
            url?.absoluteString,
            "http://127.0.0.1:8765/api/storage/thumbnail/doc-123"
        )
    }

    func testThumbnailURLRejectsEmptySourceId() {
        let url = MindPalaceNode.thumbnailURL(forSourceId: "")

        XCTAssertNil(url)
    }
}
