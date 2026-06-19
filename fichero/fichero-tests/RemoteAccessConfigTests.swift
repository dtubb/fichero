import Foundation
import XCTest

@testable import Fichero

@MainActor
final class RemoteAccessConfigTests: XCTestCase {
    func testPairingBackendURLUsesAdvertisedRoot() throws {
        let advertised = "  https://pairing.example.com/  "
        let pairingURL = try XCTUnwrap(RemoteAccessConfig.pairingBackendURL(from: advertised))
        XCTAssertEqual(pairingURL.absoluteString, "https://pairing.example.com/")

        let code = PairingCodeRecord(
            code: "PAIR-1234",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let payload = PairingService(apiRoot: pairingURL).buildQRCodePayload(from: code, spki: "spki-value")

        XCTAssertEqual(payload.apiURL, "https://pairing.example.com/")
        XCTAssertEqual(payload.pairCode, "PAIR-1234")
        XCTAssertEqual(payload.spki, "spki-value")
        XCTAssertEqual(payload.expiresAt, code.expiresAt)
    }

    func testPairingBackendURLRejectsBlankString() {
        XCTAssertNil(RemoteAccessConfig.pairingBackendURL(from: ""))
        XCTAssertNil(RemoteAccessConfig.pairingBackendURL(from: "   "))
    }
}
