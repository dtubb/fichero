import Foundation
#if canImport(Security)
import Security
#endif
@testable import FicheroAPIClient
import XCTest

final class RemoteCertificatePinningTests: XCTestCase {
    private let hostOne = "https://host-one.tailnet.example"
    private let hostTwo = "https://host-two.tailnet.example:8443"
    private let hostOneDefaultPort = "https://host-one.tailnet.example:443/api"
    private let hostedBackendHost = "https://pairing.example.com:9443"
    private let tailscaleServeHost = "https://studio.tailnet-name.ts.net"
    private let advertisedPin = Data("advertised-spki".utf8).base64EncodedString()
    private let hostOnePin = Data("host-one-spki".utf8).base64EncodedString()
    private let hostTwoPin = Data("host-two-spki".utf8).base64EncodedString()

    /// `sharing.trust-rule-is-one-function`: the CLI reads the same table (`test_trust_rule_table_to_spec.py`).
    func testTrustRuleFollowsTheSharedTable() throws {
        struct Row: Decodable { let host: String; let publicCa: Bool }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let rows = try decoder.decode([Row].self, from: Data(contentsOf: TestFixtures.sampleFile("trust_rule_table.json")))
        XCTAssertFalse(rows.isEmpty)
        for row in rows {
            XCTAssertEqual(RemoteCertificatePinning.usesPublicCertificateAuthority(host: row.host), row.publicCa, row.host)
        }
    }

