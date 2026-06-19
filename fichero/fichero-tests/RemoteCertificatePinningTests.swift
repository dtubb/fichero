import Foundation
#if canImport(Security)
import Security
#endif
@testable import FicheroAPIClient
import XCTest

final class RemoteCertificatePinningTests: XCTestCase {
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
