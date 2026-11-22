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
