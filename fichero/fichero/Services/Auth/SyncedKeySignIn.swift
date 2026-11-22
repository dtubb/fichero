import CryptoKit
import Foundation

actor SyncedKeySignIn {
    private let transport: KeySignInTransport
    private let key: P256.Signing.PrivateKey

    /// `key` is the synced key as loaded (`OwnerKeyStore.loadExisting`): a device without one has nothing to sign with,
    /// and a key made here would be one no engine knows.
    init(transport: KeySignInTransport, key: P256.Signing.PrivateKey) {
        self.transport = transport
        self.key = key
    }

    /// Challenge, sign, sign in: no password and no pairing code. A refusal (an unknown or revoked key) is thrown as it came.
    func signIn(deviceName: String, host: String) async throws -> String {
        let pem = key.publicKey.pemRepresentation
        let challenge = try await transport.challenge(publicKeyPEM: pem)
        let message = KeySignInMessage.bytes(
            engineID: challenge.engineID, keyHash: KeySignInMessage.keyHash(publicKeyPEM: pem),
            nonce: challenge.nonce, expiresAt: challenge.expiresAt)
        let signature = try key.signature(for: message)
        return try await transport.signIn(
            publicKeyPEM: pem, nonce: challenge.nonce, signature: signature.derRepresentation.base64EncodedString(),
            deviceName: deviceName, host: host)
    }
}
