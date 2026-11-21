import CryptoKit
@testable import Fichero
import Foundation
import Testing

/// multiuser.second-device-by-synced-key (the app's half) and multiuser.password-comes-last, #2403.
private struct Sent { let pem: String, signature: String, device: String, host: String }

struct SyncedKeySignInTests {
    private struct Keys: OwnerKeyProviding {
        let key: P256.Signing.PrivateKey
        func loadOrCreate() throws -> P256.Signing.PrivateKey { key }
    }

    private final class Transport: KeySignInTransport, @unchecked Sendable {
        var sent: Sent?
        func challenge(publicKeyPEM: String) async throws -> SignInChallenge {
            SignInChallenge(nonce: "n1", expiresAt: 1_900_000_000, engineID: "eng")
        }
        func signIn(publicKeyPEM: String, nonce: String, signature: String, deviceName: String, host: String) async throws -> String {
            sent = Sent(pem: publicKeyPEM, signature: signature, device: deviceName, host: host)
            return "session"
        }
    }

    /// The expected value is Python's `hashlib.sha256(b"PEM-TEXT").hexdigest()`, which is what the engine computes.
    @Test func theKeyHashIsTheHexSha256OfThePEMText() {
        #expect(KeySignInMessage.keyHash(publicKeyPEM: "PEM-TEXT") == "5cc7be15de434601c06c03fcdfd7b95eef9a042333aed2026102e6a27b83ba06")
    }

    @Test func theSignatureNamesTheKeyAndVerifiesWithIt() async throws {
        let key = P256.Signing.PrivateKey()
        let transport = Transport()
        let token = try await SyncedKeySignIn(transport: transport, keys: Keys(key: key))
            .signIn(deviceName: "Daniel's iPhone", host: "air.tail1234.ts.net")
        #expect(token == "session")
        let sent = try #require(transport.sent)
        #expect(sent.device == "Daniel's iPhone" && sent.host == "air.tail1234.ts.net" && sent.pem == key.publicKey.pemRepresentation)
        let message = KeySignInMessage.bytes(
            engineID: "eng", keyHash: KeySignInMessage.keyHash(publicKeyPEM: sent.pem), nonce: "n1", expiresAt: 1_900_000_000)
        let der = try #require(Data(base64Encoded: sent.signature))
        let signature = try P256.Signing.ECDSASignature(derRepresentation: der)
        #expect(key.publicKey.isValidSignature(signature, for: message))
        #expect((String(bytes: message, encoding: .utf8) ?? "").hasPrefix("fichero-key-sign-in-v1\u{0}eng\u{0}"))
    }

    @Test func thePasswordIsAlwaysLastAndTheKeyFirst() {
        let all = SignInOptions.order(hasSyncedKey: true, hasOwnMacs: true, canApprove: true, nearbyMacs: true, hasPasskey: true)
        #expect(all == [.silentKey, .ownMacs, .approval, .nearbyMacs, .passkey, .qrCode, .password])
        let none = SignInOptions.order(hasSyncedKey: false, hasOwnMacs: false, canApprove: false, nearbyMacs: false, hasPasskey: false)
        #expect(none == [.qrCode, .password])
    }
}
