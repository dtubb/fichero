import CryptoKit
import Foundation

/// `multiuser.second-device-by-synced-key` (#2403): a device that holds the person's synced key, and no client row on this
/// engine, signs in by challenge. The signature names the KEY (its hash), never a client id, because the device has none yet;
/// the engine registers a `device` client for it on the first success (`sign_in_by_key` in `accounts.py`).
nonisolated enum KeySignInMessage {
    static let purpose = "fichero-key-sign-in-v1"

    /// The hex SHA-256 of the public key's PEM text exactly as sent; the engine hashes the PEM it received the same way.
    static func keyHash(publicKeyPEM: String) -> String {
        SHA256.hash(data: Data(publicKeyPEM.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    static func bytes(engineID: String, keyHash: String, nonce: String, expiresAt: Int) -> Data {
        Data([purpose, engineID, keyHash, nonce, String(expiresAt)].joined(separator: "\u{0}").utf8)
    }
}

nonisolated protocol KeySignInTransport: Sendable {
    func challenge(publicKeyPEM: String) async throws -> SignInChallenge
    /// Returns the session token. `device` names this device on the engine ("Daniel's iPhone").
    func signIn(publicKeyPEM: String, nonce: String, signature: String, deviceName: String, host: String) async throws -> String
}

actor SyncedKeySignIn {
    private let transport: KeySignInTransport
    private let keys: OwnerKeyProviding

    init(transport: KeySignInTransport, keys: OwnerKeyProviding) {
        self.transport = transport
        self.keys = keys
    }

    /// Challenge, sign, sign in: no password and no pairing code. A refusal (an unknown or revoked key) is thrown as it came.
    func signIn(deviceName: String, host: String) async throws -> String {
        let key = try keys.loadOrCreate()
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

/// `multiuser.password-comes-last` / `signin.password-comes-last` (#2403, #6568): what a sign-in screen offers, in order.
enum SignInOptions {
    enum Option: Equatable { case silentKey, ownMacs, approval, nearbyMacs, passkey, qrCode, password }

    /// The key signs in silently with nothing shown; the rest are rows, and the password is always last.
    static func order(hasSyncedKey: Bool, hasOwnMacs: Bool, canApprove: Bool, nearbyMacs: Bool, hasPasskey: Bool) -> [Option] {
        var options: [Option] = []
        if hasSyncedKey { options.append(.silentKey) }
        if hasOwnMacs { options.append(.ownMacs) }
        if canApprove { options.append(.approval) }
        if nearbyMacs { options.append(.nearbyMacs) }
        if hasPasskey { options.append(.passkey) }
        return options + [.qrCode, .password]
    }
}
