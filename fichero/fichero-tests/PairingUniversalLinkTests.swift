import FicheroAPIClient
import Foundation
import XCTest

@testable import Fichero

// #3791: pairing invites must be recognised in BOTH forms — the custom
// fichero://pair scheme and the https://fichero.app/pair universal link — and
// both must decode to the same fields. The payload is redeemed peer-to-peer
// against the host it carries; the domain is only a name the app claims.
@MainActor
final class PairingUniversalLinkTests: XCTestCase {
    private let validSPKIPin = Data("spki-value".utf8).base64EncodedString()

    private func samplePayload() -> PairingQRCodePayload {
        let apiRoot = URL(string: "https://machine.tailnet.ts.net:8765/")!
        let code = PairingCodeRecord(
            code: "PAIR-ABC1",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        return PairingService(apiRoot: apiRoot).buildQRCodePayload(
            from: code,
            spki: validSPKIPin,
            libraryPath: "/Users/daniel/Library.fichero"
        )
    }

    func testCustomSchemeAndUniversalLinkBothRecognised() throws {
        let fichero = try XCTUnwrap(URL(string: "fichero://pair?payload=abc"))
        let universal = try XCTUnwrap(URL(string: "https://fichero.app/pair?payload=abc"))
        XCTAssertTrue(RemoteClientPairing.isPairingInviteLink(fichero))
        XCTAssertTrue(RemoteClientPairing.isPairingInviteLink(universal))
    }

    func testUnrelatedHttpsLinkIsNotAPairingLink() throws {
        // The get-Fichero landing page and other fichero.app paths must NOT be
        // mistaken for a pairing invite.
        let landing = try XCTUnwrap(URL(string: "https://fichero.app/"))
        let other = try XCTUnwrap(URL(string: "https://fichero.app/download"))
        let foreign = try XCTUnwrap(URL(string: "https://evil.example/pair?payload=abc"))
        XCTAssertFalse(RemoteClientPairing.isPairingInviteLink(landing))
        XCTAssertFalse(RemoteClientPairing.isPairingInviteLink(other))
        XCTAssertFalse(RemoteClientPairing.isPairingInviteLink(foreign))
    }

    func testUniversalLinkDecodesToSameFieldsAsCustomScheme() throws {
        let payload = samplePayload()
        // Reuse the minted custom-scheme link's encoded payload for the https form.
        let customLink = try RemoteClientPairing.inviteLinkString(from: payload)
        let encoded = try XCTUnwrap(URL(string: customLink)?.query)
        let universalLink = "https://fichero.app/pair?\(encoded)"

        let fields = try RemoteClientPairing.pairingFields(fromInviteOrPayload: universalLink)
        XCTAssertEqual(fields.remoteURL, "https://machine.tailnet.ts.net:8765")
        XCTAssertEqual(fields.pairCode, "PAIR-ABC1")
        XCTAssertEqual(fields.spkiPin, validSPKIPin)
        XCTAssertEqual(fields.libraryPath, "/Users/daniel/Library.fichero")
    }
}
