import CryptoKit
import FicheroAPIClient
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

/// The generated client behind `KeySignInTransport`. A refusal keeps its status: 401 is the engine refusing the key.
nonisolated struct GeneratedKeySignInTransport: KeySignInTransport, @unchecked Sendable {
    let client: FicheroClient

    func challenge(publicKeyPEM: String) async throws -> SignInChallenge {
        let response = try await client.api.keyChallengeApiAuthKeyChallengePost(body: .json(.init(publicKeyPem: publicKeyPEM)))
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            return SignInChallenge(nonce: body.nonce, expiresAt: body.expiresAt, engineID: body.engineId)
        case .unprocessableContent:
            throw SignInRefusal.refused(statusCode: 422)
        case .undocumented(let statusCode, _):
            throw SignInRefusal.refused(statusCode: statusCode)
        }
    }

    func signIn(publicKeyPEM: String, nonce: String, signature: String, deviceName: String, host: String) async throws -> String {
        let request = Components.Schemas.KeySignInRequest(
            publicKeyPem: publicKeyPEM, nonce: nonce, signature: signature, client: .init(name: deviceName, host: host))
        let response = try await client.api.signInByKeyApiAuthSignInByKeyPost(body: .json(request))
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.sessionToken
        case .unprocessableContent:
            throw SignInRefusal.refused(statusCode: 422)
        case .undocumented(let statusCode, _):
            throw SignInRefusal.refused(statusCode: statusCode)
        }
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

    /// The iPhone and iPad Connect screen's sections, in `order`. The silent key shows nothing, and the password is the
    /// host's alert after a typed address (`personSignInAlert`), so neither is a section. The nearby list always shows,
    /// with "Searching…" while it is empty.
    /// ponytail: approval and passkey rows join here when those methods are built.
    static func connectScreenRows(hasOwnMacs: Bool) -> [Option] {
        order(hasSyncedKey: false, hasOwnMacs: hasOwnMacs, canApprove: false, nearbyMacs: true, hasPasskey: false)
            .filter { $0 != .password }
    }
}
