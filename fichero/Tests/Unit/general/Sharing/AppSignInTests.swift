import CryptoKit
import Foundation
import Testing

@testable import Fichero

/// multiuser.sign-in-by-challenge, app side (slice 4, #2403). The engine's own check is pinned in
/// `fichero-server/tests/unit/security/test_challenge_sign_in_to_spec.py`.
@Suite("App sign-in")
struct AppSignInTests {
    @Test("the signed message is the engine's: purpose, engine id, client id, nonce, expiry joined by NUL")
    func messageBytes() {
        let bytes = SignInMessage.bytes(engineID: "eng", clientID: "cli", nonce: "non", expiresAt: 1_700_000_000)
        #expect(bytes == Data("fichero-sign-in-v1\u{0}eng\u{0}cli\u{0}non\u{0}1700000000".utf8))
    }

    @Test("a reset message cannot be a sign-in message")
    func purposesDiffer() {
        let signIn = SignInMessage.bytes(engineID: "e", clientID: "c", nonce: "n", expiresAt: 1)
        let reset = SignInMessage.bytes(purpose: SignInMessage.resetPurpose, engineID: "e", clientID: "c", nonce: "n", expiresAt: 1)
        #expect(signIn != reset)
    }

    @Test("sign-in answers the challenge with a signature the registered public key verifies")
    func signsTheChallenge() async throws {
        let key = P256.Signing.PrivateKey()
        let transport = FakeTransport(challenge: SignInChallenge(nonce: "n1", expiresAt: 99, engineID: "engine-a"))
        let service = AppSignInService(transport: transport, keys: FixedKey(key), clients: MemoryClientID("client-1"))
        let token = try await service.signIn()
        #expect(token == "session-token")
        let sent = try #require(transport.signIns.first)
        #expect(sent.clientID == "client-1" && sent.nonce == "n1")
        let der = try #require(Data(base64Encoded: sent.signature))
        let message = SignInMessage.bytes(engineID: "engine-a", clientID: "client-1", nonce: "n1", expiresAt: 99)
        #expect(key.publicKey.isValidSignature(try P256.Signing.ECDSASignature(derRepresentation: der), for: message))
    }

    @Test("with no registered client, sign-in says so instead of calling the engine")
    func notRegistered() async {
        let transport = FakeTransport(challenge: SignInChallenge(nonce: "n", expiresAt: 1, engineID: "e"))
        let service = AppSignInService(transport: transport, keys: FixedKey(P256.Signing.PrivateKey()), clients: MemoryClientID(nil))
        await #expect(throws: AppSignInService.Failure.notRegistered) { try await service.signIn() }
        #expect(transport.challengeCalls == 0)
    }

    @Test("first launch registers the public key through first-run, remembers the client, then signs in")
    func bootstrap() async throws {
        let key = P256.Signing.PrivateKey()
        let transport = FakeTransport(challenge: SignInChallenge(nonce: "n", expiresAt: 5, engineID: "e"))
        let clients = MemoryClientID(nil)
        let service = AppSignInService(transport: transport, keys: FixedKey(key), clients: clients)
        _ = try await service.bootstrapOwner(launchSecret: "ab", displayName: "Daniel", clientName: "Fichero", host: "Mac")
        let first = try #require(transport.firstRuns.first)
        #expect(first.launchSecret == "ab" && first.publicKeyPEM == key.publicKey.pemRepresentation)
        #expect(clients.clientID() == "new-client")
        #expect(transport.signIns.first?.clientID == "new-client")
    }
}

extension AppSignInTests {
    @Test("a second launch signs in with the remembered client and registers nothing")
    func secondLaunchSignsInOnly() async throws {
        let transport = FakeTransport(challenge: SignInChallenge(nonce: "n", expiresAt: 5, engineID: "e"))
        let service = AppSignInService(transport: transport, keys: FixedKey(P256.Signing.PrivateKey()), clients: MemoryClientID("client-1"))
        _ = try await service.signIn()
        _ = try await service.signIn()  // an engine restart signs in again
        #expect(transport.firstRuns.isEmpty && transport.migrations.isEmpty && transport.signIns.count == 2)
    }

    @Test("a client the engine no longer knows is forgotten, so the launch registers afresh")
    func staleClientIsForgotten() async {
        let transport = FakeTransport(challenge: SignInChallenge(nonce: "n", expiresAt: 5, engineID: "e"))
        transport.challengeRefusal = 401
        let clients = MemoryClientID("gone")
        let service = AppSignInService(transport: transport, keys: FixedKey(P256.Signing.PrivateKey()), clients: clients)
        await #expect(throws: AppSignInService.Failure.notRegistered) { try await service.signIn() }
        #expect(clients.clientID() == nil)
    }

