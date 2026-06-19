import Foundation
import XCTest

@testable import Fichero

@MainActor
final class RemoteAccessConfigTests: XCTestCase {
    func testPairingBackendURLUsesAdvertisedRoot() throws {
        let advertised = "  https://pairing.example.com/  "
        let pairingURL = try XCTUnwrap(RemoteAccessConfig.pairingBackendURL(from: advertised))
        XCTAssertEqual(pairingURL.absoluteString, "https://pairing.example.com")

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

    func testPairingBackendURLRejectsLocalhostAndPaths() {
        XCTAssertNil(RemoteAccessConfig.pairingBackendURL(from: "http://127.0.0.1:8765"))
        XCTAssertNil(RemoteAccessConfig.pairingBackendURL(from: "http://127.2.3.4:8765"))
        XCTAssertNil(RemoteAccessConfig.pairingBackendURL(from: "http://[::1]:8765"))
        XCTAssertNil(RemoteAccessConfig.pairingBackendURL(from: "http://[::ffff:127.0.0.1]:8765"))
        XCTAssertNil(RemoteAccessConfig.pairingBackendURL(from: "https://pairing.example.com/api"))
        XCTAssertNil(RemoteAccessConfig.pairingBackendURL(from: "https://pairing.example.com?foo=bar"))
    }

    func testValidatedRemoteURLNormalizesReachableRoot() throws {
        let url = try validatedRemoteURL(from: " https://pairing.example.com/ ", allowLocalhost: false)
        XCTAssertEqual(url.absoluteString, "https://pairing.example.com")
    }

    func testValidatedRemoteURLRejectsUnsupportedSchemes() {
        XCTAssertThrowsError(try validatedRemoteURL(from: "ftp://pairing.example.com", allowLocalhost: false)) { error in
            XCTAssertEqual(error as? RemoteURLValidationError, .unsupportedScheme)
        }
    }
}
