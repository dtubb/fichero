@testable import Fichero
import XCTest

final class AclSetParamsTests: XCTestCase {
    func testEncodesSnakeCaseAndOmitsUnsetFields() throws {
        let data = try JSONEncoder().encode(AclSetParams(user: "u-1", targetId: "doc-1", remove: true))
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])

        XCTAssertEqual(object["user"] as? String, "u-1")
        XCTAssertEqual(object["target_id"] as? String, "doc-1")
        XCTAssertEqual(object["remove"] as? Bool, true)
        XCTAssertNil(object["targetId"])
        XCTAssertNil(object["role"])
        XCTAssertNil(object["effect"])
    }
}
