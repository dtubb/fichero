@testable import Fichero
import XCTest

final class DocumentStructureNodePageRangeTests: XCTestCase {
    func testPageRangeRoundTripsThroughCodable() throws {
        let original = DocumentStructureNode.PageRange(start: 3, end: 17)
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(DocumentStructureNode.PageRange.self, from: data)

        XCTAssertEqual(decoded, original)
    }
}
