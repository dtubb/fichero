@testable import Fichero
import XCTest

final class PairingExchangeRequestTests: XCTestCase {
    func testEncodesDeviceNameInSnakeCase() throws {
        let data = try JSONEncoder().encode(PairingExchangeRequest(code: "ABC123", deviceName: "Phone"))
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: String])

        XCTAssertEqual(object, ["code": "ABC123", "device_name": "Phone"])
    }
}
