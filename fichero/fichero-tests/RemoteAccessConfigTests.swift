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

        XCTAssertEqual(payload.apiURL, "https://pairing.example.com")
        XCTAssertEqual(payload.pairCode, "PAIR-1234")
        XCTAssertEqual(payload.spki, "spki-value")
        XCTAssertEqual(payload.expiresAt, code.expiresAt)
    }

    func testPairingQRCodePayloadDecoderRoundTripsRemoteHost() throws {
        let apiRoot = URL(string: "https://pairing.example.com/")!
        let code = PairingCodeRecord(
            code: "PAIR-1234",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let payload = PairingService(apiRoot: apiRoot).buildQRCodePayload(from: code, spki: "spki-value")

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let message = try XCTUnwrap(String(bytes: encoder.encode(payload), encoding: .utf8))
        let decoded = try PairingQRCodePayloadDecoder.decode(message: message)

        XCTAssertEqual(decoded.version, 1)
        XCTAssertEqual(decoded.apiURL, "https://pairing.example.com")
        XCTAssertEqual(decoded.pairCode, code.code)
        XCTAssertEqual(decoded.spki, "spki-value")
        XCTAssertEqual(decoded.expiresAt, code.expiresAt)
    }

    func testPairingBackendURLRejectsBlankString() {
        XCTAssertNil(RemoteAccessConfig.pairingBackendURL(from: ""))
        XCTAssertNil(RemoteAccessConfig.pairingBackendURL(from: "   "))
    }
}
