@testable import Fichero
import XCTest

final class PairingExchangeResponseTests: XCTestCase {
    func testRoundTripsSnakeCaseAndExpiry() throws {
        let expiry = Date(timeIntervalSince1970: 1_750_000_000)
        let original = PairingExchangeResponse(deviceId: "device-1", deviceToken: "token", expiresAt: expiry)
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(PairingExchangeResponse.self, from: data)

        XCTAssertEqual(decoded.deviceId, "device-1")
        XCTAssertEqual(decoded.deviceToken, "token")
        XCTAssertEqual(decoded.expiresAt, expiry)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertNotNil(object["device_id"])
        XCTAssertNotNil(object["device_token"])
        XCTAssertNotNil(object["expires_at"])
        XCTAssertNil(object["deviceId"])
    }
}
