import FicheroAPIClient
import Foundation
import XCTest

@testable import Fichero

// Tests for the fichero://pair invite-link path wired in #2399.
// The URL-object path is what onOpenURL delivers — url.absoluteString may
// differ subtly from the raw link string due to percent-encoding normalisation,
// so these tests verify the full URL-object round-trip.
@MainActor
final class RemoteClientPairingInviteLinkTests: XCTestCase {
    private let validSPKIPin = Data("spki-value".utf8).base64EncodedString()

    // onOpenURL gives a URL; absoluteString is what we pass to pairingFields(fromInviteOrPayload:)
    func testURLObjectRoundTripsRemoteFields() throws {
        let apiRoot = URL(string: "https://machine.tailnet.ts.net:8765/")!
        let code = PairingCodeRecord(
            code: "PAIR-ABC1",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let payload = PairingService.buildQRCodePayload(apiRoot: apiRoot, 
            from: code,
            spki: validSPKIPin,
            libraryPath: "/Users/testuser/Library.fichero"
        )
        let linkString = try RemoteClientPairing.inviteLinkString(from: payload)
        let linkURL = try XCTUnwrap(URL(string: linkString), "inviteLinkString must produce a valid URL")

        let fields = try RemoteClientPairing.pairingFields(fromInviteOrPayload: linkURL.absoluteString)

        XCTAssertEqual(fields.remoteURL, "https://machine.tailnet.ts.net:8765")
        XCTAssertEqual(fields.pairCode, "PAIR-ABC1")
        XCTAssertEqual(fields.spkiPin, validSPKIPin)
        XCTAssertEqual(fields.libraryPath, "/Users/testuser/Library.fichero")
    }

    func testTailnetIPAddressRoundTrips() throws {
        let apiRoot = URL(string: "https://100.64.1.2:8765/")!
        let code = PairingCodeRecord(
            code: "PAIR-XYZ9",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let payload = PairingService.buildQRCodePayload(apiRoot: apiRoot, 
            from: code,
            spki: validSPKIPin,
            libraryPath: "/Volumes/Lib.fichero"
        )
        let linkString = try RemoteClientPairing.inviteLinkString(from: payload)

        let fields = try RemoteClientPairing.pairingFields(fromInviteOrPayload: linkString)

        XCTAssertEqual(fields.remoteURL, "https://100.64.1.2:8765")
    }

    func testInviteLinkStringProducesFicheroScheme() throws {
        let apiRoot = URL(string: "https://machine.tailnet.ts.net:8765/")!
        let code = PairingCodeRecord(
            code: "PAIR-SCM1",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let payload = PairingService.buildQRCodePayload(apiRoot: apiRoot, from: code, spki: validSPKIPin)

        let linkString = try RemoteClientPairing.inviteLinkString(from: payload)

        XCTAssertTrue(linkString.hasPrefix("fichero://pair?payload="))
    }

    func testMalformedBase64PayloadIsRejected() {
        XCTAssertThrowsError(
            try RemoteClientPairing.pairingFields(fromInviteOrPayload: "fichero://pair?payload=NOTBASE64!!!")
        ) { error in
            XCTAssertEqual(error as? RemoteClientPairingError, .invalidInviteLink)
        }
    }

    func testMissingPayloadQueryItemIsRejected() {
        XCTAssertThrowsError(
            try RemoteClientPairing.pairingFields(fromInviteOrPayload: "fichero://pair")
        ) { error in
            XCTAssertEqual(error as? RemoteClientPairingError, .invalidInviteLink)
        }
    }

    func testGarbageStringIsRejectedAsInvalidLink() {
        XCTAssertThrowsError(
            try RemoteClientPairing.pairingFields(fromInviteOrPayload: "fichero://pair?payload=aGVsbG8=")
        ) { error in
            // valid base64 but not a valid PairingQRCodePayload JSON
            XCTAssertEqual(error as? RemoteClientPairingError, .invalidInviteLink)
        }
    }
}
