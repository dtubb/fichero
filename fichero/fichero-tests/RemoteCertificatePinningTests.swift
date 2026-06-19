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
    private let advertisedPin = Data("advertised-spki".utf8).base64EncodedString()
    private let hostOnePin = Data("host-one-spki".utf8).base64EncodedString()
    private let hostTwoPin = Data("host-two-spki".utf8).base64EncodedString()

    override func tearDown() {
        super.tearDown()
        RemoteCertificatePinning.clearAdvertisedSPKIPin(hostString: hostOne)
        RemoteCertificatePinning.clearAdvertisedSPKIPin(hostString: hostTwo)
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: hostOne)
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: hostTwo)
        RemoteCertificatePinning.clearPersistedSPKIPin(hostString: hostOneDefaultPort)
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

    func testShouldEnforcePinningSkipsLoopbackHosts() {
        XCTAssertFalse(RemoteCertificatePinning.shouldEnforcePinning(for: URL(string: "http://127.0.0.1:8765")!))
        XCTAssertFalse(RemoteCertificatePinning.shouldEnforcePinning(for: URL(string: "https://localhost:8765")!))
        XCTAssertTrue(RemoteCertificatePinning.shouldEnforcePinning(for: URL(string: "https://host.tailnet.example")!))
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
