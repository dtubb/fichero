import FicheroAPIClient
import Foundation
import OSLog

/// The generated client behind `SignInTransport`: the three engine calls app sign-in needs.
nonisolated struct GeneratedSignInTransport: SignInTransport, @unchecked Sendable {
    let client: FicheroClient

    typealias Failure = SignInRefusal

    func challenge(clientID: String) async throws -> SignInChallenge {
        let response = try await client.api.challengeApiAuthChallengePost(body: .json(.init(clientId: clientID)))
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            return SignInChallenge(nonce: body.nonce, expiresAt: body.expiresAt, engineID: body.engineId)
        case .unprocessableContent:
            throw Failure.refused(statusCode: 422)
        case .undocumented(let statusCode, _):
            throw Failure.refused(statusCode: statusCode)
        }
    }

    func signIn(clientID: String, nonce: String, signature: String) async throws -> String {
        let request = Components.Schemas.SignInRequest(clientId: clientID, nonce: nonce, signature: signature)
        let response = try await client.api.signInApiAuthSignInPost(body: .json(request))
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.sessionToken
        case .unprocessableContent:
            throw Failure.refused(statusCode: 422)
        case .undocumented(let statusCode, _):
            throw Failure.refused(statusCode: statusCode)
        }
    }

    func firstRun(
        launchSecret: String, displayName: String, clientName: String, host: String, publicKeyPEM: String
    ) async throws -> String {
        let request = Components.Schemas.FirstRunRequest(
            displayName: displayName, publicKeyPem: publicKeyPEM, client: .init(name: clientName, host: host)
        )
        let response = try await client.api.firstRunApiAuthFirstRunPost(
            headers: .init(xFicheroLaunchSecret: launchSecret), body: .json(request)
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.client.id
        case .unprocessableContent:
            throw Failure.refused(statusCode: 422)
        case .undocumented(let statusCode, _):
            throw Failure.refused(statusCode: statusCode)
        }
    }

    func migrateOwner(
        launchSecret: String, clientName: String, host: String, publicKeyPEM: String
    ) async throws -> String {
        let request = Components.Schemas.MigrateOwnerRequest(
            publicKeyPem: publicKeyPEM, client: .init(name: clientName, host: host)
        )
        let response = try await client.api.migrateOwnerApiAuthMigrateOwnerPost(
            headers: .init(xFicheroLaunchSecret: launchSecret), body: .json(request)
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.client.id
        case .unprocessableContent:
            throw Failure.refused(statusCode: 422)
        case .undocumented(let statusCode, _):
            throw Failure.refused(statusCode: statusCode)
        }
    }
}

/// Signs the app in to its engine by the owner's key, once per launch, before the library warms up.
///
/// Registered client on this engine: challenge, sign, and keep the session token where login keeps it (the Keychain,
/// per host). No client yet and a launch secret in hand (the one the app gave its own engine on stdin, or Debug Dev
/// Local's 0600 file): first-run makes the owner and registers the key; if the engine already made a keyless owner
/// for the first loopback request (it does, before this runs), migrate-owner gives that row the key.
/// Neither: nothing to do. A failure is logged and never blocks launch (unknown is not signed out):
/// until the ambient owner leaves in slice 10, local requests still carry the bootstrap token, so a sign-in that
/// cannot happen costs the audit its client name, not the user their library.
@MainActor
final class OwnerSignInCoordinator {
    private let client: FicheroClient
    private let keys: OwnerKeyProviding
    private let log = Logger(subsystem: "app.fichero.fichero", category: "OwnerSignIn")

    init(client: FicheroClient, keys: OwnerKeyProviding = OwnerKeyStore()) {
        self.client = client
        self.keys = keys
    }

    private var hostString: String { client.baseURL.absoluteString }

    func run() async {
        let service = AppSignInService(
            transport: GeneratedSignInTransport(client: client),
            keys: keys,
            clients: UserDefaultsClientIDStore(engineKey: hostString)
        )
        do {
            let token: String
            do {
                token = try await service.signIn()
            } catch AppSignInService.Failure.notRegistered {
                guard let secret = EngineLaunchSecretStore.current ?? Self.devLaunchSecret() else { return }
                token = try await service.bootstrapOwner(
                    launchSecret: secret, displayName: Self.ownerName, clientName: "Fichero", host: Self.hostName
                )
            }
            try AuthTokenMiddleware.persistSessionToken(token, hostString: hostString)
            log.info("Signed in to the engine by the owner key")
        } catch {
            log.error("Owner key sign-in did not complete: \(String(describing: error), privacy: .public)")
        }
    }

    private static var hostName: String {
        let name = ProcessInfo.processInfo.hostName.trimmingCharacters(in: .whitespacesAndNewlines)
        return name.isEmpty ? "Mac" : name
    }

    /// The macOS full name, editable later; the person's own name for the owner row.
    private static var ownerName: String {
        let name = NSFullUserName().trimmingCharacters(in: .whitespacesAndNewlines)
        return name.isEmpty ? "Owner" : name
    }

    /// Debug Dev Local only: the secret `dev-uds-engine.sh` left next to the socket. Release, Beta and App Store
    /// builds compile this away: they only ever spawn their own engine.
    private static func devLaunchSecret() -> String? {
        #if DEBUG
        let socketPath = ProcessInfo.processInfo.environment["FICHERO_FORCE_UDS_PATH"] ?? EngineConfig.udsSocketPath
        let file = URL(fileURLWithPath: socketPath).deletingLastPathComponent().appendingPathComponent("launch-secret")
        return DevLaunchSecretFile.readAndDelete(at: file)
        #else
        return nil
        #endif
    }
}
