@testable import Fichero
import XCTest

final class SpatialNodeTests: XCTestCase {

    func testThumbnailURLUsesStorageEndpoint() {
        let baseURL = URL(string: "https://127.0.0.1:8765/api")!

        let url = SpatialNode.thumbnailURL(forSourceId: "doc-123", baseURL: baseURL)

        XCTAssertEqual(
            url?.absoluteString,
            "https://127.0.0.1:8765/api/storage/thumbnail/doc-123"
        )
    }

    func testThumbnailURLRejectsEmptySourceId() {
        let url = SpatialNode.thumbnailURL(forSourceId: "", baseURL: nil)

        XCTAssertNil(url)
    }
}
