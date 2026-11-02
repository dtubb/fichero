import FicheroAPIClient
import Foundation
import XCTest

@testable import Fichero

/// The pairing payload and the fields a link yields (split from RemoteAccessConfigTests to keep each file under the size cap).
@MainActor
final class RemoteClientPairingFieldsTests: XCTestCase {
    private let validSPKIPin = Data("spki-value".utf8).base64EncodedString()

    func testPairingQRCodePayloadDecoderRoundTripsRemoteHost() throws {
        let apiRoot = URL(string: "https://pairing.example.com/")!
        let code = PairingCodeRecord(
            code: "PAIR-1234",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let payload = PairingService.buildQRCodePayload(apiRoot: apiRoot, from: code, spki: validSPKIPin)

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let message = try XCTUnwrap(String(bytes: encoder.encode(payload), encoding: .utf8))
        let decoded = try PairingQRCodePayloadDecoder.decode(message: message)

        XCTAssertEqual(decoded.version, 1)
        XCTAssertEqual(decoded.apiURL, "https://pairing.example.com")
        XCTAssertEqual(decoded.pairCode, code.code)
        XCTAssertEqual(decoded.spki, validSPKIPin)
        XCTAssertEqual(decoded.expiresAt, code.expiresAt)
        XCTAssertNil(decoded.libraryPath)
    }

    /// A never-expiring invitation (`expires_at` null) still gets its QR: the key is left out and a scan reads it as never-expires.
    func testPairingQRCodePayloadWithNoExpiryRoundTripsAndOmitsTheKey() throws {
        let apiRoot = URL(string: "https://pairing.example.com/")!
        let payload = PairingService.buildQRCodePayload(apiRoot: apiRoot, from: PairingCodeRecord(code: "PAIR-1234", expiresAt: nil))
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let message = try XCTUnwrap(String(bytes: encoder.encode(payload), encoding: .utf8))
        XCTAssertFalse(message.contains("expires_at"))
        let decoded = try PairingQRCodePayloadDecoder.decode(message: message)
        XCTAssertNil(decoded.expiresAt)
        XCTAssertEqual(decoded.pairCode, "PAIR-1234")
    }

    func testRemoteClientPairingFieldsNormalizeRemoteHost() throws {
        let apiRoot = URL(string: "https://pairing.example.com/")!
        let code = PairingCodeRecord(
            code: "PAIR-1234",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let payload = PairingService.buildQRCodePayload(apiRoot: apiRoot, 
            from: code,
            spki: validSPKIPin,
            libraryPath: "/Users/Shared/testuser/Archive/Open.fichero"
        )

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let message = try XCTUnwrap(String(bytes: encoder.encode(payload), encoding: .utf8))
        let pairingFields = try RemoteClientPairing.pairingFields(from: message)

        XCTAssertEqual(pairingFields.remoteURL, "https://pairing.example.com")
        XCTAssertEqual(pairingFields.pairCode, "PAIR-1234")
        XCTAssertEqual(pairingFields.spkiPin, validSPKIPin)
        XCTAssertEqual(pairingFields.libraryPath, "/Users/Shared/testuser/Archive/Open.fichero")
    }

    func testRemoteClientPairingFieldsAcceptDecodedPayload() throws {
        let apiRoot = URL(string: "https://pairing.example.com/")!
        let code = PairingCodeRecord(
            code: "PAIR-1234",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let payload = PairingService.buildQRCodePayload(apiRoot: apiRoot, 
            from: code,
            spki: validSPKIPin,
            libraryPath: "  /Users/Shared/testuser/Archive/Open.fichero  "
        )

        let pairingFields = try RemoteClientPairing.pairingFields(from: payload)

        XCTAssertEqual(pairingFields.remoteURL, "https://pairing.example.com")
        XCTAssertEqual(pairingFields.pairCode, "PAIR-1234")
        XCTAssertEqual(pairingFields.spkiPin, validSPKIPin)
        XCTAssertEqual(pairingFields.libraryPath, "/Users/Shared/testuser/Archive/Open.fichero")
    }

    func testRemoteClientPairingFieldsAcceptInviteLink() throws {
        let apiRoot = URL(string: "https://pairing.example.com/")!
        let code = PairingCodeRecord(
            code: "PAIR-1234",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let payload = PairingService.buildQRCodePayload(apiRoot: apiRoot, 
            from: code,
            spki: validSPKIPin,
            libraryPath: "/Users/Shared/testuser/Archive/Open.fichero"
        )
        let invite = try RemoteClientPairing.inviteLinkString(from: payload)

        let pairingFields = try RemoteClientPairing.pairingFields(fromInviteOrPayload: invite)

        XCTAssertEqual(pairingFields.remoteURL, "https://pairing.example.com")
        XCTAssertEqual(pairingFields.pairCode, "PAIR-1234")
        XCTAssertEqual(pairingFields.spkiPin, validSPKIPin)
        XCTAssertEqual(pairingFields.libraryPath, "/Users/Shared/testuser/Archive/Open.fichero")
    }

    /// `sharing.ios-bad-library-path`: a link with no project is not refused before the network; pairing asks the host.
    func testRemoteClientPairingFieldsAcceptAMissingLibraryPathAndAskTheHost() throws {
        let apiRoot = URL(string: "https://pairing.example.com/")!
        let code = PairingCodeRecord(
            code: "PAIR-1234",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let payload = PairingService.buildQRCodePayload(apiRoot: apiRoot, from: code, spki: validSPKIPin)

        let fields = try RemoteClientPairing.pairingFields(from: payload)
        XCTAssertEqual(fields.libraryPath, "")
        XCTAssertEqual(fields.altURLs, [])
    }

    func testRemoteClientPairingFieldsRejectMalformedInviteLink() {
        XCTAssertThrowsError(
            try RemoteClientPairing.pairingFields(fromInviteOrPayload: "fichero://pair?payload=not-base64")
        ) { error in
            XCTAssertEqual(error as? RemoteClientPairingError, .invalidInviteLink)
        }
    }

    func testRemoteClientPairingFieldsRejectLocalhostPayloads() throws {
        let apiRoot = URL(string: "https://127.0.0.1:8765/")!
        let code = PairingCodeRecord(
            code: "PAIR-1234",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let payload = PairingService.buildQRCodePayload(apiRoot: apiRoot, from: code, spki: validSPKIPin)

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let message = try XCTUnwrap(String(bytes: encoder.encode(payload), encoding: .utf8))

        XCTAssertThrowsError(try RemoteClientPairing.pairingFields(from: message)) { error in
            XCTAssertEqual(error as? RemoteURLValidationError, .localhostNotAllowed)
        }
    }

    func testRemoteClientPairingFieldsRejectMissingSPKIPayload() throws {
        let apiRoot = URL(string: "https://pairing.example.com/")!
        let code = PairingCodeRecord(
            code: "PAIR-1234",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let payload = PairingService.buildQRCodePayload(apiRoot: apiRoot, from: code, spki: "")

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let message = try XCTUnwrap(String(bytes: encoder.encode(payload), encoding: .utf8))

        XCTAssertThrowsError(try RemoteClientPairing.pairingFields(from: message)) { error in
            XCTAssertEqual(error as? RemoteCertificatePinningError, .missingSPKIPin)
        }
    }
}