    @Test("a transient engine failure does not forget the client")
    func transientFailureKeepsClient() async {
        let transport = FakeTransport(challenge: SignInChallenge(nonce: "n", expiresAt: 5, engineID: "e"))
        transport.challengeRefusal = 503
        let clients = MemoryClientID("client-1")
        let service = AppSignInService(transport: transport, keys: FixedKey(P256.Signing.PrivateKey()), clients: clients)
        await #expect(throws: SignInRefusal.refused(statusCode: 503)) { try await service.signIn() }
        #expect(clients.clientID() == "client-1")
    }

    @Test("when first-run says an owner exists, the key goes onto that owner through migrate-owner")
    func bootstrapFallsBackToMigrateOwner() async throws {
        let key = P256.Signing.PrivateKey()
        let transport = FakeTransport(challenge: SignInChallenge(nonce: "n", expiresAt: 5, engineID: "e"))
        transport.firstRunRefusal = 409
        let clients = MemoryClientID(nil)
        let service = AppSignInService(transport: transport, keys: FixedKey(key), clients: clients)
        _ = try await service.bootstrapOwner(launchSecret: "ab", displayName: "Daniel", clientName: "Fichero", host: "Mac")
        #expect(transport.migrations.first?.publicKeyPEM == key.publicKey.pemRepresentation)
        #expect(clients.clientID() == "migrated-client")
        #expect(transport.signIns.first?.clientID == "migrated-client")
    }

    @Test("any other first-run refusal is not retried as a migration")
    func otherRefusalsStop() async {
        let transport = FakeTransport(challenge: SignInChallenge(nonce: "n", expiresAt: 5, engineID: "e"))
        transport.firstRunRefusal = 401
        let service = AppSignInService(transport: transport, keys: FixedKey(P256.Signing.PrivateKey()), clients: MemoryClientID(nil))
        await #expect(throws: SignInRefusal.refused(statusCode: 401)) {
            try await service.bootstrapOwner(launchSecret: "ab", displayName: "D", clientName: "F", host: "M")
        }
        #expect(transport.migrations.isEmpty)
    }
}

private final class FakeTransport: SignInTransport, @unchecked Sendable {
    struct SignIn { let clientID: String; let nonce: String; let signature: String }
    struct FirstRun { let launchSecret: String; let publicKeyPEM: String }
    let challengeToReturn: SignInChallenge
    private(set) var challengeCalls = 0
    private(set) var signIns: [SignIn] = []
    private(set) var firstRuns: [FirstRun] = []
    private(set) var migrations: [FirstRun] = []
    var firstRunRefusal: Int?
    var challengeRefusal: Int?

    init(challenge: SignInChallenge) { challengeToReturn = challenge }

    func challenge(clientID: String) async throws -> SignInChallenge {
        challengeCalls += 1
        if let code = challengeRefusal { throw SignInRefusal.refused(statusCode: code) }
        return challengeToReturn
    }

    func signIn(clientID: String, nonce: String, signature: String) async throws -> String {
        signIns.append(SignIn(clientID: clientID, nonce: nonce, signature: signature))
        return "session-token"
    }

    func firstRun(
        launchSecret: String, displayName: String, clientName: String, host: String, publicKeyPEM: String
    ) async throws -> String {
        firstRuns.append(FirstRun(launchSecret: launchSecret, publicKeyPEM: publicKeyPEM))
        if let code = firstRunRefusal { throw SignInRefusal.refused(statusCode: code) }
        return "new-client"
    }

    func migrateOwner(launchSecret: String, clientName: String, host: String, publicKeyPEM: String) async throws -> String {
        migrations.append(FirstRun(launchSecret: launchSecret, publicKeyPEM: publicKeyPEM))
        return "migrated-client"
    }
}

private struct FixedKey: OwnerKeyProviding {
    let key: P256.Signing.PrivateKey
    init(_ key: P256.Signing.PrivateKey) { self.key = key }
    func loadOrCreate() throws -> P256.Signing.PrivateKey { key }
}

private final class MemoryClientID: ClientIDStoring, @unchecked Sendable {
    private var value: String?
    init(_ value: String?) { self.value = value }
    func clientID() -> String? { value }
    func save(clientID: String) { value = clientID }
    func forget() { value = nil }
}