    override func tearDown() {
        super.tearDown()
        RemoteCertificatePinning.clearAdvertisedSPKIPin(hostString: hostOne)
        RemoteCertificatePinning.clearAdvertisedSPKIPin(hostString: hostTwo)
        RemoteCertificatePinning.clearAdvertisedSPKIPin(hostString: hostedBackendHost)
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: hostOne)
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: hostTwo)
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: hostedBackendHost)
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: tailscaleServeHost)
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: hostOneDefaultPort)
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: "https://127.0.0.1:8765")
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: "https://pairing.example.com")
    }

    func testValidatedSPKIPinRejectsMissingPin() {
        XCTAssertThrowsError(try RemoteCertificatePinning.validatedSPKIPin("   ")) { error in
            XCTAssertEqual(error as? RemoteCertificatePinningError, .missingSPKIPin)
        }
    }

    func testValidatedSPKIPinCanonicalizesSHA256Forms() throws {
        let digest = Data(repeating: 0xAB, count: 32)
        let base64 = digest.base64EncodedString()
        let hex = digest.map { String(format: "%02x", $0) }.joined()

        XCTAssertEqual(
            try RemoteCertificatePinning.validatedSPKIPin("sha256:\(base64)"),
            "sha256/\(base64)"
        )
        XCTAssertEqual(
            try RemoteCertificatePinning.validatedSPKIPin(hex),
            "sha256/\(base64)"
        )
    }

    func testLoopbackHTTPSUsesPinningOnlyWhenPinned() throws {
        let loopbackHost = "https://127.0.0.1:8765"
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: loopbackHost)

        XCTAssertFalse(RemoteCertificatePinning.shouldEnforcePinning(for: URL(string: loopbackHost)!))

        try RemoteCertificatePinning.persistSPKIPin(hostOnePin, hostString: loopbackHost)

        XCTAssertTrue(RemoteCertificatePinning.shouldEnforcePinning(for: URL(string: loopbackHost)!))
        XCTAssertTrue(RemoteCertificatePinning.shouldEnforcePinning(for: URL(string: "https://host.tailnet.example")!))
    }

    func testTailscaleServeHostsUseDefaultTrustUnlessPinned() throws {
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: tailscaleServeHost)

        XCTAssertFalse(RemoteCertificatePinning.shouldEnforcePinning(for: URL(string: tailscaleServeHost)!))

        try RemoteCertificatePinning.persistSPKIPin(hostOnePin, hostString: tailscaleServeHost)

        XCTAssertTrue(RemoteCertificatePinning.shouldEnforcePinning(for: URL(string: tailscaleServeHost)!))
    }

    func testPersistedSPKIPinsAreHostScoped() throws {
        try RemoteCertificatePinning.persistSPKIPin(hostOnePin, hostString: hostOne)
        try RemoteCertificatePinning.persistSPKIPin(hostTwoPin, hostString: hostTwo)

        XCTAssertEqual(RemoteCertificatePinning.persistedSPKIPin(hostString: hostOne), hostOnePin)
        XCTAssertEqual(RemoteCertificatePinning.persistedSPKIPin(hostString: hostTwo), hostTwoPin)

        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: hostOne)

        XCTAssertNil(RemoteCertificatePinning.persistedSPKIPin(hostString: hostOne))
        XCTAssertEqual(RemoteCertificatePinning.persistedSPKIPin(hostString: hostTwo), hostTwoPin)
    }

    func testAdvertisedSPKIPinIsStoredSeparatelyFromClientPins() throws {
        try RemoteCertificatePinning.persistAdvertisedSPKIPin(advertisedPin, hostString: hostOne)
        try RemoteCertificatePinning.persistSPKIPin(hostOnePin, hostString: hostOne)

        XCTAssertEqual(RemoteCertificatePinning.advertisedSPKIPin(hostString: hostOne), advertisedPin)
        XCTAssertEqual(RemoteCertificatePinning.persistedSPKIPin(hostString: hostOne), hostOnePin)
    }

    func testHostedBackendSPKIPinIsAvailableToBothQRAndClientSessions() throws {
        try RemoteCertificatePinning.persistHostedBackendSPKIPin(advertisedPin, hostString: hostedBackendHost)

        XCTAssertEqual(RemoteCertificatePinning.advertisedSPKIPin(hostString: hostedBackendHost), advertisedPin)
        XCTAssertEqual(RemoteCertificatePinning.persistedSPKIPin(hostString: hostedBackendHost), advertisedPin)
    }

    func testPersistedPinsNormalizeExplicitDefaultPorts() throws {
        try RemoteCertificatePinning.persistSPKIPin(hostOnePin, hostString: hostOneDefaultPort)
        try RemoteCertificatePinning.persistAdvertisedSPKIPin(advertisedPin, hostString: hostOneDefaultPort)

        XCTAssertEqual(RemoteCertificatePinning.persistedSPKIPin(hostString: hostOne), hostOnePin)
        XCTAssertEqual(RemoteCertificatePinning.advertisedSPKIPin(hostString: hostOne), advertisedPin)
    }

    #if canImport(Security)
    func testValidatePublicKeyMatchesRawSPKIAndSHA256Pins() throws {
        let attributes: [String: Any] = [
            kSecAttrKeyType as String: kSecAttrKeyTypeECSECPrimeRandom,
            kSecAttrKeySizeInBits as String: 256
        ]
        var error: Unmanaged<CFError>?
        let privateKey = try XCTUnwrap(SecKeyCreateRandomKey(attributes as CFDictionary, &error))
        let publicKey = try XCTUnwrap(SecKeyCopyPublicKey(privateKey))

        let rawPin = try RemoteCertificatePinning.spkiPin(for: publicKey)
        let sha256Pin = try RemoteCertificatePinning.sha256Pin(for: publicKey)

        XCTAssertNoThrow(try RemoteCertificatePinning.validatePublicKey(publicKey, expectedSPKIPin: rawPin))
        XCTAssertNoThrow(try RemoteCertificatePinning.validatePublicKey(publicKey, expectedSPKIPin: sha256Pin))

        let wrongPin = "sha256/\(Data(repeating: 0xCD, count: 32).base64EncodedString())"
        XCTAssertThrowsError(try RemoteCertificatePinning.validatePublicKey(publicKey, expectedSPKIPin: wrongPin)) { error in
            XCTAssertEqual(error as? RemoteCertificatePinningError, .serverIdentityMismatch)
        }
    }
    #endif
}
