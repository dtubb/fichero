import CryptoKit
import Foundation

/// The message a client signs to answer an engine's sign-in challenge (multiuser-always-on).
///
/// Domain-separated so a signature made for another engine, client, purpose or expiry never verifies: a host
/// that relays one engine's nonce to this app gets a signature the other engine rejects. The engine rebuilds the
/// same bytes from its OWN engine id and the stored expiry (`_sign_in_message` in `accounts.py`).
nonisolated enum SignInMessage {
    static let signInPurpose = "fichero-sign-in-v1"
    static let resetPurpose = "fichero-reset-v1"

    static func bytes(
        purpose: String = signInPurpose, engineID: String, clientID: String, nonce: String, expiresAt: Int
    ) -> Data {
        Data([purpose, engineID, clientID, nonce, String(expiresAt)].joined(separator: "\u{0}").utf8)
    }
}

/// What the engine returns from `POST /api/auth/challenge`.
nonisolated struct SignInChallenge: Equatable, Sendable {
    let nonce: String
    let expiresAt: Int
    let engineID: String
}

/// The engine answered a sign-in call with a refusal (its HTTP status).
nonisolated enum SignInRefusal: Error, Equatable {
    case refused(statusCode: Int)
}

/// The engine calls app sign-in needs. The generated client backs the real one; tests fake it.
nonisolated protocol SignInTransport: Sendable {
    func challenge(clientID: String) async throws -> SignInChallenge
    /// Returns the session token.
    func signIn(clientID: String, nonce: String, signature: String) async throws -> String
    /// First launch only, over the local socket with the launch secret. Returns the new client's id.
    func firstRun(
        launchSecret: String, displayName: String, clientName: String, host: String, publicKeyPEM: String
    ) async throws -> String
    /// An owner row already exists without a key (the engine makes one for the first loopback request, before this
    /// app has asked): give that row its first key. Returns the new client's id.
    func migrateOwner(
        launchSecret: String, clientName: String, host: String, publicKeyPEM: String
    ) async throws -> String
}

nonisolated protocol OwnerKeyProviding: Sendable {
    /// The owner's P-256 key, created on first use. The same key on every device of the person (iCloud Keychain).
    func loadOrCreate() throws -> P256.Signing.PrivateKey
}

nonisolated protocol ClientIDStoring: Sendable {
    func clientID() -> String?
    func save(clientID: String)
    /// The engine no longer knows this client (its database was reset, or the client was revoked).
    func forget()
}

/// Signs the owner in to their engine by key, with no prompt and no password.
actor AppSignInService {
    private let transport: SignInTransport
    private let keys: OwnerKeyProviding
    private let clients: ClientIDStoring

    init(transport: SignInTransport, keys: OwnerKeyProviding, clients: ClientIDStoring) {
        self.transport = transport
        self.keys = keys
        self.clients = clients
    }

    enum Failure: Error, Equatable {
        /// No client is registered with this engine yet: the first-run bootstrap has not happened.
        case notRegistered
    }

    /// Challenge, sign, sign in. Returns the session token.
    func signIn() async throws -> String {
        guard let clientID = clients.clientID() else { throw Failure.notRegistered }
        let challenge: SignInChallenge
        do {
            challenge = try await transport.challenge(clientID: clientID)
        } catch SignInRefusal.refused(statusCode: 401) {
            // An unknown or revoked client looks the same to the engine. Forget it so the next step registers afresh.
            clients.forget()
            throw Failure.notRegistered
        }
        let message = SignInMessage.bytes(
            engineID: challenge.engineID, clientID: clientID, nonce: challenge.nonce, expiresAt: challenge.expiresAt
        )
        let signature = try keys.loadOrCreate().signature(for: message)
        return try await transport.signIn(
            clientID: clientID, nonce: challenge.nonce, signature: signature.derRepresentation.base64EncodedString()
        )
    }

    /// First launch: make the key, register it as this app's client through `first-run`, then sign in.
    func bootstrapOwner(
        launchSecret: String, displayName: String, clientName: String, host: String
    ) async throws -> String {
        let key = try keys.loadOrCreate()
        let pem = key.publicKey.pemRepresentation
        let clientID: String
        do {
            clientID = try await transport.firstRun(
                launchSecret: launchSecret, displayName: displayName, clientName: clientName, host: host,
                publicKeyPEM: pem
            )
        } catch SignInRefusal.refused(statusCode: 409) {
            // The engine's first authenticated request already made the (keyless) owner row: add the key to it.
            clientID = try await transport.migrateOwner(
                launchSecret: launchSecret, clientName: clientName, host: host, publicKeyPEM: pem
            )
        }
        clients.save(clientID: clientID)
        return try await signIn()
    }
}
