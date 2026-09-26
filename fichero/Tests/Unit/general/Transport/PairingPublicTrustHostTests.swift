import FicheroAPIClient
import Foundation
import XCTest

@testable import Fichero

/// #5041: a pairing link must never assert a certificate the host does not hold.
///
/// Behind `tailscale serve` the advertised `.ts.net` name answers with
/// Tailscale's own Let's Encrypt certificate while the engine sits on loopback
/// behind it. Fichero was filing its own self-signed pin under that address and
/// shipping it in the link. The client stored it, and because the public-CA
/// exemption in `shouldEnforcePinning` only holds while NO pin is recorded,
/// storing one re-armed pinning against a key nothing there presents — every
/// Mac-to-Mac pairing over Tailscale was refused exactly as an attack would be.
///
/// These pin the rule on both sides of the link: the mint side advertises no pin
/// for such a host, the client side accepts none and discards any that arrives.
/// A host serving its OWN certificate is unchanged and still requires one.
@MainActor
final class PairingPublicTrustHostTests: XCTestCase {
    private let validSPKIPin = Data("spki-value".utf8).base64EncodedString()
    private let tailscaleURL = URL(string: "https://studio.tailnet-name.ts.net")!
    private let selfCertURL = URL(string: "https://pairing.example.com")!

    // MARK: - Which hosts carry their own public certificate

    func testTailscaleServeHostUsesAPublicCertificateAuthority() {
        XCTAssertTrue(RemoteCertificatePinning.usesPublicCertificateAuthority(url: tailscaleURL))
        XCTAssertTrue(RemoteCertificatePinning.usesPublicCertificateAuthority(host: "studio.tailnet-name.ts.net"))
        // Case must not decide it — a host string arrives however the user typed it.
        XCTAssertTrue(RemoteCertificatePinning.usesPublicCertificateAuthority(host: "Studio.Tailnet-Name.TS.NET"))
    }

    func testOrdinaryAndLANHostsDoNot() {
        // These serve the engine's own self-signed certificate, so the pin is
        // the only thing distinguishing the real Mac from anything else
        // answering to the same name. The rule must not leak to them.
        XCTAssertFalse(RemoteCertificatePinning.usesPublicCertificateAuthority(url: selfCertURL))
        XCTAssertFalse(RemoteCertificatePinning.usesPublicCertificateAuthority(host: "macbook-air-m1.local"))
        XCTAssertFalse(RemoteCertificatePinning.usesPublicCertificateAuthority(host: "192.168.1.42"))
        // A lookalike that merely CONTAINS the suffix is a different host.
        XCTAssertFalse(RemoteCertificatePinning.usesPublicCertificateAuthority(host: "ts.net.attacker.example"))
    }

    // MARK: - Mint side: what the share surfaces put in the link

    func testAPublicTrustHostAdvertisesNoPinEvenWhenOneIsAvailable() throws {
        // The Mac HAS minted a self-signed cert and holds its pin — it is simply
        // not the certificate this address presents, so it must not travel.
        let advertised = try RemoteClientPairing.advertisableSPKIPin(validSPKIPin, for: tailscaleURL)
        XCTAssertNil(advertised)
    }

    func testASelfCertificateHostAdvertisesItsPin() throws {
        let advertised = try RemoteClientPairing.advertisableSPKIPin(validSPKIPin, for: selfCertURL)
        XCTAssertEqual(advertised, validSPKIPin)
    }

    func testASelfCertificateHostWithNoPinYetIsStillABlocker() {
        // The "still minting the certificate" state. It must NOT silently become
        // a pinless link for a host that genuinely needs one.
        XCTAssertThrowsError(try RemoteClientPairing.advertisableSPKIPin("", for: selfCertURL))
    }

    func testAPublicTrustHostIsNeverBlockedOnACertificateItDoesNotNeed() throws {
        // The mirror of the case above: no pin yet is the NORMAL, finished state
        // here, not a half-prepared one, so the share surface must offer a link.
        XCTAssertNil(try RemoteClientPairing.advertisableSPKIPin("", for: tailscaleURL))
    }

    // MARK: - Client side: what the receiving device stores

    func testTheClientStoresNoPinForAPublicTrustHost() throws {
        XCTAssertNil(try RemoteClientPairing.resolvedSPKIPin(nil, for: tailscaleURL))
    }

    func testTheClientDISCARDSAPinAdvertisedForAPublicTrustHost() throws {
        // An older Mac (or a forged link) may still send one. Storing it is the
        // exact failure this issue is about, so it is dropped, not honoured.
        XCTAssertNil(try RemoteClientPairing.resolvedSPKIPin(validSPKIPin, for: tailscaleURL))
    }

    func testTheClientStillREQUIRESAPinFromASelfCertificateHost() {
        // The security property that must not regress: a link claiming an
        // ordinary remote host without a pin is rejected, not waved through.
        XCTAssertThrowsError(try RemoteClientPairing.resolvedSPKIPin(nil, for: selfCertURL)) { error in
            XCTAssertEqual(error as? RemoteCertificatePinningError, .missingSPKIPin)
        }
        XCTAssertThrowsError(try RemoteClientPairing.resolvedSPKIPin("not-a-pin!", for: selfCertURL))
    }

    func testTheClientKeepsAValidPinFromASelfCertificateHost() throws {
        XCTAssertEqual(try RemoteClientPairing.resolvedSPKIPin(validSPKIPin, for: selfCertURL), validSPKIPin)
    }

    // MARK: - End to end: a pinless link for a Tailscale host parses

    func testAPinlessTailscaleInviteLinkRoundTripsAndPairs() throws {
        // Before #5041 this link could not be built (the payload demanded a pin)
        // and could not be read (pairingFields threw). It is now the ordinary
        // shape of a Tailscale invite.
        let code = PairingCodeRecord(
            code: "PAIR-ABC1",
            expiresAt: Date(timeIntervalSince1970: 1_700_000_000)
        )
        let payload = PairingService.buildQRCodePayload(
            apiRoot: tailscaleURL,
            from: code,
            spki: nil,
            libraryPath: "/Users/testuser/Archive/Open.fichero"
        )
        XCTAssertNil(payload.spki, "the link must not carry a pin it cannot honour")

        let invite = try RemoteClientPairing.inviteLinkString(from: payload)
        let fields = try RemoteClientPairing.pairingFields(fromInviteOrPayload: invite)

        XCTAssertEqual(fields.remoteURL, "https://studio.tailnet-name.ts.net")
        XCTAssertEqual(fields.pairCode, "PAIR-ABC1")
        XCTAssertNil(fields.spkiPin)
        XCTAssertEqual(fields.libraryPath, "/Users/testuser/Archive/Open.fichero")
    }
}
